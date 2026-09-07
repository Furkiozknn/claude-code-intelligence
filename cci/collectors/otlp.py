"""OTLP HTTP alicisi (loopback). docs/PROVIDERS.md §4, ARCHITECTURE.md §9.

- `/v1/logs` (birincil), `/v1/metrics` (capraz dogrulama), `/v1/traces` (Core disi:
  200 + `dropped_traces` sayaci; R-2).
- Icerik turu: `application/json` (OTLP/JSON). `application/x-protobuf` icin
  protobuf cozucu yoksa DURUST 415 doner (sessiz "200 OK" yok - zcquant anti-kalibi).
- Govde <= 1 MB (413), gzip desteklenir, bozuk JSON 400.
- Her olay ingest kapisindan gecer; kabul edilenler `sink`'e verilir.
- Hicbir istek yolu/govde loglanmaz (log_message susturuldu).
"""

from __future__ import annotations

import gzip
import json
import threading
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

            def do_POST(self) -> None:  # noqa: N802
                try:
                    length = int(self.headers.get("Content-Length") or 0)
                except ValueError:
                    length = 0
                if length > receiver.max_body:
                    receiver.counters["too_large"] += 1
                    self._send(413, {"error": "body too large"})
                    return
                body = self.rfile.read(length) if length else b""
                if (self.headers.get("Content-Encoding") or "").lower() == "gzip":
                    try:
                        body = gzip.decompress(body)
                    except OSError:
                        receiver.counters["bad_request"] += 1
                        self._send(400, {"error": "bad gzip"})
                        return
                    if len(body) > receiver.max_body:
                        receiver.counters["too_large"] += 1
                        self._send(413, {"error": "body too large"})
                        return
                status, payload = receiver.handle(self.path, self.headers.get("Content-Type") or "", body)
                self._send(status, payload)

            def do_GET(self) -> None:  # noqa: N802
                if self.path == "/health":
                    self._send(200, {"status": "ok", "counters": dict(receiver.counters)})
                else:
                    self._send(404, {"error": "unknown path"})

        return Handler
