from collections import Counter
from datetime import UTC, date, datetime

from cci.adapters.base import RawBatch, RawItem
from cci.collectors.otlp_map import OtlpLogMapper
from cci.collectors.transcript import strip_content
from cci.model import AccountRef, SourceInstance, UsageRecord
from cci.normalize import Deduper, merge_records, normalize_transcript_batch, records_from_transcript

INST = SourceInstance(provider="anthropic", instance_id="claude-config:x", label="Default Claude", kind="cli",
                      root_path="/tmp/.claude", schema_verified=True, verified_at=date(2026, 9, 7))
ACC = AccountRef(provider="anthropic", account_key="acc")


def raw_assistant(msg_id="msg_1", req="req_1", out=300, sidechain=False, uuid=None, usage_extra=None,
                  iterations=None, model="claude-opus-5", cwd="D:/proj", agent=None, cost=None):
    usage = {"input_tokens": 12, "output_tokens": out, "cache_creation_input_tokens": 100,
             "cache_read_input_tokens": 5000,
             "cache_creation": {"ephemeral_5m_input_tokens": 60, "ephemeral_1h_input_tokens": 40}}
    if usage_extra:
        usage.update(usage_extra)
    if iterations is not None:
        usage["iterations"] = iterations
    rec = {"type": "assistant", "uuid": uuid or f"u-{msg_id}-{req}-{out}", "timestamp": "2026-09-07T12:00:00.000Z",
           "sessionId": "sess-1", "requestId": req, "cwd": cwd, "gitBranch": "main", "isSidechain": sidechain,
           "attributionSkill": "commit", "attributionMcpServer": "playwright",
           "message": {"id": msg_id, "model": model, "role": "assistant", "usage": usage,
                       "content": [{"type": "text", "text": "GIZLI"}]}}
    if agent:
        rec["agentId"] = agent
    if cost is not None:
        rec["costUSD"] = cost
    return strip_content(rec)


def test_transcript_record_maps_tokens_ttl_attribution_and_workspace():
    c = Counter()
    recs = records_from_transcript(raw_assistant(cost=0.0123), INST, ACC, c)
    assert len(recs) == 1
    r = recs[0]
    assert r.dedup_key == "anthropic:req:req_1" and r.message_key == "anthropic:msg:msg_1:sess-1"
    assert (r.tokens.input, r.tokens.output, r.tokens.cache_read, r.tokens.cache_write_total) == (12, 300, 5000, 100)
    assert (r.tokens.cache_write_5m, r.tokens.cache_write_1h) == (60, 40)
    assert r.attribution.skill == "commit" and r.attribution.mcp_server == "playwright"
    assert r.workspace.project_key and r.workspace.git_branch == "main" and "proj" not in r.workspace.project_key
    assert r.cost.vendor_usd.evidence_class.value == "vendor_estimated" and r.cost.usd.released is False
    assert r.model.display == "Opus 5" and r.ts == datetime(2026, 9, 7, 12, 0, tzinfo=UTC)


def test_ttl_mismatch_drops_split_and_counts():
    c = Counter()
    r = records_from_transcript(raw_assistant(usage_extra={"cache_creation_input_tokens": 999}), INST, ACC, c)[0]
    assert r.tokens.cache_write_total == 999 and r.tokens.cache_write_5m is None and c["cache_ttl_mismatch"] == 1


def test_synthetic_error_record_has_zero_tokens_and_flags():
    c = Counter()
    payload = raw_assistant(model="<synthetic>", req=None, msg_id="0f0f")
    payload["isApiErrorMessage"] = True
    r = records_from_transcript(payload, INST, ACC, c)[0]
    assert r.flags.synthetic and r.flags.api_error and r.tokens.billable_total == 0 and r.model.unknown
    assert c["synthetic"] == 1


def test_advisor_iterations_become_separate_records_and_zero_top_level_sums_iterations():
    c = Counter()
    its = [{"type": "advisor_message", "model": "claude-fable-5-1", "usage": {"input_tokens": 3, "output_tokens": 4}},
           {"type": "retry", "usage": {"input_tokens": 1, "output_tokens": 1}}]
    recs = records_from_transcript(raw_assistant(iterations=its), INST, ACC, c)
    assert len(recs) == 2 and recs[1].flags.advisor and recs[1].flags.iteration_index == 0
    assert recs[1].message_id == "msg_1:advisor:0" and recs[1].request_id is None
    assert recs[1].dedup_key == "anthropic:msg:msg_1:advisor:0:sess-1" and recs[1].model.display == "Fable 5.1"
    assert c["advisor"] == 1
    zero = raw_assistant(usage_extra={"input_tokens": 0, "output_tokens": 0, "cache_creation_input_tokens": 0,
                                      "cache_read_input_tokens": 0, "cache_creation": {"ephemeral_5m_input_tokens": 0, "ephemeral_1h_input_tokens": 0}},
                         iterations=[{"type": "retry", "usage": {"input_tokens": 7, "output_tokens": 8}},
                                     {"type": "retry", "usage": {"input_tokens": 1, "output_tokens": 1}}])
    c2 = Counter()
    r = records_from_transcript(zero, INST, ACC, c2)[0]
    assert (r.tokens.input, r.tokens.output) == (8, 9) and c2["iterations_summed"] == 1


def test_subagent_and_non_assistant_records():
    c = Counter()
    sub = records_from_transcript(raw_assistant(agent="a1"), INST, ACC, c)[0]
    assert sub.session.agent_id == "a1" and sub.attribution.query_source == "subagent"
    assert records_from_transcript({"type": "user", "message": {"role": "user"}}, INST, ACC, c) == []
    assert c["skipped_non_assistant"] == 1


def test_batch_normalization_counts_invalid():
    batch = RawBatch(instance=INST, items=(
        RawItem(kind="transcript_record", ref="a@0", payload=raw_assistant()),
        RawItem(kind="transcript_record", ref="a@1", payload={"type": "assistant", "timestamp": "1999-01-01T00:00:00Z",
                                                                "sessionId": "s", "message": {"usage": {}}}),
        RawItem(kind="other", ref="b", payload={}),
    ))
    recs, counters = normalize_transcript_batch(batch, ACC)
    assert len(recs) == 1 and counters["skipped_bad_timestamp"] == 0 and counters["skipped_invalid"] == 1
    assert counters["skipped_kind"] == 1


# ------------------------------------------------------------------ dedup
def rec(**kw) -> UsageRecord:
    return records_from_transcript(raw_assistant(**kw), INST, ACC)[0]


def test_seven_stream_copies_collapse_to_max_total():
    d = Deduper()
    outcomes = d.add_many([rec(out=o, uuid=f"u{o}") for o in (10, 50, 120, 300, 200, 300, 90)])
    assert len(d) == 1 and d.records()[0].tokens.output == 300
    assert outcomes["inserted"] == 1 and outcomes["replaced"] + outcomes["merged"] == 6
    assert d.counters["token_mismatch"] >= 1  # kismi akis kopyalari farkli sayilar tasir


def test_sidechain_replay_is_dropped_whichever_order():
    parent = rec()
    replay = rec(req="req_replay", sidechain=True, out=999)
    d1 = Deduper(); d1.add(parent); assert d1.add(replay) == "sidechain_dropped" and len(d1) == 1
    d2 = Deduper(); d2.add(replay); assert d2.add(parent) == "replaced" and len(d2) == 1
    assert d2.records()[0].session.is_sidechain is False and d2.counters["sidechain_replay_dropped"] == 1


def test_distinct_sidechain_response_is_kept():
    d = Deduper()
    d.add(rec())
    assert d.add(rec(msg_id="msg_side", req="req_side", sidechain=True)) == "inserted" and len(d) == 2


def test_otel_and_transcript_merge_into_one_record():
    otel_doc = {"resourceLogs": [{"resource": {"attributes": [
        {"key": "session.id", "value": {"stringValue": "sess-1"}},
        {"key": "user.account_uuid", "value": {"stringValue": "acc"}}]},
        "scopeLogs": [{"logRecords": [{"timeUnixNano": "1788782400000000000", "attributes": [
            {"key": "event.name", "value": {"stringValue": "api_request"}},
            {"key": "model", "value": {"stringValue": "claude-opus-5"}},
            {"key": "request_id", "value": {"stringValue": "req_1"}},
            {"key": "input_tokens", "value": {"intValue": "12"}}, {"key": "output_tokens", "value": {"intValue": "300"}},
            {"key": "cache_read_tokens", "value": {"intValue": "5000"}}, {"key": "cache_creation_tokens", "value": {"intValue": "100"}},
            {"key": "cost_usd_micros", "value": {"intValue": "45000"}}, {"key": "duration_ms", "value": {"intValue": "1234"}},
            {"key": "agent.name", "value": {"stringValue": "Explore"}}, {"key": "prompt.id", "value": {"stringValue": "p-1"}}]}]}]}]}
    env = OtlpLogMapper().map_request(otel_doc)[0]
    otel = UsageRecord.from_payload(env.payload)
    assert otel.dedup_key == env.payload["dedup_key"] and otel.tokens.input_total == env.payload["tokens"]["input_total"]
    transcript = rec()
    assert otel.dedup_key == transcript.dedup_key == "anthropic:req:req_1"
    d = Deduper()
    d.add(otel)
    d.add(transcript)
    merged = d.records()[0]
    assert len(d) == 1
    assert merged.cost.vendor_usd.render() == "$0.05"           # OTel'den
    assert merged.tokens.cache_write_5m == 60                     # transcript'ten TTL kirilimi
    assert merged.attribution.agent == "Explore" and merged.attribution.skill == "commit"
    assert merged.prompt_id == "p-1" and merged.message_id == "msg_1" and merged.workspace is not None
    assert merged.timing.duration_ms == 1234
    assert d.counters["token_mismatch"] == 0 and d.counters["vendor_cost_merged"] + d.counters["ttl_split_merged"] >= 1


def test_dedup_result_is_independent_of_arrival_order():
    import itertools
    otel_doc = {"resourceLogs": [{"resource": {"attributes": [{"key": "session.id", "value": {"stringValue": "sess-1"}}]},
        "scopeLogs": [{"logRecords": [{"timeUnixNano": "1788782400000000000", "attributes": [
            {"key": "event.name", "value": {"stringValue": "api_request"}},
            {"key": "model", "value": {"stringValue": "claude-opus-5"}},
            {"key": "request_id", "value": {"stringValue": "req_1"}},
            {"key": "input_tokens", "value": {"intValue": "12"}}, {"key": "output_tokens", "value": {"intValue": "300"}},
            {"key": "cache_read_tokens", "value": {"intValue": "5000"}}, {"key": "cache_creation_tokens", "value": {"intValue": "100"}},
            {"key": "cost_usd_micros", "value": {"intValue": "45000"}}]}]}]}]}
    otel = UsageRecord.from_payload(OtlpLogMapper().map_request(otel_doc)[0].payload)
    items = {"otel": otel, "copy10": rec(out=10, uuid="a"), "copy300": rec(out=300, uuid="b"),
             "replay": rec(req="req_replay", sidechain=True, out=999, uuid="c")}
    for order in itertools.permutations(items):
        d = Deduper()
        for name in order:
            d.add(items[name])
        recs = d.records()
        assert len(recs) == 1, order
        r = recs[0]
        assert r.dedup_key == "anthropic:req:req_1" and r.tokens.output == 300, order
        assert r.cost.vendor_usd is not None and r.cost.vendor_usd.render() == "$0.05", order
        assert r.tokens.cache_write_5m == 60 and r.session.is_sidechain is False, order
        # Kazananin KIMLIGI de sabit olmali: summarize_daily (gun, provider, source.instance_id)
        # ile gruplar. Token sayilari esitken kazanan gelis sirasina kalirsa ayni gun iki
        # satira bolunur (transcript satiri + OTel satiri) ve koruma yasasi 1 gun beklerken 2 bulur.
        assert (r.source.instance_id, r.ts) == ("claude-config:x", datetime(2026, 9, 7, 12, 0, tzinfo=UTC)), order
        assert d.counters["sidechain_replay_dropped"] == 1, order


def test_merge_records_never_overwrites_tokens_but_counts_mismatch():
    a, b = rec(out=100, uuid="a"), rec(out=101, uuid="b")
    c = Counter()
    m = merge_records(a, b, c)
    assert m.tokens.output == 100 and c["token_mismatch"] == 1
