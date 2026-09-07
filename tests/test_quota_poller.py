import json
import os
from datetime import UTC, datetime, timedelta

import pytest

from cci.adapters.claude_code.quota_map import QuotaParseError, parse_usage_response
from cci.collectors.credentials import (Credential, CredentialError, load_credential, parse_credential,
                                        sanitize_error)
from cci.collectors.quota import (DEFAULT_RETRY_AFTER_S, MAX_BACKOFF_S, MIN_INTERVAL_S, FetchResult,
                                  QuotaPoller)
from cci.model import AccountRef

NOW = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
ACC = AccountRef(provider="anthropic", account_key="acc-uuid-1")

USAGE_BODY = {
    "five_hour": {"utilization": 72.0, "resets_at": "2026-09-07T15:00:00Z"},
    "seven_day": {"utilization": 84.5, "resets_at": "2026-09-10T19:00:00Z"},
    "limits": [
        {"kind": "session", "group": "session", "percent": 72, "severity": "warning",
         "resets_at": "2026-09-07T15:00:00Z", "is_active": True},
        {"kind": "weekly_all", "group": "weekly", "percent": 84.5, "severity": "warning",
         "resets_at": "2026-09-10T19:00:00Z", "is_active": True},
        {"kind": "weekly_scoped", "group": "weekly", "percent": 40, "severity": "normal",
         "resets_at": "2026-09-10T19:00:00Z", "scope": {"model": {"display_name": "Opus"}}, "is_active": True},
    ],
    "spend": {"used": 12.5, "limit": 100},
    "extra_usage": {"enabled": False},
    "nimbus_quill": {"x": 1}, "tangelo": None, "omelette_prime": 3,
}


def write_creds(path, token="sk-ant-oat01-SECRETTOKEN", expires_in_ms=3_600_000):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"claudeAiOauth": {"accessToken": token,
                                                  "expiresAt": int(NOW.timestamp() * 1000) + expires_in_ms,
                                                  "subscriptionType": "max", "rateLimitTier": "default_max_5x"}}),
                    encoding="utf-8")
    if os.name != "nt":
        path.chmod(0o600)
    return path


def ok(body=USAGE_BODY, status=200, headers=None):
    return FetchResult(status, headers or {}, json.dumps(body).encode("utf-8"))


# ---------------------------------------------------------------- parse
def test_parse_prefers_limits_and_drops_codename_noise():
    snap, unknown = parse_usage_response(USAGE_BODY, account=ACC, fetched_at=NOW)
    assert snap.authoritative and snap.storable
    assert snap.window("session_5h").utilization == 0.72
    assert snap.window("weekly_all").utilization == 0.845
    assert snap.window("weekly_scoped", "Opus").utilization == 0.40
    assert snap.window("session_5h").severity == "warning"
    assert snap.spend.used.render() == "$12.50"
    assert unknown == ["nimbus_quill", "omelette_prime", "tangelo"]
    assert "nimbus" not in json.dumps(snap.model_dump(mode="json"))


def test_parse_falls_back_to_legacy_fields():
    body = {"five_hour": {"utilization": 10, "resets_at": "2026-09-07T15:00:00Z"},
            "seven_day": {"utilization": 20, "resets_at": "2026-09-10T19:00:00Z"},
            "seven_day_opus": {"utilization": 5, "resets_at": "2026-09-10T19:00:00Z"}}
    snap, _ = parse_usage_response(body, account=ACC, fetched_at=NOW)
    assert snap.authoritative
    assert snap.window("weekly_scoped", "Opus").utilization == 0.05


def test_parse_unknown_kind_is_unclassified_not_authoritative():
    body = {"limits": [{"kind": "lunar_cycle", "percent": 3, "resets_at": "2026-09-30T00:00:00Z"}]}
    snap, _ = parse_usage_response(body, account=ACC, fetched_at=NOW)
    assert not snap.authoritative and snap.windows[0].kind == "unclassified"


def test_parse_rejects_out_of_scale_utilization():
    with pytest.raises(QuotaParseError):
        parse_usage_response({"five_hour": {"utilization": 250}}, account=ACC, fetched_at=NOW)


# ---------------------------------------------------------------- credentials
def test_credential_repr_never_shows_token():
    c = parse_credential(json.dumps({"claudeAiOauth": {"accessToken": "sk-ant-SECRET", "expiresAt": 1}}))
    assert "SECRET" not in repr(c) and "SECRET" not in str(c) and c.access_token == "sk-ant-SECRET"
    assert c.is_expired(now_ms=1_000_000)


def test_sanitize_error_redacts_token_shapes():
    msg = "failed Bearer abc.def sk-ant-oat01-xyz ya29.aaa ghp_bbb eyJhbGciOiJIUzI1NiJ9.x"
    out = sanitize_error(msg)
    for secret in ("abc.def", "sk-ant-oat01-xyz", "ya29.aaa", "ghp_bbb", "eyJhbGci"):
        assert secret not in out
    assert out.count("[REDACTED]") >= 5


def test_load_credential_missing_returns_none(tmp_path):
    assert load_credential(tmp_path / "nope.json") is None


def test_load_credential_refuses_symlink(tmp_path):
    real = write_creds(tmp_path / "real.json")
    link = tmp_path / "link.json"
    try:
        link.symlink_to(real)
    except (OSError, NotImplementedError):
        pytest.skip("symlink olusturulamiyor")
    with pytest.raises(CredentialError):
        load_credential(link)


def test_load_credential_refuses_oversized(tmp_path):
    p = tmp_path / "big.json"
    p.write_text("{" + " " * 70_000 + "}", encoding="utf-8")
    with pytest.raises(CredentialError):
        load_credential(p)


@pytest.mark.skipif(os.name == "nt", reason="POSIX mod bitleri")
def test_load_credential_refuses_broad_permissions(tmp_path):
    p = write_creds(tmp_path / "c.json")
    p.chmod(0o644)
    with pytest.raises(CredentialError):
        load_credential(p)


# ---------------------------------------------------------------- poller policy
class FakeFetch:
    def __init__(self, *results):
        self.results = list(results)
        self.calls = []

    def __call__(self, token):
        self.calls.append(token)
        r = self.results.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def make_poller(tmp_path, fetch, **kw):
    creds = write_creds(tmp_path / ".claude" / ".credentials.json")
    return QuotaPoller(creds, fetch=fetch, account=ACC, now=lambda: NOW, **kw)


def test_poll_success_resets_backoff_and_uses_interval(tmp_path):
    fetch = FakeFetch(ok())
    p = make_poller(tmp_path, fetch, interval_s=10)  # 10 -> MIN_INTERVAL'e cekilir
    r = p.poll_once()
    assert r.snapshot is not None and r.health.status == "ok" and r.next_in_s == MIN_INTERVAL_S
    assert r.unknown_keys == ("nimbus_quill", "omelette_prime", "tangelo")
    assert fetch.calls == ["sk-ant-oat01-SECRETTOKEN"]
    assert "SECRET" not in r.health.detail


def test_poll_429_honours_retry_after_with_floor(tmp_path):
    p = make_poller(tmp_path, FakeFetch(ok(status=429, headers={"retry-after": "5"})))
    r = p.poll_once()
    assert r.snapshot is None and r.health.error_class == "rate_limited" and r.next_in_s == 60
    p2 = make_poller(tmp_path, FakeFetch(FetchResult(429, {}, b'{"retry_after": 420}')))
    assert p2.poll_once().next_in_s == 420
    p3 = make_poller(tmp_path, FakeFetch(FetchResult(429, {}, b"")))
    assert p3.poll_once().next_in_s == DEFAULT_RETRY_AFTER_S


def test_poll_401_rereads_once_then_degrades_without_refreshing(tmp_path):
    fetch = FakeFetch(ok(status=401), ok())
    p = make_poller(tmp_path, fetch)
    r = p.poll_once()
    assert r.health.error_class == "unauthorized" and len(fetch.calls) == 1  # dosya degismedi -> tekrar yok
    # dosya degisti -> bir kez daha dener
    fetch2 = FakeFetch(ok(status=401), ok())
    creds = write_creds(tmp_path / "x" / ".credentials.json", token="sk-ant-OLD")
    p2 = QuotaPoller(creds, fetch=fetch2, account=ACC, now=lambda: NOW)
    orig = p2._credential
    state = {"n": 0}

    def rotating():
        state["n"] += 1
        if state["n"] == 2:
            write_creds(creds, token="sk-ant-NEW")
        return orig()

    p2._credential = rotating
    r2 = p2.poll_once()
    assert r2.health.status == "ok" and fetch2.calls == ["sk-ant-OLD", "sk-ant-NEW"]


def test_poll_network_errors_back_off_exponentially_to_cap(tmp_path):
    fetch = FakeFetch(*([ConnectionError("boom Bearer sk-ant-oat01-SECRETTOKEN")] * 5))
    p = make_poller(tmp_path, fetch)
    waits = [p.poll_once().next_in_s for _ in range(5)]
    assert waits == [360, 720, 900, 900, 900] and MAX_BACKOFF_S == 900
    assert "SECRET" not in p.last_health.detail and p.last_health.error_class == "network"


def test_poll_other_4xx_is_terminal(tmp_path):
    p = make_poller(tmp_path, FakeFetch(ok(status=403)))
    r = p.poll_once()
    assert r.health.status == "down" and r.health.error_class == "http_403" and r.next_in_s == MAX_BACKOFF_S


def test_poll_expired_token_never_calls_and_never_refreshes(tmp_path):
    fetch = FakeFetch(ok())
    creds = write_creds(tmp_path / ".claude" / ".credentials.json", expires_in_ms=-1)
    p = QuotaPoller(creds, fetch=fetch, account=ACC, now=lambda: NOW)
    r = p.poll_once()
    assert r.health.error_class == "expired" and fetch.calls == []


def test_poll_without_credentials_is_down(tmp_path):
    p = QuotaPoller(tmp_path / "missing.json", fetch=FakeFetch(ok()), now=lambda: NOW)
    r = p.poll_once()
    assert r.health.status == "down" and r.health.error_class == "no_credentials"


def test_poll_malformed_body_degrades(tmp_path):
    p = make_poller(tmp_path, FakeFetch(FetchResult(200, {}, b"<html>")))
    assert p.poll_once().health.error_class == "malformed_response"


def test_snapshot_without_account_is_live_only(tmp_path):
    creds = write_creds(tmp_path / ".claude" / ".credentials.json")
    p = QuotaPoller(creds, fetch=FakeFetch(ok()), account=None, now=lambda: NOW)
    r = p.poll_once()
    assert r.snapshot is not None and not r.snapshot.storable
