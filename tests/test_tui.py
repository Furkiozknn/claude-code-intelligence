import json

from cci.cli import EXIT_OK, main
from cci.surfaces.tui import render

SNAP = {"generated_at": "2026-09-07T12:00:00+00:00", "attention": "loops",
        "quota": {"windows": [{"kind": "session_5h", "utilization_pct": 72.0, "badge": "●", "pace": {"delta_pct": 4.0},
                               "forecast": {"verdict": "watch", "projected_at_reset": {"median_pct": 96.0}}},
                              {"kind": "weekly_all", "utilization_pct": None, "badge": ""}]},
        "today": {"requests": 12, "tokens": {"input_total": 123456, "output": 789}, "cost": {"text": "$4.20", "released": True},
                  "models": [{"display": "Opus 5", "requests": 12, "cost": {"text": "$4.20"}}]},
        "alerts": [{"severity": "warning", "rule_id": "session.loop", "message": "Bash x4"}]}


def test_render_fits_and_shows_everything():
    out = render(SNAP)
    lines = out.splitlines()
    assert all(len(l) <= 100 for l in lines) and len(lines) <= 24
    assert "session_5h" in out and "72.0%●" in out and "⇡4%" in out and "~%96 (watch)" in out
    assert "--" in out  # utilization yok
    assert "$4.20" in out and "DIKKAT  loops" in out and "session.loop" in out
    assert render(None).startswith("CCI — snapshot yok")


def test_tui_once_via_cli(tmp_path, capsys):
    (tmp_path / "d" / "state").mkdir(parents=True)
    (tmp_path / "d" / "state" / "latest.json").write_text(json.dumps(SNAP), encoding="utf-8")
    assert main(["--data-dir", str(tmp_path / "d"), "tui", "--once"], env={}, home=tmp_path) == EXIT_OK
    assert "CLAUDE CODE INTELLIGENCE" in capsys.readouterr().out
