import http.client
import json
import threading
from datetime import UTC, date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer

from cci.model import (AccountRef, CollectorRef, Cost, EvidenceClass, Figure, ModelRef, QuotaSnapshot, QuotaWindow, SessionRef,
                       SourceInstance, Tokens, UsageRecord)
from cci.pricing import PricingTable
from cci.research import ResearchProxy, estimate_unit, headers_to_quota_snapshot, intervals_from, sanitize_headers

NOW = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
ACC = AccountRef(provider="anthropic", account_key="acc")


class FakeAnthropic(BaseHTTPRequestHandler):
    seen = []

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length)
        FakeAnthropic.seen.append({"path": self.path, "auth": self.headers.get("Authorization"), "body": body})
        payload = b'{"id":"msg_1","usage":{"input_tokens":10,"output_tokens":5}}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("anthropic-ratelimit-unified-5h-utilization", "0.42")
        self.send_header("anthropic-ratelimit-unified-5h-reset", str(int((NOW + timedelta(hours=2)).timestamp())))
        self.send_header("anthropic-ratelimit-unified-5h-status", "allowed")
        self.send_header("anthropic-ratelimit-unified-7d-utilization", "0.9")
        self.send_header("anthropic-ratelimit-unified-7d-status", "allowed_warning")
        self.send_header("Set-Cookie", "gizli=1")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *a):
        return


def test_sanitize_and_headers_to_snapshot():
    h = {"Authorization": "Bearer sk-ant-GIZLI", "X-Api-Key": "k", "anthropic-ratelimit-unified-5h-utilization": "0.5",
         "anthropic-ratelimit-unified-5h-reset": "1788789600", "anthropic-ratelimit-unified-7d-utilization": "1.4"}
    assert "authorization" not in sanitize_headers(h) and "x-api-key" not in sanitize_headers(h)
    snap = headers_to_quota_snapshot(h, fetched_at=NOW, account=ACC)
    assert snap.source == "rate_limit_headers" and snap.authoritative
    assert snap.window("session_5h").utilization == 0.5 and snap.window("session_5h").resets_at.year == 2026
    assert snap.window("weekly_all").utilization == 1.0  # kirpildi
    assert headers_to_quota_snapshot({"content-type": "x"}, fetched_at=NOW, account=ACC) is None


def test_proxy_forwards_streams_and_never_logs_secrets(tmp_path):
    FakeAnthropic.seen = []
    upstream = HTTPServer(("127.0.0.1", 0), FakeAnthropic)
    threading.Thread(target=upstream.serve_forever, daemon=True).start()
    snaps = []
    proxy = ResearchProxy(research_dir=tmp_path / "research", upstream=f"http://127.0.0.1:{upstream.server_address[1]}",
                          quota_sink=snaps.append, account=ACC).start()
    try:
        host, port = proxy.address
        conn = http.client.HTTPConnection(host, port, timeout=5)
        body = json.dumps({"model": "claude-opus-5", "messages": [{"role": "user", "content": "GIZLI PROMPT"}]}).encode()
        conn.request("POST", "/v1/messages", body=body, headers={"Authorization": "Bearer sk-ant-GIZLI", "Content-Type": "application/json",
                                                                 "anthropic-beta": "x", "Content-Length": str(len(body))})
        resp = conn.getresponse()
        data = resp.read()
        assert resp.status == 200 and json.loads(data)["id"] == "msg_1"
        assert resp.getheader("anthropic-ratelimit-unified-5h-utilization") == "0.42"
        assert FakeAnthropic.seen[0]["auth"] == "Bearer sk-ant-GIZLI" and FakeAnthropic.seen[0]["body"] == body  # degistirilmedi
        conn.close()
    finally:
        proxy.stop()
        upstream.shutdown(); upstream.server_close()
    assert len(snaps) == 1 and snaps[0].window("session_5h").utilization == 0.42 and snaps[0].window("weekly_all").severity == "warning"
    log = (tmp_path / "research" / "requests.jsonl").read_text(encoding="utf-8")
    assert "GIZLI" not in log and "authorization" not in log.lower() and "cookie" not in log.lower()
    rec = json.loads(log.splitlines()[0])
    assert rec["model"] == "claude-opus-5" and rec["status"] == 200 and rec["rate_limit"]["anthropic-ratelimit-unified-5h-status"] == "allowed"
    assert not (tmp_path / "research" / "bodies").exists()  # govde yakalama kapali
    assert proxy.counters == {"requests": 1, "errors": 0, "quota_headers": 1, "bodies": 0}


def test_proxy_upstream_down_returns_502(tmp_path):
    proxy = ResearchProxy(research_dir=tmp_path / "r", upstream="http://127.0.0.1:1", timeout_s=2).start()
    try:
        host, port = proxy.address
        conn = http.client.HTTPConnection(host, port, timeout=10)
        conn.request("POST", "/v1/messages", body=b"{}", headers={"Content-Length": "2"})
        resp = conn.getresponse()
        assert resp.status == 502 and json.loads(resp.read())["error"] == "upstream unreachable"
        conn.close()
    finally:
        proxy.stop()
    assert proxy.counters["errors"] == 1


# ------------------------------------------------------------------ unit estimator
SRC = SourceInstance(provider="anthropic", instance_id="x", label="x", kind="cli", schema_verified=True, verified_at=date(2026, 9, 7))
COL = CollectorRef(name="transcript", version="0.0.1", schema_version=1)
H5 = 5 * 3600


def snap(at, util, resets_at):
    return QuotaSnapshot(snapshot_id=f"s{at.isoformat()}", provider="anthropic", account=ACC, fetched_at=at, source="usage_api",
                         authoritative=True, raw_hash="a" * 64,
                         windows=(QuotaWindow(kind="session_5h", duration_s=H5, utilization=util, resets_at=resets_at),))


def rec(i, ts, inp, out, cache_read=0, cache_write=0):
    return UsageRecord(provider="anthropic", source=SRC, account=ACC, session=SessionRef(session_id="s"), request_id=f"r{i}", ts=ts,
                       model=ModelRef(id="claude-opus-5", display="Opus 5"),
                       tokens=Tokens(input=inp, output=out, cache_read=cache_read, cache_write_total=cache_write),
                       cost=Cost(usd=Figure.withheld("nanoUSD", EvidenceClass.ESTIMATED, "x")), collector=COL)


def test_intervals_and_estimate_bands():
    resets = NOW + timedelta(hours=4)
    # utilization her 10 dk'da %2 artiyor; her aralikta 1000 input + 200 output (io_only=1200 -> cap 60000 sabit)
    snaps, recs = [], []
    util = 0.10
    for k in range(6):
        t = NOW + timedelta(minutes=10 * k)
        snaps.append(snap(t, util, resets))
        if k < 5:
            # cache okuma/yazma dalgalanir, io sabit -> yalniz io_only tutarli
            recs.append(rec(k, t + timedelta(minutes=5), 1000, 200, cache_read=500 * (k % 2), cache_write=300 * ((k + 1) % 2)))
        util += 0.02
    ivs = intervals_from(snaps, recs, "session_5h")
    assert len(ivs) == 5 and all(abs(iv.d_util - 0.02) < 1e-9 and iv.records == 1 for iv in ivs)
    res = estimate_unit(snaps, recs, "session_5h", table=PricingTable.load_bundled())
    assert res["n_intervals"] == 5 and not res["learning"]
    io = res["candidates"]["io_only"]
    assert abs(io["implied_cap"]["p50"] - 60000) < 1 and io["cv"] < 1e-9
    assert res["most_consistent"] == "io_only" and res["core_params"]["candidate"] == "io_only"
    assert res["candidates"]["raw"]["cv"] > 0 and res["candidates"]["no_cache_read"]["cv"] > 0
    assert res["candidates"]["price_equivalent"]["n"] == 5


def test_estimate_learning_with_few_intervals_and_reset_handling():
    resets = NOW + timedelta(hours=4)
    snaps = [snap(NOW, 0.5, resets), snap(NOW + timedelta(minutes=10), 0.5, resets), snap(NOW + timedelta(minutes=20), 0.6, resets),
             snap(NOW + timedelta(minutes=30), 0.1, resets + timedelta(hours=5))]  # reset -> yeni cipa
    recs = [rec(0, NOW + timedelta(minutes=15), 100, 10)]
    res = estimate_unit(snaps, recs, "session_5h")
    assert res["n_intervals"] == 1 and res["learning"] and res["most_consistent"] is None
    assert res["candidates"]["io_only"]["implied_cap"]["p50"] is None
    assert abs(res["candidates"]["io_only"]["implied_cap"]["median"] - 1100.0) < 1e-6
    assert "core_params" not in res
