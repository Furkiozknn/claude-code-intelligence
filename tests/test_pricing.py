from datetime import date
from decimal import Decimal

from cci.model import Tokens
from cci.pricing import LONG_CONTEXT_THRESHOLD, PricingTable, normalize_for_pricing

SNAPSHOT = {
    "source": "test", "fetched_at": "2026-09-07", "sha256": "abcdef0123456789",
    "models": {
        "claude-opus-5": {"input_cost_per_token": 5e-06, "output_cost_per_token": 2.5e-05,
                          "cache_read_input_token_cost": 5e-07, "cache_creation_input_token_cost": 6.25e-06,
                          "cache_creation_input_token_cost_above_1hr": 1e-05, "max_input_tokens": 1000000},
        "claude-sonnet-4-5": {"input_cost_per_token": 3e-06, "output_cost_per_token": 1.5e-05,
                              "cache_read_input_token_cost": 3e-07, "cache_creation_input_token_cost": 3.75e-06,
                              "cache_creation_input_token_cost_above_1hr": 6e-06,
                              "input_cost_per_token_above_200k_tokens": 6e-06,
                              "output_cost_per_token_above_200k_tokens": 2.25e-05,
                              "cache_read_input_token_cost_above_200k_tokens": 6e-07,
                              "cache_creation_input_token_cost_above_200k_tokens": 7.5e-06,
                              "cache_creation_input_token_cost_above_1hr_above_200k_tokens": 1.2e-05,
                              "deprecation_date": "2027-01-01"},
        "claude-nocache-1": {"input_cost_per_token": 1e-06, "output_cost_per_token": 2e-06},
        "claude-broken": {"output_cost_per_token": 2e-06},
    },
}


def table():
    return PricingTable.from_snapshot(SNAPSHOT)


def test_normalization_candidates():
    assert normalize_for_pricing("us.anthropic.claude-sonnet-4-5-20250929-v1:0") == [
        "us.anthropic.claude-sonnet-4-5-20250929-v1:0", "claude-sonnet-4-5-20250929-v1:0",
        "claude-sonnet-4-5-20250929", "claude-sonnet-4-5"]
    assert table().lookup("us.anthropic.claude-sonnet-4-5-20250929-v1:0").model == "claude-sonnet-4-5"
    assert table().lookup("gpt-5") is None


def test_version_and_estimator():
    t = table()
    assert t.version == "2026-09-07-abcdef01" and t.estimator.id == "pricing.litellm" and len(t) == 3


def test_cost_with_ttl_split_is_reconciled_estimate():
    t = table()
    f = t.cost(Tokens(input=1000, output=100, cache_read=10000, cache_write_5m=600, cache_write_1h=400,
                      cache_write_total=1000), "claude-opus-5")
    # 1000*5e-6 + 100*2.5e-5 + 10000*5e-7 + 600*6.25e-6 + 400*1e-5 = 0.005+0.0025+0.005+0.00375+0.004 = 0.02025
    assert f.released and f.released_as == "reconciled" and f.evidence_class.value == "estimated"
    assert f.value == Decimal("20250000") and f.render() == "$0.02"
    assert f.estimator == t.estimator


def test_cost_without_ttl_split_is_draft_under_5m_assumption():
    f = table().cost(Tokens(input=0, output=0, cache_write_total=1000), "claude-opus-5")
    assert f.released and f.released_as == "draft" and f.value == Decimal("6250000")


def test_unknown_model_and_missing_components_are_withheld():
    t = table()
    assert not t.cost(Tokens(input=1, output=1), "gpt-5").released
    assert "bilinmeyen" in t.cost(Tokens(input=1, output=1), "gpt-5").withheld_because
    ok = t.cost(Tokens(input=10, output=10), "claude-nocache-1")
    assert ok.released and ok.value == Decimal("30000")
    missing = t.cost(Tokens(input=10, output=10, cache_read=5), "claude-nocache-1")
    assert not missing.released and "cache okuma" in missing.withheld_because
    assert t.lookup("claude-broken") is None  # input fiyati yok -> tabloya girmez


def test_long_context_tier_applies_to_whole_request():
    t = table()
    small = t.cost(Tokens(input=LONG_CONTEXT_THRESHOLD, output=10), "claude-sonnet-4-5")
    big = t.cost(Tokens(input=LONG_CONTEXT_THRESHOLD + 1, output=10), "claude-sonnet-4-5")
    assert small.value == Decimal(str(LONG_CONTEXT_THRESHOLD * 3e-06 + 10 * 1.5e-05)) * 10**9
    assert big.value == (Decimal(LONG_CONTEXT_THRESHOLD + 1) * Decimal("6e-06") + Decimal(10) * Decimal("2.25e-05")) * 10**9


def test_bundled_snapshot_loads_and_has_current_models():
    t = PricingTable.load_bundled()
    assert len(t) >= 20 and t.fetched_at == date(2026, 9, 7) and t.source.startswith("https://")
    for m in ("claude-opus-5", "claude-sonnet-5", "claude-fable-5-1", "claude-haiku-4-5", "claude-opus-4-5"):
        p = t.lookup(m)
        assert p is not None and p.cache_write_1h is not None, m
    f = t.cost(Tokens(input=1_000_000, output=0), "claude-fable-5-1")
    assert f.released and f.render() == "$10.00"
