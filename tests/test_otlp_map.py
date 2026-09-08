import json

from cci.adapters.claude_code.models import display_name, model_ref, normalize_model_id
from cci.collectors.otlp_map import OtlpLogMapper, any_value
from cci.ingest import IngestGate, find_forbidden_key

TS = "1788782400000000000"  # 2026-09-07T12:00:00Z


def kv(key, value):
    if isinstance(value, bool):
        return {"key": key, "value": {"boolValue": value}}
    if isinstance(value, int):
        return {"key": key, "value": {"intValue": str(value)}}
    if isinstance(value, float):
        return {"key": key, "value": {"doubleValue": value}}
    return {"key": key, "value": {"stringValue": value}}


def record(name, **attrs):
    return {"timeUnixNano": TS, "severityText": "INFO", "body": {"stringValue": f"claude_code.{name}"},
            "attributes": [kv("event.name", name)] + [kv(k, v) for k, v in attrs.items()]}


def request_doc(*records):
    return {"resourceLogs": [{
        "resource": {"attributes": [kv("service.name", "claude-code"), kv("session.id", "sess-1"),
                                    kv("user.account_uuid", "acc-uuid-1"), kv("user.email", "GIZLI@ornek.com"),
                                    kv("app.version", "2.1.201")]},
        "scopeLogs": [{"scope": {"name": "com.anthropic.claude_code"}, "logRecords": list(records)}],
    }]}


def test_any_value_shapes():
    assert any_value({"intValue": "42"}) == 42 and any_value({"doubleValue": 1.5}) == 1.5
    assert any_value({"boolValue": True}) is True and any_value({"stringValue": "x"}) == "x"
    assert any_value({"arrayValue": {"values": [{"intValue": "1"}, {"stringValue": "a"}]}}) == [1, "a"]


def test_model_display_names():
    assert display_name("claude-opus-5") == "Opus 5"
    assert display_name("claude-sonnet-4-5-20250929") == "Sonnet 4.5"
    assert display_name("us.anthropic.claude-fable-5-1-v1:0") == "Fable 5.1"
    assert normalize_model_id("us.anthropic.claude-fable-5-1-v1:0") == "claude-fable-5-1"
    assert model_ref("<synthetic>").unknown and model_ref(None).unknown and model_ref("gpt-5").unknown


def test_api_request_maps_to_usage_record_with_vendor_cost_and_account():
    doc = request_doc(record("api_request", model="claude-opus-5", cost_usd=0.0123, cost_usd_micros=12300,
                             duration_ms=1500, input_tokens=120, output_tokens=40, cache_read_tokens=900,
                             cache_creation_tokens=300, request_id="req_9", client_request_id="cli-1",
                             speed="fast", query_source="subagent", effort="high", **{"agent.name": "Explore",
                             "skill.name": "commit", "prompt.id": "p-1"}))
    m = OtlpLogMapper()
    envs = m.map_request(doc)
    assert len(envs) == 1 and m.counters["mapped"] == 1
    e = envs[0]
    assert e.type == "usage.request" and e.account_key == "acc-uuid-1" and e.session_id == "sess-1"
    p = e.payload
    assert p["dedup_key"] == "anthropic:req:req_9"
    # exclude_none: bos alanlar payload'a yazilmaz (depo boyutu)
    assert p["tokens"]["input"] == 120 and p["tokens"]["input_total"] == 1320 and "cache_write_5m" not in p["tokens"]
    assert p["cost"]["vendor_usd"]["evidence_class"] == "vendor_estimated"
    assert p["cost"]["vendor_usd"]["value"] == "12300000"  # micros*1000 nanoUSD
    assert p["cost"]["usd"]["released"] is False
    assert p["attribution"] == {"query_source": "subagent", "agent": "Explore", "skill": "commit", "speed": "fast",
                                "effort": "high"}
    assert p["model"] == {"id": "claude-opus-5", "display": "Opus 5", "family": "opus", "unknown": False}
    assert "GIZLI" not in json.dumps(p)
    assert IngestGate().check(e).accepted


def test_prompt_and_tool_events_never_carry_content():
    doc = request_doc(
        record("user_prompt", prompt_length=42, prompt="GIZLI PROMPT METNI", **{"prompt.id": "p-1", "message.uuid": "m-1"}),
        record("tool_result", tool_name="Bash", tool_use_id="t-1", success=True, duration_ms=30,
               tool_parameters='{"command":"GIZLI"}', tool_input="GIZLI", tool_input_size_bytes=12,
               tool_result_size_bytes=300, error="GIZLI HATA", **{"prompt.id": "p-1"}),
        record("api_error", model="claude-opus-5", status_code=529, attempt=2, duration_ms=10,
               error="GIZLI overloaded", request_id="req_e"),
        record("assistant_response", response_length=99, response="GIZLI YANIT", model="claude-opus-5",
               request_id="req_9", **{"prompt.id": "p-1"}),
        record("permission_mode_changed", from_mode="default", to_mode="plan", trigger="shift_tab"),
        record("mcp_server_connection", server_name="playwright", status="connected", transport_type="stdio",
               duration_ms=120),
        record("tool_decision", tool_name="Edit", tool_use_id="t-2", decision="accept", tool_source="builtin",
               source="user_temporary"),
        record("api_refusal", model="claude-opus-5", attempt=1, request_id="req_r"),
    )
    m = OtlpLogMapper()
    envs = m.map_request(doc)
    types = [e.type for e in envs]
    assert types == ["prompt.submitted", "tool.call", "usage.error", "prompt.responded", "permission.mode_changed",
                     "mcp.connection", "tool.decision", "usage.refusal"]
    gate = IngestGate()
    for e in envs:
        assert "GIZLI" not in json.dumps(e.payload), e.type
        assert find_forbidden_key(e.payload) is False
        assert gate.check(e).accepted, (e.type, gate.check(e))
    assert envs[0].payload == {"prompt_id": "p-1", "prompt_length": 42, "message_uuid": "m-1"}
    assert envs[1].payload["input_size_bytes"] == 12 and "error" not in envs[1].payload


def test_raw_body_and_unknown_events_are_dropped_with_counters():
    doc = request_doc(record("api_request_body", body="GIZLI GOVDE", model="x"),
                      record("api_response_body", body="GIZLI"),
                      record("auth", action="login", success=True),
                      {"timeUnixNano": TS, "attributes": [kv("model", "x")]})
    m = OtlpLogMapper()
    assert m.map_request(doc) == []
    assert m.counters == {"dropped_raw_body": 2, "dropped_unknown_event": 1, "dropped_no_event_name": 1}


def test_missing_account_uuid_gives_no_account_key():
    doc = {"resourceLogs": [{"resource": {"attributes": [kv("session.id", "s")]},
                             "scopeLogs": [{"logRecords": [record("api_request", model="claude-opus-5",
                                                                  input_tokens=1, output_tokens=1, request_id="r")]}]}]}
    e = OtlpLogMapper().map_request(doc)[0]
    assert e.account_key is None and "account" not in e.payload and e.payload["session"]["session_id"] == "s"
