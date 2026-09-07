import json
import threading
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, HTTPServer

from cci.alerts import AlertEngine, AlertInputs, evaluate_rules, send_webhook
from cci.analytics.anomaly import Anomaly
from cci.analytics.diagnostics import LoopFingerprint, SessionDiagnostics
from cci.config import AlertConfig, load_config
from cci.model import AccountRef, Evidence, Figure, QuotaSnapshot, QuotaWindow

NOW = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
ACC = AccountRef(provider="anthropic", account_key="acc")
H5 = 5 * 3600


def quota(util_5h, util_7d=0.1, remaining_s=H5 / 2):
    return QuotaSnapshot(snapshot_id="q", provider="anthropic", account=ACC, fetched_at=NOW, source="usage_api", authoritative=True,
                         raw_hash="a" * 64, windows=(
                             QuotaWindow(kind="session_5h", duration_s=H5, utilization=util_5h, resets_at=NOW + timedelta(seconds=remaining_s)),
                             QuotaWindow(kind="weekly_all", duration_s=7 * 86400, utilization=util_7d, resets_at=NOW + timedelta(days=3))))


def diag(session="s1", loops=0, context=None, cost=None):
    lp = tuple(LoopFingerprint(tool_name="Bash", fingerprint="Bash|1|0|err", count=4, first_index=0, last_index=3, severity="high") for _ in range(loops))
    from cci.analytics.diagnostics import ContextUtilization
    ctx = ContextUtilization(used_pct=context, risk="critical" if context >= 85 else "warn" if context >= 70 else "ok") if context else None
    return SessionDiagnostics(session_id=session, requests=3, errors=0, retry_events=0, error_rate=0, tool_calls=4, tool_failures=0,
                              tool_timeouts=0, loops=lp, compactions=0, context=ctx, cost=cost, health=90, attention="ok")


def test_rules_quota_threshold_pace_and_forecast_basis():
    cfg = AlertConfig()
    alerts = evaluate_rules(AlertInputs(quota=quota(0.92, remaining_s=3 * 3600)), NOW, cfg)
    rules = {a.rule_id: a for a in alerts}
    assert rules["quota.threshold"].severity == "critical" and rules["quota.threshold"].basis == "certain"
    assert "quota.pace" in rules and rules["quota.pace"].subject.id == "session_5h"
    assert all("\n" not in a.message and a.evidence for a in alerts)


def test_rules_session_loop_context_cost_and_anomalies():
    cfg = AlertConfig()
    inp = AlertInputs(diagnostics=[diag(loops=1, context=90, cost=Figure.observed(1_500_000_000, "nanoUSD"))],
                      anomalies=[Anomaly(kind="retry.storm", severity="critical", subject_kind="session", subject_id="s1", message="6 hata",
                                         evidence=(Evidence(metric="errors_10m", value=Decimal(6), evidence_class="observed"),))],
                      collector_health={"transcript": {"status": "down", "down_since_s": 900, "error_class": "no_config_dir"}})
    rules = {a.rule_id: a for a in evaluate_rules(inp, NOW, cfg)}
    assert {"session.loop", "session.context", "session.cost", "session.retry_storm", "collector.down"} <= set(rules)
    assert rules["session.cost"].severity == "info" and rules["collector.down"].message.startswith("toplayici transcript 15 dk")


def test_engine_cooldown_escalation_resolution_and_storm_limit():
    cfg = AlertConfig(cooldown_s=1800, storm_limit_per_minute=2)
    eng = AlertEngine(cfg)
    q = lambda u: quota(u, remaining_s=1800)  # reset'e 30 dk: pace kurali (reset > 1 sa) devreye girmez
    raised, envs = eng.run(AlertInputs(quota=q(0.75)), NOW)
    assert [a.rule_id for a in raised] == ["quota.threshold"] and envs[0].type == "alert.raised"
    raised2, envs2 = eng.run(AlertInputs(quota=q(0.76)), NOW + timedelta(minutes=5))
    assert raised2 == [] and eng.suppressed == [("quota.threshold|quota_window|session_5h", "cooldown")] and envs2 == []
    raised3, _ = eng.run(AlertInputs(quota=q(0.95)), NOW + timedelta(minutes=6))  # yukselme cooldown'i kirar
    assert len(raised3) == 1 and raised3[0].severity == "critical"
    raised4, envs4 = eng.run(AlertInputs(quota=q(0.10)), NOW + timedelta(minutes=7))
    assert raised4 == [] and [e.type for e in envs4] == ["alert.resolved"] and eng.snapshot_alerts() == []
    # firtina: 3 warning aday, limit 2 (critical sinira takilmaz)
    many = AlertInputs(diagnostics=[diag(session=f"s{i}", loops=1) for i in range(3)],
                       anomalies=[Anomaly(kind="retry.storm", severity="critical", subject_kind="session", subject_id="s9", message="x")])
    raised5, _ = eng.run(many, NOW + timedelta(hours=2))
    assert len(raised5) == 3 and raised5[0].severity == "critical" and ("session.loop|session|s2", "storm_limit") in eng.suppressed


def test_quiet_hours_suppress_non_critical_and_state_reload():
    cfg = AlertConfig(quiet_hours=(23, 7))
    eng = AlertEngine(cfg)
    night = NOW.replace(hour=1)
    raised, _ = eng.run(AlertInputs(quota=quota(0.75)), NOW, now_local=night)
    assert raised == [] and eng.suppressed[0][1] == "quiet_hours"
    raised, envs = eng.run(AlertInputs(quota=quota(0.95)), NOW, now_local=night)
    assert len(raised) == 1  # critical sessiz saatte de gecer
    eng2 = AlertEngine(AlertConfig())
    eng2.load_state(envs)  # depodan yeniden kurma: cooldown + aktif uyari geri gelir
    assert eng2.last_raised and list(eng2.active.values())[0].rule_id == "quota.threshold"
    assert eng2.snapshot_alerts()[0]["severity"] == "critical"


def test_webhook_only_loopback_and_delivers_json():
    received = []

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            received.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            self.send_response(204); self.end_headers()

        def log_message(self, *a):
            return

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        alerts = evaluate_rules(AlertInputs(quota=quota(0.95)), NOW, AlertConfig())
        assert send_webhook(f"http://127.0.0.1:{srv.server_address[1]}/hook", alerts) is True
        assert received[0][0]["rule_id"] == "quota.threshold" and "message" in received[0][0]
        assert send_webhook("http://example.com/hook", alerts) is False
    finally:
        srv.shutdown(); srv.server_close()


def test_config_defaults_and_loopback_webhook_rule(tmp_path):
    p = tmp_path / "config.toml"
    assert load_config(p).alerts.quota_warning_pct == 70.0
    p.write_text('retention_days = 45\n[alerts]\nquota_warning_pct = 60\nquiet_hours = [22, 8]\nwebhook_url = "http://example.com/x"\n', encoding="utf-8")
    cfg = load_config(p)
    assert cfg.retention_days == 45 and cfg.alerts.quota_warning_pct == 60 and cfg.alerts.quiet_hours == (22, 8)
    assert cfg.alerts.webhook_url is None  # dis host reddedildi
    p.write_text('[alerts]\nwebhook_url = "http://127.0.0.1:9999/hook"\n', encoding="utf-8")
    assert load_config(p).alerts.webhook_url == "http://127.0.0.1:9999/hook"
