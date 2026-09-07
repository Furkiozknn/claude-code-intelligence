from pathlib import Path

from cci.adapters import Cursor, assert_contract
from cci.adapters.claude_code import (ClaudeCodeAdapter, SCHEMA_VERIFIED_AT, config_dirs,
                                      find_transcripts)


def make_layout(root: Path, session="s1", with_journal=True):
    proj = root / "projects" / "D--proj"
    (proj).mkdir(parents=True)
    (proj / f"{session}.jsonl").write_text('{"type":"user"}\n', encoding="utf-8")
    sub = proj / session / "subagents"
    sub.mkdir(parents=True)
    (sub / "agent-a1.jsonl").write_text("{}\n", encoding="utf-8")
    wf = sub / "workflows" / "wf_1"
    wf.mkdir(parents=True)
    (wf / "agent-a2.jsonl").write_text("{}\n", encoding="utf-8")
    if with_journal:
        (wf / "journal.jsonl").write_text("{}\n", encoding="utf-8")
    return root


def test_config_dirs_from_env_comma_separated(tmp_path):
    a, b = tmp_path / "one", tmp_path / "two"
    a.mkdir(); b.mkdir()
    missing = tmp_path / "missing"
    env = {"CLAUDE_CONFIG_DIR": f"{a}, {b},{missing},{a}"}
    dirs = config_dirs(env, home=tmp_path)
    assert dirs == (a.resolve(), b.resolve())


def test_config_dirs_default_home(tmp_path):
    (tmp_path / ".claude").mkdir()
    assert config_dirs({}, home=tmp_path) == ((tmp_path / ".claude").resolve(),)


def test_find_transcripts_recursive_and_skips_journal(tmp_path):
    root = make_layout(tmp_path / ".claude")
    names = [p.name for p in find_transcripts(root)]
    assert names == ["agent-a1.jsonl", "agent-a2.jsonl", "s1.jsonl"] or set(names) == {
        "agent-a1.jsonl", "agent-a2.jsonl", "s1.jsonl"}
    assert "journal.jsonl" not in names


def test_adapter_discovers_instances_with_unique_labels(tmp_path):
    r1 = make_layout(tmp_path / "cfgA")
    r2 = make_layout(tmp_path / "cfgA2")
    adapter = ClaudeCodeAdapter(env={"CLAUDE_CONFIG_DIR": f"{r1},{r2}"}, home=tmp_path)
    assert_contract(adapter)
    insts = adapter.discover()
    assert len(insts) == 2
    assert {i.label for i in insts} == {"cfgA", "cfgA2"}
    assert all(i.schema_verified and i.verified_at == SCHEMA_VERIFIED_AT for i in insts)
    assert len({i.instance_id for i in insts}) == 2


def test_same_basename_roots_get_numbered_labels(tmp_path):
    r1 = make_layout(tmp_path / "p1" / ".claude")
    r2 = make_layout(tmp_path / "p2" / ".claude")
    adapter = ClaudeCodeAdapter(env={"CLAUDE_CONFIG_DIR": f"{r1},{r2}"}, home=tmp_path)
    labels = sorted(i.label for i in adapter.discover())
    assert labels == ["claude 1", "claude 2"]


def test_default_root_is_labelled_default_claude(tmp_path):
    make_layout(tmp_path / ".claude")
    adapter = ClaudeCodeAdapter(env={}, home=tmp_path)
    assert [i.label for i in adapter.discover()] == ["Default Claude"]


def test_health_and_probe_roots(tmp_path):
    adapter = ClaudeCodeAdapter(env={"CLAUDE_CONFIG_DIR": str(tmp_path / "nope")}, home=tmp_path)
    assert adapter.health().status == "down"
    roots = adapter.probe_roots()
    assert any(r.label == "config dir" and not r.exists for r in roots)
    empty = tmp_path / "empty"; (empty / "projects").mkdir(parents=True)
    adapter2 = ClaudeCodeAdapter(env={"CLAUDE_CONFIG_DIR": str(empty)}, home=tmp_path)
    assert adapter2.health().status == "degraded"
    make_layout(tmp_path / "full")
    adapter3 = ClaudeCodeAdapter(env={"CLAUDE_CONFIG_DIR": str(tmp_path / "full")}, home=tmp_path)
    h = adapter3.health()
    assert h.status == "ok" and "3 transcript" in h.detail
    assert adapter3.collect(adapter3.discover()[0], Cursor()).complete


def test_credentials_are_probed_but_never_read(tmp_path):
    root = make_layout(tmp_path / ".claude")
    cred = root / ".credentials.json"
    cred.write_text('{"claudeAiOauth":{"accessToken":"sk-ant-SECRET"}}', encoding="utf-8")
    adapter = ClaudeCodeAdapter(env={}, home=tmp_path)
    probe = [r for r in adapter.probe_roots() if "credentials" in r.label][0]
    assert probe.exists
    described = str(adapter.describe()) + adapter.health().detail
    assert "SECRET" not in described
