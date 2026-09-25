import gzip
import http.client
import json

import pytest

from cci.collectors.otlp import OtlpReceiver
from cci.collectors.otlp_metrics import OtlpMetricMapper

TS = "1788782400000000000"


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


# --- sertlestirme: 25 Eylul 2026 ------------------------------------------------
# Alici tek basina calisan, kimlik dogrulamasi olmayan bir yerel HTTP sunucusu.
# Asagidaki uc test, her biri o gun gercekten calisan bir saldiri yolunu kapatir.


def _raw(r, request: bytes, timeout: float = 3.0) -> bytes:
    import socket
    host, port = r.address
    with socket.create_connection((host, port), timeout=timeout) as s:
        s.sendall(request)
        chunks = []
        try:
            while True:
                c = s.recv(65536)
                if not c:
                    break
                chunks.append(c)
                if b"\r\n\r\n" in b"".join(chunks):
                    break
        except TimeoutError:
            pass
        return b"".join(chunks)


def test_gzip_bomb_is_rejected_without_inflating_it(receiver):
    # 1 MB sinirinin altinda kalan bir gzip govdesi, acildiginda yuzlerce MB
    # olabiliyordu - ve alici onu once TAMAMEN acip ancak sonra boyutuna
    # bakiyordu. Sinir, acma sirasinda uygulanmali.
    import tracemalloc
    bomb = gzip.compress(b" " * (200 * 1024 * 1024), compresslevel=9)
    assert len(bomb) < receiver.max_body
    tracemalloc.start()
    try:
        status, _ = post(receiver, "/v1/logs", bomb, encoding="gzip")
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert status == 413 and receiver.counters["too_large"] == 1 and receiver._sink_list == []
    assert peak < 32 * 1024 * 1024, f"alici govdeyi acarken {peak // 2**20} MB ayirdi"


def test_gzip_body_at_the_limit_is_still_accepted(receiver):
    raw = json.dumps(logs_doc()).encode()
    receiver.max_body = len(raw)
    status, _ = post(receiver, "/v1/logs", gzip.compress(raw), encoding="gzip")
    assert status == 200 and len(receiver._sink_list) == 1


def test_negative_content_length_is_400_not_an_unbounded_read(receiver):
    # int("-1") gecerli; rfile.read(-1) ise baglanti kapanana kadar okur -
    # boyut siniri atlanir ve is parcacigi istemci gidene dek asili kalir.
    resp = _raw(receiver, b"POST /v1/logs HTTP/1.1\r\nHost: x\r\nContent-Type: application/json\r\n"
                          b"Content-Length: -1\r\n\r\n{}")
    assert resp.startswith(b"HTTP/1.1 400"), resp[:60]
    assert receiver.counters["bad_request"] == 1 and receiver._sink_list == []


@pytest.mark.parametrize("ctype", ["application/json", ""])
def test_browser_requests_are_refused(receiver, ctype):
    # Tarayici her POST'a Origin ekler; OTLP ihracatcilari eklemez. Origin'li
    # bir istek, kullanicinin actigi herhangi bir web sayfasinin 127.0.0.1'e
    # sahte kullanim/maliyet yazmaya calismasidir (icerik turu bos bir Blob
    # "basit istek" sayilir, on ucus yok). Depoya hicbir sey girmemeli.
    host, port = receiver.address
    conn = http.client.HTTPConnection(host, port, timeout=5)
    body = json.dumps(logs_doc()).encode()
    headers = {"Content-Length": str(len(body)), "Origin": "https://ornek.invalid"}
    if ctype:
        headers["Content-Type"] = ctype
    conn.request("POST", "/v1/logs", body=body, headers=headers)
    resp = conn.getresponse()
    resp.read()
    conn.close()
    assert resp.status == 403
    assert receiver.counters["browser_origin"] == 1 and receiver._sink_list == []


@pytest.mark.parametrize("body", [b"not gzip at all", gzip.compress(b'{"resourceLogs": []}')[:-12]])
def test_corrupt_or_truncated_gzip_is_400(receiver, body):
    status, body_ = post(receiver, "/v1/logs", body, encoding="gzip")
    assert status == 400 and body_ == {"error": "bad gzip"} and receiver.counters["bad_request"] == 1
