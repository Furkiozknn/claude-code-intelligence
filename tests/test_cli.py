import json
from datetime import UTC, datetime

import pytest

from cci.cli import EXIT_NO_CREDENTIALS, EXIT_NO_DATA, EXIT_OK, main, statusline_text
from tests.test_pipeline import assistant, layout


def run(args, tmp_path, env=None, capsys=None):
    code = main(["--data-dir", str(tmp_path / "data"), *args], env=env or {}, home=tmp_path)
    out = capsys.readouterr() if capsys else None
    return code, out


@pytest.fixture
def workspace(tmp_path):
    root = tmp_path / ".claude"
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    layout(root, [assistant("msg_1", "req_1", 40, ts=now), assistant("msg_2", "req_2", 20, ts=now)])
    return tmp_path, {"CLAUDE_CONFIG_DIR": str(root)}


def test_scan_then_today_and_sessions(workspace, capsys):
    tmp, env = workspace
    code, out = run(["scan"], tmp, env, capsys)
    assert code == EXIT_OK and "2 yeni olay" in out.out
    code, out = run(["--json", "today", "--strict"], tmp, env, capsys)
    assert code == EXIT_OK
    doc = json.loads(out.out)
    assert doc["days"][0]["totals"]["requests"] == 2 and doc["days"][0]["conservation"]["ok"] is True
    code, out = run(["sessions"], tmp, env, capsys)
    assert code == EXIT_OK and "istek    2" in out.out
    code, out = run(["daily"], tmp, env, capsys)
    assert code == EXIT_OK and "≈" in out.out and "gizli" not in out.out


def test_session_diagnostics_via_cli(workspace, capsys):
    from datetime import UTC, datetime
    from cci.events import Envelope, SourceRef
    from cci.store import EventStore
    tmp, env = workspace
    run(["scan"], tmp, env, capsys)
    code, out = run(["session", "sess-1"], tmp, env, capsys)
    assert code == EXIT_OK and "saglik 100/100" in out.out and "dikkat: ok" in out.out
    # OTLP'den gelmis gibi 4 ardisik basarisiz Bash cagrisi ekle -> dongu + hata
    src = SourceRef(collector="otlp", instance_id="otlp:claude-code", collector_version="0.0.1", schema_version=1)
    with EventStore(tmp / "data" / "events.db") as store:
        for i in range(4):
            store.append(Envelope(type="tool.call", ts=datetime.now(UTC), source=src, provider="anthropic", session_id="sess-1",
                                  payload={"tool_name": "Bash", "tool_use_id": f"t{i}", "success": False, "duration_ms": 10,
                                           "input_size_bytes": 77, "error_type": "exit_code"}))
    code, out = run(["--json", "session", "sess"], tmp, env, capsys)
    doc = json.loads(out.out)
    assert code == EXIT_OK and doc["diagnostics"]["attention"] == "failures" and len(doc["diagnostics"]["loops"]) == 1
    code, out = run(["sessions"], tmp, env, capsys)
    assert "failures" in out.out and "saglik" in out.out
    code, out = run(["snapshot"], tmp, env, capsys)
    snap = json.loads((tmp / "data" / "state" / "latest.json").read_text(encoding="utf-8"))
    assert snap["attention"] == "failures"
    code, out = run(["session", "yok"], tmp, env, capsys)
    assert code == EXIT_NO_DATA


def test_quota_forecast_and_backtest_via_cli(workspace, capsys):
    from datetime import UTC, datetime, timedelta
    from cci.events import Envelope, SourceRef
    from cci.store import EventStore
    from tests.test_forecast import history
    tmp, env = workspace
    snaps, now = history(6)
    shift = datetime.now(UTC) - now  # gecmisi simdiye tasi (mevcut dongu acik kalsin)
    src = SourceRef(collector="quota", instance_id="usage_api", collector_version="0.0.1", schema_version=1)
    with EventStore(tmp / "data" / "events.db") as store:
        for s in snaps:
            moved = s.model_copy(update={"fetched_at": s.fetched_at + shift,
                                         "windows": tuple(w.model_copy(update={"resets_at": w.resets_at + shift}) for w in s.windows)})
            store.append(Envelope(type="quota.snapshot", ts=moved.fetched_at, source=src, provider="anthropic",
                                  account_key="acc", privacy_class="sensitive", payload=moved.model_dump(mode="json")))
    code, out = run(["quota", "--forecast"], tmp, env, capsys)
    assert code == EXIT_OK and "tahmin session_5h:" in out.out and "dongu" in out.out
    code, out = run(["--json", "quota", "--backtest"], tmp, env, capsys)
    doc = json.loads(out.out)
    assert code == EXIT_OK and doc["backtest"]["session_5h"]["cycles"] == 6 and doc["backtest"]["session_5h"]["best"]
    code, out = run(["snapshot"], tmp, env, capsys)
    snap = json.loads((tmp / "data" / "state" / "latest.json").read_text(encoding="utf-8"))
    w = [w for w in snap["quota"]["windows"] if w["kind"] == "session_5h"][0]
    assert w["forecast"]["verdict"] in ("enough", "watch", "at_risk", "surplus") and w["forecast"]["badge"] == "~"


def test_alerts_cli_raises_persists_and_shows_history(workspace, capsys):
    from datetime import UTC, datetime, timedelta
    from cci.adapters.claude_code.quota_map import parse_usage_response
    from cci.events import Envelope, SourceRef
    from cci.model import AccountRef
    from cci.store import EventStore
    tmp, env = workspace
    run(["scan"], tmp, env, capsys)
    now = datetime.now(UTC)
    body = {"five_hour": {"utilization": 93, "resets_at": (now + timedelta(hours=2)).isoformat()},
            "seven_day": {"utilization": 40, "resets_at": (now + timedelta(days=3)).isoformat()}}
    snap, _ = parse_usage_response(body, account=AccountRef(provider="anthropic", account_key="acc"), fetched_at=now)
    src = SourceRef(collector="quota", instance_id="usage_api", collector_version="0.0.1", schema_version=1)
    with EventStore(tmp / "data" / "events.db") as store:
        store.append(Envelope(type="quota.snapshot", ts=now, source=src, provider="anthropic", account_key="acc",
                              privacy_class="sensitive", payload=snap.model_dump(mode="json")))
    # %93 ve reset'e 2 sa: esik (critical) + pace (warning) -> 2 uyari
    code, out = run(["alerts", "--dry-run"], tmp, env, capsys)
    assert code == EXIT_OK and "quota.threshold" in out.out and "quota.pace" in out.out and "yeni: 2" in out.out
    code, out = run(["--json", "alerts"], tmp, env, capsys)
    doc = json.loads(out.out)
    assert code == EXIT_OK and doc["raised_now"][0]["rule_id"] == "quota.threshold" and doc["baseline"]["records"] == 2
    code, out = run(["alerts"], tmp, env, capsys)  # cooldown: yeni yok, aktif 2
    assert "yeni: 0" in out.out and "aktif: 2" in out.out
    code, out = run(["alerts", "--history"], tmp, env, capsys)
    assert "alert.raised" in out.out
    code, out = run(["snapshot"], tmp, env, capsys)
    snapd = json.loads((tmp / "data" / "state" / "latest.json").read_text(encoding="utf-8"))
    assert snapd["alerts"][0]["rule_id"] == "quota.threshold" and snapd["alerts"][0]["severity"] == "critical"


def test_today_without_data_exits_4(tmp_path, capsys):
    code, out = run(["today"], tmp_path, {"CLAUDE_CONFIG_DIR": str(tmp_path / "none")}, capsys)
    assert code == EXIT_NO_DATA and "veri yok" in out.out


def test_doctor_reports_paths_store_and_pricing(workspace, capsys):
    tmp, env = workspace
    run(["scan"], tmp, env, capsys)
    code, out = run(["--json", "doctor"], tmp, env, capsys)
    assert code == EXIT_OK
    doc = json.loads(out.out)
    assert doc["adapter"]["health"]["status"] == "ok" and doc["store"]["events"] == 2
    assert doc["pricing"]["models"] >= 20 and doc["account_key_known"] is False and doc["quota"] is None
    assert any(p["label"].startswith("credentials") and p["exists"] is False for p in doc["adapter"]["probe_roots"])
    code, out = run(["doctor"], tmp, env, capsys)
    assert "YOK -> kota snapshot saklanmaz" in out.out


def test_quota_without_snapshot_and_without_credentials(workspace, capsys):
    tmp, env = workspace
    code, out = run(["quota"], tmp, env, capsys)
    assert code == EXIT_NO_DATA and "--" in out.out
    code, out = run(["quota", "--poll"], tmp, env, capsys)
    assert code == EXIT_NO_CREDENTIALS and "kimlik" in out.err


def test_snapshot_and_statusline(workspace, capsys):
    tmp, env = workspace
    run(["scan"], tmp, env, capsys)
    code, out = run(["snapshot"], tmp, env, capsys)
    assert code == EXIT_OK and (tmp / "data" / "state" / "latest.json").exists()
    code, out = run(["statusline"], tmp, env, capsys)
    line = out.out.strip()
    assert code == EXIT_OK and line.startswith("5h --") and "$" in line and line.endswith("ok")
    assert len(line) <= 60


def test_statusline_text_formats_quota_and_pace():
    snap = {"quota": {"windows": [{"kind": "session_5h", "utilization_pct": 72.0, "badge": "●", "stale": False,
                                   "pace": {"delta_pct": 4.2}},
                                  {"kind": "weekly_all", "utilization_pct": 84.0, "badge": "●", "stale": True}]},
            "today": {"cost": {"text": "$18.42", "released": True}}, "attention": "ok"}
    assert statusline_text(snap) == "5h 72%● ⇡4% · 7d 84%●(eski) · $18.42≈ · ok"
    assert statusline_text(None) == "cci --"


def test_setup_otlp_dry_run_and_write_with_backup(tmp_path, capsys):
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"permissions": {"allow": ["Read"]}, "env": {"FOO": "1"}}), encoding="utf-8")
    code, out = run(["setup", "otlp", "--settings", str(settings), "--port", "4318"], tmp_path, {}, capsys)
    assert code == EXIT_OK and "--write" in out.out and "http://127.0.0.1:4318" in out.out
    assert json.loads(settings.read_text(encoding="utf-8"))["env"] == {"FOO": "1"}  # dokunulmadi
    code, out = run(["setup", "otlp", "--settings", str(settings), "--write"], tmp_path, {}, capsys)
    assert code == EXIT_OK
    doc = json.loads(settings.read_text(encoding="utf-8"))
    assert doc["permissions"] == {"allow": ["Read"]} and doc["env"]["FOO"] == "1"
    assert doc["env"]["OTEL_EXPORTER_OTLP_PROTOCOL"] == "http/json" and doc["env"]["CLAUDE_CODE_ENABLE_TELEMETRY"] == "1"
    assert list(tmp_path.glob("settings.json.bak-*"))


def test_run_once_starts_receiver_scans_and_writes_snapshot(workspace, capsys):
    tmp, env = workspace
    code, out = run(["run", "--once", "--otlp-port", "0", "--no-quota"], tmp, env, capsys)
    assert code == EXIT_OK and "ccid: OTLP http://127.0.0.1:" in out.err
    snap = json.loads((tmp / "data" / "state" / "latest.json").read_text(encoding="utf-8"))
    assert snap["today"]["requests"] == 2 and snap["health"]["scan"]["written"] == 2 and snap["health"]["otlp"] == {}
