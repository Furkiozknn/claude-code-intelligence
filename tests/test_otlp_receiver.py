import gzip
import http.client
import json

import pytest

from cci.collectors.otlp import OtlpReceiver
from cci.collectors.otlp_metrics import OtlpMetricMapper

TS = "1757246400000000000"


def kv(key, value):
    if isinstance(value, bool):
        return {"key": key, "value": {"boolValue": value}}
    if isinstance(value, int):
        return {"key": key, "value": {"intValue": str(value)}}
    if isinstance(value, float):
        return {"key": key, "value": {"doubleValue": value}}
    return {"key": key, "value": {"stringValue": value}}


def logs_doc():
    return {"resourceLogs": [{"resource": {"attributes": [kv("session.id", "sess-1"), kv("user.account_uuid", "acc")]},
                              "scopeLogs": [{"logRecords": [
                                  {"timeUnixNano": TS, "attributes": [kv("event.name", "api_request"), kv("model", "claude-opus-5"),
                                                                     kv("input_tokens", 10), kv("output_tokens", 5), kv("request_id", "req_1"),
                                                                     kv("cost_usd_micros", 100)]},
                                  {"timeUnixNano": TS, "attributes": [kv("event.name", "api_request_body"), kv("body", "GIZLI")]},
                              ]}]}]}


def metrics_doc(tokens, cost, lines_added=3, sessions=1):
    def dp(value, **attrs):
        base = {"timeUnixNano": TS, "attributes": [kv(k, v) for k, v in attrs.items()]}
        base["asInt" if isinstance(value, int) else "asDouble"] = str(value) if isinstance(value, int) else value
        return base
    return {"resourceMetrics": [{"resource": {"attributes": [kv("session.id", "sess-1")]}, "scopeMetrics": [{"metrics": [
        {"name": "claude_code.token.usage", "sum": {"aggregationTemporality": 2, "isMonotonic": True,
                                                  "dataPoints": [dp(tokens, type="input", model="claude-opus-5")]}},
        {"name": "claude_code.cost.usage", "sum": {"aggregationTemporality": 2, "dataPoints": [dp(cost, model="claude-opus-5")]}},
        {"name": "claude_code.lines_of_code.count", "sum": {"aggregationTemporality": 2, "dataPoints": [dp(lines_added, type="added")]}},
        {"name": "claude_code.session.count", "sum": {"aggregationTemporality": 2, "dataPoints": [dp(sessions, start_type="fresh")]}},
        {"name": "claude_code.active_time.total", "sum": {"aggregationTemporality": 2, "dataPoints": [dp(12.5, type="user")]}},
        {"name": "claude_code.weird.metric", "sum": {"dataPoints": [dp(1)]}},
    ]}]}]}


@pytest.fixture
def receiver():
    sink: list = []
    r = OtlpReceiver(sink.append).start()
    r._sink_list = sink  # type: ignore[attr-defined]
    yield r
    r.stop()


def post(r, path, body: bytes, ctype="application/json", encoding=None):
    host, port = r.address
    conn = http.client.HTTPConnection(host, port, timeout=5)
    headers = {"Content-Type": ctype, "Content-Length": str(len(body))}
    if encoding:
        headers["Content-Encoding"] = encoding
    conn.request("POST", path, body=body, headers=headers)
    resp = conn.getresponse()
    data = resp.read()
    conn.close()
    return resp.status, json.loads(data or b"{}")


def test_receiver_binds_loopback_only():
    with pytest.raises(ValueError):
        OtlpReceiver(lambda e: None, host="0.0.0.0")


def test_logs_are_mapped_gated_and_sunk(receiver):
    status, body = post(receiver, "/v1/logs", json.dumps(logs_doc()).encode())
    assert status == 200 and body == {}
    sunk = receiver._sink_list
    assert len(sunk) == 1 and sunk[0].type == "usage.request" and sunk[0].payload["dedup_key"] == "anthropic:req:req_1"
    assert receiver.counters["accepted"] == 1 and receiver.logs.counters["dropped_raw_body"] == 1


def test_gzip_bodies_are_accepted(receiver):
    raw = json.dumps(logs_doc()).encode()
    status, _ = post(receiver, "/v1/logs", gzip.compress(raw), encoding="gzip")
    assert status == 200 and len(receiver._sink_list) == 1


def test_invalid_json_is_400_and_counted(receiver):
    status, body = post(receiver, "/v1/logs", b"{not json")
    assert status == 400 and receiver.counters["bad_request"] == 1 and receiver._sink_list == []


def test_too_large_is_413(receiver):
    receiver.max_body = 100
    status, _ = post(receiver, "/v1/logs", b"{" + b" " * 200 + b"}")
    assert status == 413 and receiver.counters["too_large"] == 1


def test_protobuf_without_decoder_is_honest_415(receiver):
    from cci.collectors import otlp as mod
    if mod.HAS_PROTO:
        pytest.skip("protobuf cozucu kurulu")
    status, body = post(receiver, "/v1/logs", b"\x0a\x00", ctype="application/x-protobuf")
    assert status == 415 and "http/json" in body["error"] and receiver.counters["unsupported_protobuf"] == 1


def test_traces_are_dropped_with_counter_by_default(receiver):
    status, _ = post(receiver, "/v1/traces", b"{}")
    assert status == 200 and receiver.counters["dropped_traces"] == 1 and receiver._sink_list == []


def test_unknown_path_is_404(receiver):
    status, _ = post(receiver, "/v1/other", b"{}")
    assert status == 404


def test_health_endpoint_exposes_counters(receiver):
    post(receiver, "/v1/logs", json.dumps(logs_doc()).encode())
    host, port = receiver.address
    conn = http.client.HTTPConnection(host, port, timeout=5)
    conn.request("GET", "/health")
    resp = conn.getresponse()
    data = json.loads(resp.read())
    assert resp.status == 200 and data["counters"]["accepted"] == 1


def test_metric_mapper_emits_deltas_from_cumulative_sums():
    m = OtlpMetricMapper()
    first = m.map_request(metrics_doc(tokens=100, cost=0.5))
    types = sorted(e.type for e in first)
    assert types == ["code.lines", "session.active_time", "session.started", "usage.metric_delta", "usage.metric_delta"]
    tok = [e for e in first if e.type == "usage.metric_delta" and e.payload["metric"] == "token.usage"][0]
    assert tok.payload == {"metric": "token.usage", "type": "input", "model": "claude-opus-5", "delta": 100.0}
    assert tok.evidence_class.value == "derived" and m.counters["dropped_unknown_metric"] == 1

    second = m.map_request(metrics_doc(tokens=130, cost=0.5, lines_added=3, sessions=1))
    deltas = {(e.type, e.payload.get("metric")): e.payload for e in second}
    assert deltas[("usage.metric_delta", "token.usage")]["delta"] == 30.0
    assert ("usage.metric_delta", "cost.usage") not in deltas  # sifir delta atlandi
    assert ("code.lines", None) not in deltas

    third = m.map_request(metrics_doc(tokens=20, cost=0.1))  # sayac dustu -> yeniden baslatma
    tok3 = [e for e in third if e.payload.get("metric") == "token.usage"][0]
    assert tok3.payload["delta"] == 20.0


def test_metrics_endpoint_end_to_end(receiver):
    status, _ = post(receiver, "/v1/metrics", json.dumps(metrics_doc(tokens=10, cost=0.01)).encode())
    assert status == 200
    assert {e.type for e in receiver._sink_list} >= {"usage.metric_delta", "code.lines", "session.started"}
    assert all(receiver.gate.check(e).accepted for e in receiver._sink_list)
