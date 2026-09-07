import http.client
import json

import pytest

from cci.api.http import CSP, ApiServer, load_or_create_token
from cci.api.snapshot import write_snapshot
from cci.cli import EXIT_OK, main, statusline_command
from cci.surfaces import widget_lines
from tests.test_pipeline import assistant, layout


@pytest.fixture
def api(tmp_path):
    snap_path = tmp_path / "state" / "latest.json"
    write_snapshot(snap_path, {"schema_version": 1, "generated_at": "2026-09-07T12:00:00+00:00", "attention": "ok",
                               "quota": {"placeholder": "--", "windows": []}, "today": None, "alerts": [], "health": {},
                               "next_display_change_at": "2026-09-07T12:01:00+00:00"})
    token = load_or_create_token(tmp_path / "api_token")
    calls = []

    def data(name, ident):
        calls.append((name, ident))
        if name == "today":
            return [{"requests": 3}]
        if name == "session":
            return {"session": {"id": ident}} if ident == "abc" else None
        if name == "doctor":
            raise RuntimeError("gizli detay")
        return {"name": name}

    server = ApiServer(snapshot_path=snap_path, token=token, data=data, port=0).start()
    server._calls = calls  # type: ignore[attr-defined]
    yield server, token
    server.stop()


def get(server, path, token=None):
    host, port = server.address
    conn = http.client.HTTPConnection(host, port, timeout=5)
    conn.request("GET", path, headers={"X-CCI-Token": token} if token else {})
    resp = conn.getresponse()
    body = resp.read()
    headers = dict(resp.getheaders())
    conn.close()
    return resp.status, body, headers


def test_token_is_created_once_and_private(tmp_path):
    p = tmp_path / "t"
    a = load_or_create_token(p)
    assert len(a) >= 32 and load_or_create_token(p) == a


def test_loopback_only():
    with pytest.raises(ValueError):
        ApiServer(snapshot_path=None, token="x" * 32, data=lambda n, i: None, host="0.0.0.0")


def test_health_and_dashboard_need_no_token_but_carry_csp(api):
    server, token = api
    status, body, headers = get(server, "/health")
    assert status == 200 and json.loads(body)["status"] == "ok" and headers["Content-Security-Policy"] == CSP
    status, body, headers = get(server, "/")
    assert status == 200 and b"CLAUDE CODE INTELLIGENCE" in body and "text/html" in headers["Content-Type"]
    assert b"cdn" not in body.lower() and b"http://" not in body  # dis kaynak yok


def test_api_requires_token(api):
    server, token = api
    assert get(server, "/api/v1/snapshot")[0] == 401
    assert get(server, "/api/v1/snapshot", token="yanlis")[0] == 401
    status, body, _ = get(server, "/api/v1/snapshot", token=token)
    assert status == 200 and json.loads(body)["attention"] == "ok"
    status, body, _ = get(server, f"/api/v1/snapshot?token={token}")
    assert status == 200 and server.unauthorized == 2


def test_data_routes_and_error_hiding(api):
    server, token = api
    status, body, _ = get(server, "/api/v1/today", token=token)
    assert status == 200 and json.loads(body) == [{"requests": 3}]
    assert get(server, "/api/v1/session/abc", token=token)[0] == 200
    assert get(server, "/api/v1/session/yok", token=token)[0] == 404
    status, body, _ = get(server, "/api/v1/doctor", token=token)
    assert status == 500 and "gizli" not in body.decode() and json.loads(body)["error"] == "RuntimeError"
    assert get(server, "/api/v1/nope", token=token)[0] == 404
    assert ("today", None) in server._calls


def test_cli_serve_once_and_run_with_api(tmp_path, capsys):
    root = tmp_path / ".claude"
    layout(root, [assistant("msg_1", "req_1", 40)])
    env = {"CLAUDE_CONFIG_DIR": str(root)}
    code = main(["--data-dir", str(tmp_path / "data"), "serve", "--port", "0", "--once"], env=env, home=tmp_path)
    err = capsys.readouterr().err
    assert code == EXIT_OK and "cci pano: http://127.0.0.1:" in err and "token=" in err
    assert (tmp_path / "data" / "api_token").exists()
    code = main(["--data-dir", str(tmp_path / "data"), "run", "--once", "--otlp-port", "0", "--api-port", "0", "--no-quota"], env=env, home=tmp_path)
    assert code == EXIT_OK and "cci pano" in capsys.readouterr().err


def test_setup_statusline_dry_run_and_write(tmp_path, capsys):
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"env": {"A": "1"}}), encoding="utf-8")
    code = main(["--data-dir", str(tmp_path / "d"), "setup", "statusline", "--settings", str(settings)], env={}, home=tmp_path)
    out = capsys.readouterr().out
    assert code == EXIT_OK and "statusLine" in out and "-m cci.cli statusline" in out
    assert "statusLine" not in json.loads(settings.read_text(encoding="utf-8"))
    code = main(["--data-dir", str(tmp_path / "d"), "setup", "statusline", "--settings", str(settings), "--write"], env={}, home=tmp_path)
    doc = json.loads(settings.read_text(encoding="utf-8"))
    assert code == EXIT_OK and doc["statusLine"] == {"type": "command", "command": statusline_command()} and doc["env"] == {"A": "1"}
    assert list(tmp_path.glob("settings.json.bak-*"))


def test_widget_lines_and_cli_print(tmp_path, capsys):
    snap = {"quota": {"windows": [{"kind": "session_5h", "utilization_pct": 72.0, "badge": "●", "resets_at": "2026-09-07T15:00:00+00:00",
                                   "pace": {"delta_pct": 4.0, "eta_s": 1800}}]},
            "today": {"cost": {"text": "$1.20", "released": True}, "requests": 7, "tokens": {"input_total": 1234, "output": 56}},
            "attention": "loops", "alerts": [{"rule_id": "session.loop", "message": "Bash x4"}]}
    assert widget_lines(snap) == ["5h 72%●⇡4 · 7d --", "$1.20≈ · loops"]
    detailed = widget_lines(snap, detailed=True)
    assert detailed[2].startswith("session_5h: reset 09-07 15:00 · ~30 dk") and detailed[3] == "istek 7 · token 1,234/56"
    assert detailed[4] == "! session.loop: Bash x4"
    assert widget_lines(None) == ["cci --", "snapshot yok"]
    code = main(["--data-dir", str(tmp_path / "d"), "widget", "--print"], env={}, home=tmp_path)
    assert code == EXIT_OK and "cci --" in capsys.readouterr().out
