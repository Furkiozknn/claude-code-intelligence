"""Spending budgets: `[budget]` in config.toml, `cci budget`, budget alerts."""

import json
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from cci.alerts.engine import AlertInputs, evaluate_rules
from cci.analytics.budget import budget_status
from cci.analytics.summaries import Conservation, DailySummary, Totals
from cci.cli import EXIT_BUDGET, EXIT_NO_DATA, EXIT_OK, main
from cci.config import AlertConfig, load_config
from cci.model.evidence import EvidenceClass
from cci.model.figure import Figure, usd_to_nano
from cci.model.usage import Tokens
from tests.test_pipeline import assistant, layout


def _day(d: date, usd: float | None) -> DailySummary:
    cost = (Figure.derived(usd_to_nano(usd), "nanoUSD") if usd is not None
            else Figure.withheld("nanoUSD", EvidenceClass.DERIVED, "fiyatsiz model"))
    totals = Totals(requests=1, tokens=Tokens(input=1, output=1, cache_read=0, cache_write_total=0),
                    cost=cost, vendor_cost=Figure.withheld("nanoUSD", EvidenceClass.VENDOR_ESTIMATED, "yok"))
    return DailySummary(day=d, tz="UTC", provider="anthropic", instance_id="i", totals=totals, models=(), projects=(),
                        conservation=Conservation(ok=True, total_tokens=2, model_tokens=2, project_tokens=2),
                        summary_version=1)


def test_daily_states_follow_the_thresholds():
    today = date(2026, 10, 15)
    for usd, state in [(1.0, "ok"), (4.0, "warning"), (5.0, "exceeded"), (7.5, "exceeded")]:
        (b,) = budget_status([_day(today, usd), _day(date(2026, 10, 14), 99)], today, daily_usd=5, monthly_usd=None)
        assert (b.period, b.state) == ("day", state)
        assert b.pct == pytest.approx(usd / 5 * 100)


def test_month_sums_the_month_to_date_and_projects_linearly():
    today = date(2026, 10, 10)  # day 10 of a 31-day month
    days = [_day(date(2026, 10, d), 2.0) for d in range(1, 11)] + [_day(date(2026, 9, 30), 50)]
    (b,) = budget_status(days, today, daily_usd=None, monthly_usd=100)
    assert b.spent.value == usd_to_nano(20)
    assert b.pct == pytest.approx(20)
    assert b.projected.value == usd_to_nano(62)  # 20 * 31 / 10
    assert b.projected.evidence_class == EvidenceClass.PREDICTED and b.projected.projected
    assert b.state == "ok"
    (over,) = budget_status(days, today, daily_usd=None, monthly_usd=50)
    assert over.state == "projected_over"


def test_a_withheld_cost_makes_the_budget_unknown_not_safe():
    today = date(2026, 10, 15)
    (b,) = budget_status([_day(today, 1.0), _day(today, None)], today, daily_usd=5, monthly_usd=None)
    assert b.state == "unknown" and b.pct is None and not b.spent.released


def test_no_spend_is_an_observed_zero():
    (b,) = budget_status([], date(2026, 10, 15), daily_usd=5, monthly_usd=None)
    assert b.spent.released and b.spent.value == 0 and b.state == "ok"


def test_alert_rules():
    now = datetime(2026, 10, 15, 12, tzinfo=UTC)
    today = now.date()
    days = [_day(today, 6.0)]
    statuses = budget_status(days, today, daily_usd=5, monthly_usd=1000)
    alerts = evaluate_rules(AlertInputs(budgets=statuses), now, AlertConfig())
    (exceeded,) = [a for a in alerts if a.rule_id == "budget.exceeded"]
    assert exceeded.severity == "critical" and exceeded.subject.id == "day:2026-10-15"
    assert exceeded.basis == "certain"
    projected = budget_status([_day(date(2026, 10, 1), 40.0)], date(2026, 10, 2), daily_usd=None, monthly_usd=50)
    (a,) = evaluate_rules(AlertInputs(budgets=projected), now, AlertConfig())
    assert a.rule_id == "budget.projected" and a.basis == "probable" and a.subject.id == "month:2026-10"
    unknown = budget_status([_day(today, None)], today, daily_usd=5, monthly_usd=None)
    assert evaluate_rules(AlertInputs(budgets=unknown), now, AlertConfig()) == []


def test_config_parsing_ignores_nonsense(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text("[budget]\ndaily_usd = 5\nmonthly_usd = -3\nwarn_pct = 250\n", encoding="utf-8")
    cfg = load_config(p).budget
    assert cfg.daily_usd == 5.0 and cfg.monthly_usd is None and cfg.warn_pct == 80.0 and cfg.configured
    p.write_text("[budget]\ndaily_usd = true\n", encoding="utf-8")
    assert not load_config(p).budget.configured
    assert not load_config(tmp_path / "missing.toml").budget.configured


# --- CLI ---------------------------------------------------------------------


def run(args, tmp_path, env, capsys):
    code = main(["--data-dir", str(tmp_path / "data"), *args], env=env, home=tmp_path)
    return code, capsys.readouterr()


@pytest.fixture
def scanned(tmp_path, capsys):
    root = tmp_path / ".claude"
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    layout(root, [assistant("m1", "r1", 4000, ts=now), assistant("m2", "r2", 4000, ts=now)])
    env = {"CLAUDE_CONFIG_DIR": str(root)}
    run(["scan"], tmp_path, env, capsys)
    return tmp_path, env


def _config(tmp_path, text):
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "data" / "config.toml").write_text(text, encoding="utf-8")


def test_cli_without_a_budget_explains_how_to_set_one(scanned, capsys):
    tmp, env = scanned
    code, out = run(["budget"], tmp, env, capsys)
    assert code == EXIT_NO_DATA and "[budget]" in out.out and "daily_usd" in out.out


def test_cli_reports_and_check_exits_6_when_exceeded(scanned, capsys):
    tmp, env = scanned
    _config(tmp, "[budget]\ndaily_usd = 0.000001\nmonthly_usd = 1000\n")
    code, out = run(["budget"], tmp, env, capsys)
    assert code == EXIT_OK
    assert "bugun" in out.out and "EXCEEDED" in out.out and "ay sonu ~" in out.out
    code, out = run(["budget", "--check"], tmp, env, capsys)
    assert code == EXIT_BUDGET
    code, out = run(["--json", "budget"], tmp, env, capsys)
    doc = json.loads(out.out)
    assert [b["period"] for b in doc["budgets"]] == ["day", "month"]
    assert doc["budgets"][0]["state"] == "exceeded"
    assert doc["budgets"][1]["projected"]["evidence_class"] == "predicted"


def test_cli_check_passes_within_budget(scanned, capsys):
    tmp, env = scanned
    _config(tmp, "[budget]\ndaily_usd = 1000\n")
    code, out = run(["budget", "--check"], tmp, env, capsys)
    assert code == EXIT_OK and "ok" in out.out


def test_cli_alerts_raise_the_budget_alert(scanned, capsys):
    tmp, env = scanned
    _config(tmp, "[budget]\ndaily_usd = 0.000001\n")
    code, out = run(["--json", "alerts", "--dry-run"], tmp, env, capsys)
    doc = json.loads(out.out)
    assert any(a["rule_id"] == "budget.exceeded" for a in doc["raised_now"])
