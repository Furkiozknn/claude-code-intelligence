import json
from pathlib import Path

from cci.adapters import Cursor
from cci.adapters.claude_code import ClaudeCodeAdapter
from cci.collectors import TranscriptCollector, read_new_lines, strip_content
from cci.ingest import find_forbidden_key

USAGE = {"input_tokens": 12, "output_tokens": 300, "cache_creation_input_tokens": 100,
         "cache_read_input_tokens": 5000,
         "cache_creation": {"ephemeral_5m_input_tokens": 60, "ephemeral_1h_input_tokens": 40},
         "service_tier": "standard",
         "iterations": [{"type": "advisor_message", "model": "claude-opus-5",
                         "usage": {"input_tokens": 3, "output_tokens": 4}, "content": "GIZLI"}]}


def assistant(msg_id="msg_1", req="req_1", out=300, sidechain=False, content=None):
    return {"type": "assistant", "uuid": f"u-{msg_id}-{out}", "parentUuid": "p", "timestamp": "2026-09-07T12:00:00.000Z",
            "sessionId": "sess-1", "requestId": req, "cwd": "D:/proj", "gitBranch": "main", "version": "2.1.201",
            "isSidechain": sidechain, "attributionSkill": "commit",
            "message": {"id": msg_id, "model": "claude-opus-5", "role": "assistant", "type": "message",
                        "stop_reason": "tool_use", "usage": {**USAGE, "output_tokens": out},
                        "content": content or [
                            {"type": "text", "text": "GIZLI METIN"},
                            {"type": "tool_use", "id": "t1", "name": "Edit",
                             "input": {"file_path": "D:/proj/a.py", "old_string": "GIZLI", "new_string": "GIZLI2"}},
                            {"type": "tool_use", "id": "t2", "name": "Bash", "input": {"command": "rm -rf GIZLI"}},
                        ]}}


def user_record():
    return {"type": "user", "uuid": "u0", "timestamp": "2026-09-07T11:59:00.000Z", "sessionId": "sess-1",
            "cwd": "D:/proj", "message": {"role": "user", "content": "GIZLI PROMPT"},
            "toolUseResult": {"stdout": "GIZLI CIKTI"}}


def synthetic_error():
    return {"type": "assistant", "uuid": "u-syn", "timestamp": "2026-09-07T12:01:00.000Z", "sessionId": "sess-1",
            "isApiErrorMessage": True,
            "message": {"id": "0f0f", "model": "<synthetic>", "role": "assistant",
                        "usage": {"input_tokens": 0, "output_tokens": 0}, "content": [{"type": "text", "text": "API Error"}]}}


def write_jsonl(path: Path, records, partial: str | None = None, malformed=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(r) for r in records]
    if malformed:
        lines.insert(1, "{bozuk json")
    text = "\n".join(lines) + "\n"
    if partial is not None:
        text += partial
    path.write_text(text, encoding="utf-8")


def test_strip_content_keeps_only_allowlisted_fields():
    out = strip_content(assistant())
    assert "content" not in out.get("message", {})
    assert out["message"]["usage"]["cache_creation"] == {"ephemeral_5m_input_tokens": 60, "ephemeral_1h_input_tokens": 40}
    assert out["message"]["usage"]["iterations"] == [{"type": "advisor_message", "model": "claude-opus-5",
                                                       "usage": {"input_tokens": 3, "output_tokens": 4}}]
    assert out["message"]["tool_uses"] == [{"name": "Edit", "file_path": "D:/proj/a.py"}, {"name": "Bash"}]
    assert out["attributionSkill"] == "commit" and out["requestId"] == "req_1"
    assert "GIZLI" not in json.dumps(out)


def test_strip_content_on_user_record_drops_prompt_and_tool_results():
    out = strip_content(user_record())
    assert "toolUseResult" not in out and out["message"] == {"role": "user"}
    assert "GIZLI" not in json.dumps(out)


def test_stripped_payloads_pass_the_ingest_forbidden_scan():
    for rec in (assistant(), user_record(), synthetic_error()):
        assert find_forbidden_key(strip_content(rec)) is False


def test_read_new_lines_skips_malformed_and_leaves_partial(tmp_path):
    p = tmp_path / "s.jsonl"
    write_jsonl(p, [assistant(), assistant("msg_2")], partial='{"type":"assistant","yarim":', malformed=True)
    consumed, records, skipped = read_new_lines(p, 0)
    assert len(records) == 2 and skipped == 1
    assert consumed < p.stat().st_size  # yarim satir tuketilmedi
    consumed2, records2, _ = read_new_lines(p, consumed)
    assert records2 == [] and consumed2 == consumed


def test_collector_is_incremental_and_restarts_on_shrink(tmp_path):
    root = tmp_path / ".claude"
    f = root / "projects" / "D--proj" / "sess-1.jsonl"
    write_jsonl(f, [user_record(), assistant(), assistant(out=350)])
    adapter = ClaudeCodeAdapter(env={"CLAUDE_CONFIG_DIR": str(root)}, home=tmp_path)
    inst = adapter.discover()[0]
    col = TranscriptCollector()

    b1 = col.collect(inst, Cursor())
    assert len(b1.items) == 3 and b1.skipped == 0
    assert all(i.kind == "transcript_record" and i.ref.startswith("D--proj/sess-1.jsonl@") for i in b1.items)
    assert all(find_forbidden_key(i.payload) is False for i in b1.items)
    fc = b1.next_cursor.files["D--proj/sess-1.jsonl"]
    assert fc.bytes_consumed == f.stat().st_size

    b2 = col.collect(inst, b1.next_cursor)
    assert b2.items == ()

    with f.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(synthetic_error()) + "\n")
    b3 = col.collect(inst, b2.next_cursor)
    assert len(b3.items) == 1 and b3.items[0].payload["message"]["model"] == "<synthetic>"

    write_jsonl(f, [assistant("msg_9")])  # dosya kuculdu -> bastan
    b4 = col.collect(inst, b3.next_cursor)
    assert len(b4.items) == 1 and b4.items[0].payload["message"]["id"] == "msg_9"


def test_collector_handles_subagent_files_and_counts_bad_files(tmp_path):
    root = tmp_path / ".claude"
    proj = root / "projects" / "D--proj"
    write_jsonl(proj / "sess-1.jsonl", [assistant()])
    write_jsonl(proj / "sess-1" / "subagents" / "agent-a1.jsonl", [assistant("msg_sub", sidechain=True)])
    (proj / "sess-1" / "subagents" / "workflows" / "wf_1").mkdir(parents=True)
    (proj / "sess-1" / "subagents" / "workflows" / "wf_1" / "journal.jsonl").write_text('{"agentId":"x"}\n', encoding="utf-8")
    (proj / "broken.jsonl").write_text("not json at all\n", encoding="utf-8")
    adapter = ClaudeCodeAdapter(env={"CLAUDE_CONFIG_DIR": str(root)}, home=tmp_path)
    batch = TranscriptCollector().collect(adapter.discover()[0], Cursor())
    refs = sorted(i.ref.split("@")[0] for i in batch.items)
    assert refs == ["D--proj/sess-1.jsonl", "D--proj/sess-1/subagents/agent-a1.jsonl"]
    assert batch.skipped == 1
    assert set(batch.next_cursor.files) == {"D--proj/sess-1.jsonl", "D--proj/sess-1/subagents/agent-a1.jsonl", "D--proj/broken.jsonl"}
