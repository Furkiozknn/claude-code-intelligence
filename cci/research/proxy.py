"""Research Mode proxy: Claude Code -> 127.0.0.1:<port> -> api.anthropic.com (ANTHROPIC_BASE_URL).

- Akis korunur (chunk chunk aktarilir); istek/yanit degistirilmez.
- Diske YALNIZ meta yazilir (`requests.jsonl`): zaman, yol, durum, boyutlar, model, rate-limit basliklari.
  `authorization`, `x-api-key`, `proxy-authorization`, `cookie` hicbir zaman yazilmaz.
- Govdeler yalniz `capture_bodies=True` ile `bodies/` altina (arastirma dizini, 0700, 7 gun).
- Rate-limit basliklari (`anthropic-ratelimit-unified-*`) -> QuotaSnapshot{source=rate_limit_headers}
  (utilization 0-1, reset unix s) - cagirana verilir; cekirdek depoya yazip yazmamak cagiranin karari.
Kaynak: notes/02 §E (CodeZeno claude.rs, claude-meter normalizer.go), claude-meter proxy iskeleti.
"""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import threading
import time
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import urlparse

from cci.model.evidence import EvidenceClass
from cci.model.ids import AccountRef
from cci.model.quota import SESSION_5H_S, WEEKLY_S, QuotaSnapshot, QuotaWindow, WindowScope

SECRET_HEADERS = frozenset({"authorization", "x-api-key", "proxy-authorization", "cookie", "set-cookie"})
HOP_HEADERS = frozenset({"connection", "keep-alive", "transfer-encoding", "te", "trailer", "upgrade", "proxy-connection"})
RL_PREFIX = "anthropic-ratelimit-unified-"
QuotaSink = Callable[[QuotaSnapshot], None]


def sanitize_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {k.lower(): v for k, v in headers.items() if k.lower() not in SECRET_HEADERS}


def _f(v: str | None) -> float | None:
    try:
        return float(v) if v is not None else None
    except ValueError:
        return None


def headers_to_quota_snapshot(headers: Mapping[str, str], *, fetched_at: datetime, account: AccountRef | None,
                              provider: str = "anthropic") -> QuotaSnapshot | None:
    """`anthropic-ratelimit-unified-{5h,7d}-{utilization,reset,status}` -> snapshot. Yoksa None."""
    h = {k.lower(): v for k, v in headers.items()}
    windows: list[QuotaWindow] = []
    for key, dur in (("5h", SESSION_5H_S), ("7d", WEEKLY_S)):
        util = _f(h.get(f"{RL_PREFIX}{key}-utilization"))
        if util is None:
            continue
        reset = _f(h.get(f"{RL_PREFIX}{key}-reset"))
        status = h.get(f"{RL_PREFIX}{key}-status")
        sev = {"allowed": "normal", "allowed_warning": "warning", "rejected": "critical"}.get(str(status or "").lower())
        windows.append(QuotaWindow(kind="unclassified", duration_s=dur, utilization=min(max(util, 0.0), 1.0),
                                   resets_at=datetime.fromtimestamp(reset, UTC) if reset else None,
                                   scope=WindowScope(), severity=sev))
    if not windows:
        return None
    raw = "|".join(f"{k}={v}" for k, v in sorted(h.items()) if k.startswith(RL_PREFIX)).encode("utf-8")
    return QuotaSnapshot.build(snapshot_id=f"{provider}:headers:{fetched_at.isoformat()}", provider=provider, account=account,
                               fetched_at=fetched_at, source="rate_limit_headers", raw_hash=hashlib.sha256(raw).hexdigest(),
                               windows=windows, evidence_class=EvidenceClass.OBSERVED)


class ResearchProxy:
    def __init__(self, *, research_dir: Path, upstream: str = "https://api.anthropic.com", port: int = 0,
                 capture_bodies: bool = False, quota_sink: QuotaSink | None = None, account: AccountRef | None = None,
                 timeout_s: float = 600.0) -> None:
        self.research_dir = research_dir
        self.upstream = urlparse(upstream)
        self.capture_bodies = capture_bodies
        self.quota_sink = quota_sink
        self.account = account
        self.timeout_s = timeout_s
        self.counters: dict[str, int] = {"requests": 0, "errors": 0, "quota_headers": 0, "bodies": 0}
        research_dir.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            try:
                os.chmod(research_dir, 0o700)
            except OSError:
                pass
        self._log = research_dir / "requests.jsonl"
        self._lock = threading.Lock()
        self._server = ThreadingHTTPServer(("127.0.0.1", port), self._handler_class())
        self._server.daemon_threads = True

    @property
    def address(self) -> tuple[str, int]:
        h, p = self._server.server_address[:2]
        return str(h), int(p)

    @property
    def base_url(self) -> str:
        h, p = self.address
        return f"http://{h}:{p}"

    def start(self) -> "ResearchProxy":
        threading.Thread(target=self._server.serve_forever, name="cci-research-proxy", daemon=True).start()
        return self

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    def _record(self, meta: Mapping[str, Any]) -> None:
        with self._lock, self._log.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(meta, ensure_ascii=False, sort_keys=True) + "\n")

    def _save_body(self, kind: str, req_id: str, data: bytes) -> str | None:
        if not self.capture_bodies or not data:
            return None
        bdir = self.research_dir / "bodies"
        bdir.mkdir(exist_ok=True)
        path = bdir / f"{req_id}.{kind}.bin"
        path.write_bytes(data)
        self.counters["bodies"] += 1
        return path.name

    def forward(self, method: str, path: str, headers: Mapping[str, str], body: bytes,
                write: Callable[[int, list[tuple[str, str]]], Callable[[bytes], None]]) -> None:
        """Upstream'e ilet; `write(status, headers)` -> chunk yazici doner (akis)."""
        started = time.monotonic()
        req_id = hashlib.sha256(f"{started}{path}".encode()).hexdigest()[:16]
        model = None
        try:
            doc = json.loads(body.decode("utf-8")) if body else None
            if isinstance(doc, dict) and isinstance(doc.get("model"), str):
                model = doc["model"]
        except (ValueError, UnicodeDecodeError):
            pass
        conn_cls = http.client.HTTPSConnection if self.upstream.scheme == "https" else http.client.HTTPConnection
        conn = conn_cls(self.upstream.hostname, self.upstream.port, timeout=self.timeout_s)
        fwd = {k: v for k, v in headers.items() if k.lower() not in HOP_HEADERS and k.lower() != "host"}
        fwd["Host"] = self.upstream.netloc
        status = 502
        resp_headers: dict[str, str] = {}
        resp_size = 0
        try:
            conn.request(method, path, body=body if body else None, headers=fwd)
            resp = conn.getresponse()
            status = resp.status
            resp_headers = {k: v for k, v in resp.getheaders()}
            out_headers = [(k, v) for k, v in resp_headers.items() if k.lower() not in HOP_HEADERS and k.lower() != "content-length"]
            writer = write(status, out_headers)
            captured = bytearray()
            while True:
                chunk = resp.read(4096)
                if not chunk:
                    break
                resp_size += len(chunk)
                if self.capture_bodies:
                    captured.extend(chunk)
                writer(chunk)
            writer(b"")
            self._save_body("response", req_id, bytes(captured))
        except Exception as exc:
            self.counters["errors"] += 1
            try:
                writer = write(502, [("Content-Type", "application/json")])
                writer(json.dumps({"error": "upstream unreachable", "kind": type(exc).__name__}).encode())
                writer(b"")
            except Exception:
                pass
        finally:
            conn.close()
        self.counters["requests"] += 1
        now = datetime.now(UTC)
        snap = headers_to_quota_snapshot(resp_headers, fetched_at=now, account=self.account) if resp_headers else None
        if snap is not None:
            self.counters["quota_headers"] += 1
            if self.quota_sink is not None:
                try:
                    self.quota_sink(snap)
                except Exception:
                    pass
        self._save_body("request", req_id, body)
        self._record({"ts": now.isoformat(), "req_id": req_id, "method": method, "path": path, "status": status,
                      "model": model, "request_bytes": len(body), "response_bytes": resp_size,
                      "duration_ms": round((time.monotonic() - started) * 1000),
                      "rate_limit": {k: v for k, v in sanitize_headers(resp_headers).items() if k.startswith(RL_PREFIX) or k == "retry-after"},
                      "request_headers": sorted(k.lower() for k in headers if k.lower() not in SECRET_HEADERS)})

    def _handler_class(self):
        proxy = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
                return

            def _handle(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length) if length else b""
                handler = self

                def write(status: int, headers: list[tuple[str, str]]) -> Callable[[bytes], None]:
                    handler.send_response(status)
                    for k, v in headers:
                        handler.send_header(k, v)
                    handler.send_header("Transfer-Encoding", "chunked")
                    handler.end_headers()

                    def chunk(data: bytes) -> None:
                        if data:
                            handler.wfile.write(f"{len(data):x}\r\n".encode() + data + b"\r\n")
                        else:
                            handler.wfile.write(b"0\r\n\r\n")
                        handler.wfile.flush()
                    return chunk

                proxy.forward(self.command, self.path, dict(self.headers.items()), body, write)

            do_POST = do_GET = do_PUT = do_DELETE = do_PATCH = _handle

        return Handler
