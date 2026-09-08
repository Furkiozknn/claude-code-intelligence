import json

from cci.adapters import Cursor, assert_contract
from cci.adapters.codex import CodexAdapter, records_from_rollout
from cci.ingest import find_forbidden_key


def rollout(path, lines):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(x) + "\n" for x in lines), encoding="utf-8")


def meta(subagent=False):
    return {"type": "session_meta", "timestamp": "2026-09-07T12:00:00Z",
            "payload": {"type": "session_meta", "id": "codex-sess-1", "thread_source": "subagent" if subagent else "primary",
                        "instructions": "GIZLI TALIMAT"}}


def ctx(model="gpt-5-codex"):
    return {"type": "turn_context", "timestamp": "2026-09-07T12:00:05Z", "payload": {"type": "turn_context", "model": model,
                                                                                      "cwd": "D:/gizli"}}


def usage(inp, cached, out, ts="2026-09-07T12:01:00Z"):
    return {"type": "event_msg", "timestamp": ts,
            "payload": {"type": "token_count", "last_token_usage": {"input_tokens": inp, "cached_input_tokens": cached,
                                                                    "output_tokens": out, "reasoning_output_tokens": 7},
                        "total_token_usage": {"input_tokens": 99999}}}


def test_cached_input_is_subtracted_and_model_backfilled(tmp_path):
    root = tmp_path / ".codex" / "sessions" / "2026" / "09"
    rollout(root / "rollout-1.jsonl", [meta(), usage(1000, 800, 50, "2026-09-07T12:00:01Z"), ctx(), usage(2000, 1500, 60)])
    a = CodexAdapter(env={}, home=tmp_path)
    assert_contract(a)
    batch = a.collect(a.discover()[0], Cursor())
    assert all(find_forbidden_key(i.payload) is False for i in batch.items)
    assert "GIZLI" not in json.dumps([i.payload for i in batch.items])
    recs = a.normalize(batch)
    assert len(recs) == 2
    assert (recs[0].tokens.input, recs[0].tokens.cache_read, recs[0].tokens.output) == (200, 800, 50)
    assert recs[0].model.id == "gpt-5-codex"  # ilk turn_context'ten geri dolduruldu
    assert recs[1].tokens.input == 500 and recs[1].tokens.reasoning == 7
    assert recs[0].dedup_key.startswith("openai:uuid:codex:") and recs[0].provider == "openai"
    assert not recs[0].cost.usd.released  # Codex fiyati yok -> withheld


def test_subagent_marks_sidechain_and_unknown_model(tmp_path):
    root = tmp_path / ".codex" / "sessions"
    rollout(root / "rollout-2.jsonl", [meta(subagent=True), usage(10, 0, 5)])
    a = CodexAdapter(env={}, home=tmp_path)
    recs = a.normalize(a.collect(a.discover()[0], Cursor()))
    assert recs[0].session.is_sidechain and recs[0].model.unknown and recs[0].attribution.query_source == "subagent"
    assert recs[0].session.session_id == "codex-sess-1"


def test_incremental_and_health(tmp_path):
    a = CodexAdapter(env={}, home=tmp_path)
    assert a.health().status == "down" and a.discover() == ()
    root = tmp_path / ".codex" / "sessions"
    rollout(root / "rollout-3.jsonl", [meta(), ctx(), usage(100, 0, 10)])
    inst = a.discover()[0]
    b1 = a.collect(inst, Cursor())
    assert len(b1.items) == 3 and a.health().status == "ok"
    assert a.collect(inst, b1.next_cursor).items == ()
