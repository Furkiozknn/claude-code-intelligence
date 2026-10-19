"""`cci projects`: usage by working directory, with the conservation law."""

import hashlib
import json
from datetime import UTC, datetime

import pytest

from cci.analytics.summaries import ConservationError, summarize_projects
from cci.cli import EXIT_NO_DATA, EXIT_OK, main, project_labels
from cci.model.usage import UsageRecord
from tests.test_pipeline import assistant, layout


def run(args, tmp_path, env, capsys):
    code = main(["--data-dir", str(tmp_path / "data"), *args], env=env, home=tmp_path)
    return code, capsys.readouterr()


def _rec(msg, req, out, cwd, session="sess-1"):
    r = assistant(msg, req, out, ts=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z"))
    r["cwd"] = cwd
    r["sessionId"] = session
    return r


@pytest.fixture
def two_projects(tmp_path):
    root = tmp_path / ".claude"
    layout(root, [
        _rec("m1", "r1", 400, "D:/work/big", "s-a"),
        _rec("m2", "r2", 400, "D:/work/big", "s-b"),
        _rec("m3", "r3", 10, "D:/work/small", "s-c"),
    ])
    return tmp_path, {"CLAUDE_CONFIG_DIR": str(root)}


def _key(path):
    return hashlib.sha256(path.encode("utf-8")).hexdigest()[:16]


def test_projects_add_up_and_rank_by_cost(two_projects, capsys):
    tmp, env = two_projects
    run(["scan"], tmp, env, capsys)
    code, out = run(["--json", "projects", "--strict"], tmp, env, capsys)
    assert code == EXIT_OK
    doc = json.loads(out.out)
    assert doc["conservation"]["ok"] is True
    keys = [p["project_key"] for p in doc["projects"]]
    assert keys == [_key("D:/work/big"), _key("D:/work/small")]
    big, small = doc["projects"]
    assert big["totals"]["requests"] == 2 and big["sessions"] == 2
    assert small["totals"]["requests"] == 1 and small["sessions"] == 1
    assert doc["totals"]["requests"] == 3
    assert doc["share_basis"] in ("cost", "tokens")
    assert doc["labels"] == {}
    # No path anywhere in the output: only hashes.
    assert "D:/work" not in out.out


def test_projects_text_labels_only_paths_given_on_the_command_line(two_projects, capsys):
    tmp, env = two_projects
    run(["scan"], tmp, env, capsys)
    code, out = run(["projects", "--name", "D:/work/small"], tmp, env, capsys)
    assert code == EXIT_OK
    lines = out.out.splitlines()
    assert lines[0].startswith("tum kayitlar") and "proje 2" in lines[0]
    small_line = next(l for l in lines if _key("D:/work/small")[:8] in l)
    big_line = next(l for l in lines if _key("D:/work/big")[:8] in l)
    assert small_line.rstrip().endswith("D:/work/small")
    assert "D:/work/big" not in big_line
    assert "%" in big_line and "oturum" in big_line


def test_projects_without_data_is_exit_4(tmp_path, capsys):
    code, out = run(["projects"], tmp_path, {"CLAUDE_CONFIG_DIR": str(tmp_path / "none")}, capsys)
    assert code == EXIT_NO_DATA


def test_projects_limit_and_hint(two_projects, capsys):
    tmp, env = two_projects
    run(["scan"], tmp, env, capsys)
    code, out = run(["projects", "--limit", "1"], tmp, env, capsys)
    assert "1 proje daha (--limit)" in out.out
    assert "--name YOL" in out.out


def test_label_variants_cover_slash_direction_and_trailing_separator():
    labels = project_labels(["D:/work/app/"])
    assert _key("D:/work/app") in labels
    assert _key("D:\\work\\app") in labels
    assert all(v == "D:/work/app/" for v in labels.values())


def test_summarize_projects_unknown_bucket_and_strict(two_projects, capsys):
    tmp, env = two_projects
    from cci.cli import Context
    from pathlib import Path
    run(["scan"], tmp, env, capsys)
    ctx = Context(tmp / "data", as_json=True, env=env, home=tmp)
    try:
        records = ctx.pipe.records()
        no_workspace = records[0].model_copy(update={"workspace": None})
        report = summarize_projects([no_workspace, *records[1:]])
        assert "unknown" in [p.project_key for p in report.projects]
        assert report.conservation.ok
        assert report.totals.requests == sum(p.totals.requests for p in report.projects)
    finally:
        ctx.close()


def test_conservation_violation_is_reported_and_raises_with_strict(monkeypatch, two_projects, capsys):
    tmp, env = two_projects
    run(["scan"], tmp, env, capsys)
    import cci.analytics.summaries as summaries

    real = summaries._totals

    def lying_totals(records):
        t = real(records)
        # Inflate the period total only when called for the full set.
        return t.model_copy(update={"requests": t.requests + 1}) if len(records) == 3 else t

    monkeypatch.setattr(summaries, "_totals", lying_totals)
    from cci.cli import Context
    ctx = Context(tmp / "data", as_json=True, env=env, home=tmp)
    try:
        records = ctx.pipe.records()
        assert summarize_projects(records).conservation.ok is False
        with pytest.raises(ConservationError):
            summarize_projects(records, strict=True)
    finally:
        ctx.close()
