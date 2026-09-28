"""OTLP HTTP alicisi (loopback). docs/PROVIDERS.md §4, ARCHITECTURE.md §9.

- `/v1/logs` (birincil), `/v1/metrics` (capraz dogrulama), `/v1/traces` (Core disi:
  200 + `dropped_traces` sayaci; R-2).
- Icerik turu: `application/json` (OTLP/JSON). `application/x-protobuf` icin
  protobuf cozucu yoksa DURUST 415 doner (sessiz "200 OK" yok - zcquant anti-kalibi).
- Govde <= 1 MB (413), gzip desteklenir, bozuk JSON 400. Sinir gzip ACILIRKEN
  uygulanir: 1 MB'lik bir gzip bombasi bellekte yuzlerce MB'a acilmaz.
- Negatif/bozuk `Content-Length` 400 (okunmaz; `read(-1)` sinirsiz okurdu).
- `Origin` basligi tasiyan istek 403: tarayici her POST'a Origin ekler, OTLP
  ihracatcilari eklemez. Boylece acik bir web sayfasi 127.0.0.1'e sahte
  kullanim/maliyet yazamaz (kimlik dogrulamasi olmayan alicinin tek kapisi).
- Her olay ingest kapisindan gecer; kabul edilenler `sink`'e verilir.
- Hicbir istek yolu/govde loglanmaz (log_message susturuldu).
"""

from __future__ import annotations

import json
import threading
import zlib
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Mapping

from cci.events.envelope import Envelope
from cci.ingest.allowlist import IngestGate

from .otlp_map import OtlpLogMapper
from .otlp_metrics import OtlpMetricMapper

MAX_BODY_BYTES = 1024 * 1024
Sink = Callable[[Envelope], None]

try:  # protobuf cozucu opsiyonel bagimlilik (Stage 3b)
    from .otlp_proto import decode_logs, decode_metrics  # type: ignore
    HAS_PROTO = True
except Exception:  # pragma: no cover - bagimlilik yoksa
    HAS_PROTO = False


def gunzip_bounded(body: bytes, limit: int) -> bytes | None:
    """gzip govdesini en fazla `limit` bayta acar; asarsa None.

    `gzip.decompress` once her seyi acar: 1 MB'lik bir bomba bellekte yuzlerce
    MB olur ve boyut kontrolu ancak ondan sonra gelir. Burada acma, siniri
    bir bayt gecen noktada durur. Bozuk gzip `zlib.error` firlatir.
    """
    d = zlib.decompressobj(wbits=16 + zlib.MAX_WBITS)
    out = d.decompress(body, limit + 1)
    if len(out) > limit:
        return None
    if not d.eof:
        # Girdi bitti ama akis tamamlanmadi: kesik gzip. (Sinira takilan
        # durum yukarida yakalandi; burada kalan girdi yok.)
        raise zlib.error("truncated gzip stream")
    return out


class OtlpReceiver:
    def __init__(self, sink: Sink, *, host: str = "127.0.0.1", port: int = 0,
                 max_body: int = MAX_BODY_BYTES, accept_traces: bool = False,
                 gate: IngestGate | None = None) -> None:
        if host not in ("127.0.0.1", "::1", "localhost"):
            raise ValueError("OTLP alici yalniz loopback'e baglanir")
        self.sink = sink
        self.max_body = max_body
        self.accept_traces = accept_traces
        self.gate = gate or IngestGate()
        self.logs = OtlpLogMapper()
        self.metrics = OtlpMetricMapper()
        self.counters: Counter[str] = Counter()
        self._server = ThreadingHTTPServer((host, port), self._handler_class())
        self._server.daemon_threads = True
        self._thread: threading.Thread | None = None

    # --- yasam dongusu -----------------------------------------------------
    @property
    def address(self) -> tuple[str, int]:
        host, port = self._server.server_address[:2]
        return str(host), int(port)

    @property
    def endpoint(self) -> str:
        host, port = self.address
        return f"http://{host}:{port}"

    def start(self) -> "OtlpReceiver":
        self._thread = threading.Thread(target=self._server.serve_forever, name="cci-otlp", daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    # --- isleme ---------------------------------------------------------------
    def handle(self, path: str, content_type: str, body: bytes) -> tuple[int, dict[str, Any]]:
        """(HTTP durum, JSON yanit). Test edilebilir saf-ish cekirdek."""
        ctype = content_type.split(";")[0].strip().lower()
        if path not in ("/v1/logs", "/v1/metrics", "/v1/traces"):
            self.counters["not_found"] += 1
            return 404, {"error": "unknown path"}
        if path == "/v1/traces":
            self.counters["accepted_traces" if self.accept_traces else "dropped_traces"] += 1
            return 200, {}
        if ctype == "application/x-protobuf":
            if not HAS_PROTO:
                self.counters["unsupported_protobuf"] += 1
                return 415, {"error": "protobuf decoder not installed; use OTEL_EXPORTER_OTLP_PROTOCOL=http/json"}
            doc = decode_logs(body) if path == "/v1/logs" else decode_metrics(body)  # pragma: no cover
        elif ctype in ("application/json", ""):
            try:
                doc = json.loads(body.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                self.counters["bad_request"] += 1
                return 400, {"error": "invalid json"}
        else:
            self.counters["unsupported_media"] += 1
            return 415, {"error": f"unsupported content type"}
        if not isinstance(doc, Mapping):
            self.counters["bad_request"] += 1
            return 400, {"error": "invalid body"}
        envelopes = self.logs.map_request(doc) if path == "/v1/logs" else self.metrics.map_request(doc)
        for env in envelopes:
            decision = self.gate.check(env)
            if decision.accepted:
                self.counters["accepted"] += 1
                try:
                    self.sink(env)
                except Exception:  # abone hatasi alimi dusurmez
                    self.counters["sink_error"] += 1
            else:
                self.counters[decision.reason] += 1
        self.counters["requests"] += 1
        return 200, {}

    def _handler_class(self):
        receiver = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
                return  # yol/govde loglanmaz

            def _send(self, status: int, payload: Mapping[str, Any]) -> None:
                data = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _refuse(self, status: int, counter: str, error: str) -> None:
                # Govde okunmadan donuluyor; baglanti acik kalirsa okunmamis
                # baytlar bir sonraki istek diye ayristirilir. Kapat.
                receiver.counters[counter] += 1
                self.close_connection = True
                self._send(status, {"error": error})

            def do_POST(self) -> None:  # noqa: N802
                if self.headers.get("Origin") is not None:
                    self._refuse(403, "browser_origin", "browser requests are not accepted")
                    return
                raw_len = (self.headers.get("Content-Length") or "0").strip()
                if not (raw_len.isascii() and raw_len.isdigit()):
                    self._refuse(400, "bad_request", "invalid content-length")
                    return
                length = int(raw_len)
                if length > receiver.max_body:
                    self._refuse(413, "too_large", "body too large")
                    return
                body = self.rfile.read(length) if length else b""
                if (self.headers.get("Content-Encoding") or "").lower() == "gzip":
                    try:
                        inflated = gunzip_bounded(body, receiver.max_body)
                    except zlib.error:
                        receiver.counters["bad_request"] += 1
                        self._send(400, {"error": "bad gzip"})
                        return
                    if inflated is None:
                        receiver.counters["too_large"] += 1
                        self._send(413, {"error": "body too large"})
                        return
                    body = inflated
                status, payload = receiver.handle(self.path, self.headers.get("Content-Type") or "", body)
                self._send(status, payload)

            def do_GET(self) -> None:  # noqa: N802
                if self.path == "/health":
                    self._send(200, {"status": "ok", "counters": dict(receiver.counters)})
                else:
                    self._send(404, {"error": "unknown path"})

        return Handler
