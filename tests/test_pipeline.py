import json
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from cci.adapters.claude_code import ClaudeCodeAdapter
from cci.adapters.claude_code.quota_map import parse_usage_response
from cci.api import build_snapshot, write_snapshot
from cci.api.snapshot import read_snapshot
from cci.collectors.otlp_map import OtlpLogMapper
from cci.model import AccountRef
from cci.pipeline import Pipeline
from cci.pricing import PricingTable
from cci.store import EventStore

IST = ZoneInfo("Europe/Istanbul")
NOW = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
ACC = AccountRef(provider="anthropic", account_key="acc-uuid-12345678")


def assistant(msg_id, req, out, ts="2026-09-07T12:00:00.000Z", sidechain=False):
    return {"type": "assistant", "uuid": f"u-{msg_id}-{req}-{out}", "timestamp": ts, "sessionId": "sess-1",
            "requestId": req, "cwd": "D:/gizli/proje", "isSidechain": sidechain,
            "message": {"id": msg_id, "model": "claude-opus-5", "role": "assistant",
                        "usage": {"input_tokens": 100, "output_tokens": out, "cache_creation_input_tokens": 50,
                                  "cache_read_input_tokens": 1000,
                                  "cache_creation": {"ephemeral_5m_input_tokens": 30, "ephemeral_1h_input_tokens": 20}},
                        "content": [{"type": "text", "text": "GIZLI"}]}}


def layout(root, records):
    f = root / "projects" / "D--gizli-proje" / "sess-1.jsonl"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    return f


def otel_request(req, out, micros):
    doc = {"resourceLogs": [{"resource": {"attributes": [{"key": "session.id", "value": {"stringValue": "sess-1"}},
                                                          {"key": "user.account_uuid", "value": {"stringValue": ACC.account_key}}]},
                             "scopeLogs": [{"logRecords": [{"timeUnixNano": "1788782400000000000", "attributes": [
                                 {"key": "event.name", "value": {"stringValue": "api_request"}},
                                 {"key": "model", "value": {"stringValue": "claude-opus-5"}},
                                 {"key": "request_id", "value": {"stringValue": req}},
                                 {"key": "input_tokens", "value": {"intValue": "100"}}, {"key": "output_tokens", "value": {"intValue": str(out)}},
                                 {"key": "cache_read_tokens", "value": {"intValue": "1000"}}, {"key": "cache_creation_tokens", "value": {"intValue": "50"}},
                                 {"key": "cost_usd_micros", "value": {"intValue": str(micros)}}]}]}]}]}
    return OtlpLogMapper().map_request(doc)[0]


def test_end_to_end_transcript_and_otlp_merge_then_summaries_and_snapshot(tmp_path):
    root = tmp_path / ".claude"
    f = layout(root, [assistant("msg_1", "req_1", 10), assistant("msg_1", "req_1", 40),  # akis kopyasi
                      assistant("msg_2", "req_2", 20), assistant("msg_1", "req_replay", 999, sidechain=True)])
    adapter = ClaudeCodeAdapter(env={"CLAUDE_CONFIG_DIR": str(root)}, home=tmp_path)
    store = EventStore(tmp_path / "cci" / "events.db")
    pipe = Pipeline(store, PricingTable.load_bundled(), IST, cursors_path=tmp_path / "cci" / "cursors.json", account=ACC)

    r1 = pipe.ingest_transcripts(adapter)
    assert r1.instances == 1 and r1.raw_items == 4 and r1.records == 4 and r1.written == 4 and r1.rejected == 0
    r2 = pipe.ingest_transcripts(adapter)
    assert r2.raw_items == 0 and r2.written == 0  # imlec kalici

    # OTLP ayni istek icin satici maliyeti getirir
    for env in (otel_request("req_1", 40, 12345), otel_request("req_2", 20, 6789)):
        assert pipe.gate.check(env).accepted and pipe.sink(env)
    assert pipe.sink(otel_request("req_1", 40, 12345)) is False  # idempotent

    recs = pipe.records()
    assert [r.dedup_key for r in recs] == ["anthropic:req:req_1", "anthropic:req:req_2"]
    r_1 = recs[0]
    assert r_1.tokens.output == 40 and r_1.tokens.cache_write_5m == 30       # max kopya + TTL kirilimi
    assert r_1.cost.vendor_usd.render() == "$0.01" and r_1.cost.usd.released   # OTel maliyeti + bizim fiyat
    assert r_1.message_id == "msg_1" and r_1.workspace is not None and "gizli" not in r_1.workspace.project_key
    assert pipe.dedup_counters["sidechain_replay_dropped"] == 1

    days = pipe.daily(strict=True)
    assert len(days) == 1 and days[0].totals.requests == 2 and days[0].conservation.ok
    sessions = pipe.sessions(strict=True)
    assert sessions[0].session_id == "sess-1" and sessions[0].totals.requests == 2

    # yeni satir eklenince artimli devam
    with f.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(assistant("msg_3", "req_3", 5, ts="2026-09-07T13:00:00.000Z")) + "\n")
    r3 = pipe.ingest_transcripts(adapter)
    assert r3.raw_items == 1 and r3.written == 1 and pipe.daily()[0].totals.requests == 3

    snap_body = {"five_hour": {"utilization": 72, "resets_at": (NOW + timedelta(hours=2)).isoformat()},
                 "seven_day": {"utilization": 84, "resets_at": (NOW + timedelta(days=3)).isoformat()}}
    quota, _ = parse_usage_response(snap_body, account=ACC, fetched_at=NOW - timedelta(seconds=30))
    snapshot = build_snapshot(now=NOW, quota=quota, today=days[0], health={"transcript": "ok"})
    path = tmp_path / "cci" / "state" / "latest.json"
    write_snapshot(path, snapshot)
    back = read_snapshot(path)
    assert back["schema_version"] == 1 and back["account_key_short"] == "acc-uuid" and back["quota"]["age_s"] == 30
    kinds = {w["kind"]: w for w in back["quota"]["windows"]}
    assert kinds["session_5h"]["utilization_pct"] == 72 and kinds["session_5h"]["pace"]["stage"] in ("far_ahead", "ahead")
    assert kinds["session_5h"]["badge"] == "●" and kinds["session_5h"]["pace"]["eta_badge"] == "~"
    assert back["today"]["requests"] == 2 and back["today"]["cost"]["released"] is True
    assert back["today"]["cost"]["text"].startswith("$") and back["today"]["conservation_ok"] is True
    text = json.dumps(back)
    assert "gizli" not in text and "D:/" not in text and ACC.account_key not in text
    assert not list(path.parent.glob("*.tmp"))
    assert back["next_display_change_at"] > back["generated_at"]
    store.close()


def test_snapshot_without_quota_shows_placeholder():
    snap = build_snapshot(now=NOW, quota=None, today=None)
    assert snap["quota"]["placeholder"] == "--" and snap["quota"]["windows"] == [] and snap["today"] is None
