"""Stage 9 - loopback HTTP API + statik web panosu (docs/PRODUCT.md §3, PRIVACY §5).

- Yalniz 127.0.0.1; her API istegi `X-CCI-Token` basligi ya da `?token=` ister
  (token dosyasi `api_token`, 0600, ilk baslatmada uretilir).
- `GET /`            -> satir ici HTML/JS pano (CDN yok, CSP: default-src 'none')
- `GET /health`      -> token gerektirmez; yalniz {"status":"ok"}
- `GET /api/v1/snapshot|today|sessions|session/<id>|quota|doctor`
- Veri: snapshot dosyasi + istek basina salt okunur depo (thread guvenligi icin).
- Yol/govde loglanmaz.
"""

from __future__ import annotations

import json
import secrets
import threading
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import parse_qs, urlparse

from cci import __version__
from cci.api.snapshot import read_snapshot

CSP = "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; img-src data:"
DataFn = Callable[[str, str | None], Any]   # (kaynak adi, kimlik) -> JSON'lanabilir nesne | None


def load_or_create_token(path: Path) -> str:
    try:
        tok = path.read_text(encoding="utf-8").strip()
        if len(tok) >= 32:
            return tok
    except OSError:
        pass
    tok = secrets.token_urlsafe(32)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(tok, encoding="utf-8")
    try:
        import os
        if os.name != "nt":
            os.chmod(path, 0o600)
    except OSError:
        pass
    return tok


DASHBOARD_HTML = """<!doctype html><html lang="tr"><head><meta charset="utf-8"><title>cci</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{color-scheme:light dark;font-family:system-ui,sans-serif;--ok:#2e7d32;--warn:#ef6c00;--crit:#c62828;--muted:#777}
body{margin:0;padding:1rem;max-width:960px;margin-inline:auto}
h1{font-size:1.1rem;margin:.2rem 0 1rem}
section{border:1px solid #8884;border-radius:8px;padding:.8rem 1rem;margin-bottom:.8rem}
.bar{height:10px;background:#8883;border-radius:5px;overflow:hidden;margin:.2rem 0}
.bar i{display:block;height:100%;background:var(--ok)}
.warn i{background:var(--warn)}.crit i{background:var(--crit)}
.muted{color:var(--muted);font-size:.85rem}
table{border-collapse:collapse;width:100%}td,th{text-align:left;padding:.2rem .4rem;border-bottom:1px solid #8883;font-size:.9rem}
.badge{font-family:monospace}
.att-ok{color:var(--ok)}.att-warning,.att-cost,.att-latency,.att-loops{color:var(--warn)}.att-critical,.att-failures,.att-context{color:var(--crit)}
</style></head><body>
<h1>CLAUDE CODE INTELLIGENCE <span id="gen" class="muted"></span></h1>
<section><b>Kota</b> <span id="qmeta" class="muted"></span><div id="quota"></div></section>
<section><b>Dikkat</b>: <span id="att"></span></section>
<section><b>Bugün</b><div id="today" class="muted">veri yok</div></section>
<section><b>Uyarılar</b><div id="alerts" class="muted">yok</div></section>
<section><b>Sağlık</b><pre id="health" class="muted"></pre></section>
<script>
const token=new URLSearchParams(location.search).get('token')||'';
const badge={observed:'●',derived:'◐',vendor_estimated:'≈',estimated:'≈',predicted:'~',inferred:'?'};
function fig(f){return f?(f.text+(f.released?'':' ('+(f.withheld_because||'')+')')):'-'}
async function load(){
  const r=await fetch('/api/v1/snapshot',{headers:{'X-CCI-Token':token}});
  if(!r.ok){document.getElementById('att').textContent='yetkisiz ('+r.status+')';return}
  const s=await r.json();
  document.getElementById('gen').textContent=' · '+s.generated_at;
  const q=s.quota||{};document.getElementById('qmeta').textContent=q.placeholder?q.placeholder:('kaynak '+q.source+' · '+Math.round(q.age_s||0)+' sn önce'+(q.authoritative===false?' · authoritative=false!':''));
  document.getElementById('quota').innerHTML=(q.windows||[]).map(w=>{
    const pct=w.utilization_pct==null?null:w.utilization_pct;const cls=pct>=90?'crit':pct>=70?'warn':'';
    const pace=w.pace?(' '+(w.pace.delta_pct>0?'⇡':'⇣')+Math.abs(w.pace.delta_pct)+'%◐ '+w.pace.stage+(w.pace.eta_s?(' ~'+Math.round(w.pace.eta_s/60)+' dk'):'')):'';
    return '<div>'+w.kind+(w.model?' ['+w.model+']':'')+' <b>'+(pct==null?'--':pct+'%'+w.badge)+'</b>'+pace+(w.stale?' <span class=muted>(eski)</span>':'')+'<div class="bar '+cls+'"><i style="width:'+(pct||0)+'%"></i></div></div>'}).join('')||'<span class=muted>--</span>';
  const a=s.attention||'ok';document.getElementById('att').innerHTML='<span class="att-'+a+'">'+a+'</span>';
  if(s.today){const t=s.today;document.getElementById('today').innerHTML='<table><tr><th>istek</th><th>token</th><th>maliyet</th><th>satıcı</th></tr><tr><td>'+t.requests+'</td><td>'+t.tokens.input_total.toLocaleString()+' / '+t.tokens.output.toLocaleString()+'</td><td>'+fig(t.cost)+'≈</td><td>'+fig(t.vendor_cost)+'</td></tr></table>'+
    '<table>'+(t.models||[]).map(m=>'<tr><td>'+m.display+'</td><td>'+m.requests+'</td><td>'+fig(m.cost)+'</td></tr>').join('')+'</table>'+(t.conservation_ok?'':'<b class=att-critical>koruma yasası ihlali</b>')}
  document.getElementById('alerts').innerHTML=(s.alerts||[]).map(x=>'<div><b>'+x.severity+'</b> '+x.rule_id+': '+x.message+'</div>').join('')||'yok';
  document.getElementById('health').textContent=JSON.stringify(s.health||{},null,1);
  const next=new Date(s.next_display_change_at)-Date.now();setTimeout(load,Math.min(Math.max(next,5000),60000));
}
load();
</script></body></html>"""


class ApiServer:
    def __init__(self, *, snapshot_path: Path, token: str, data: DataFn, host: str = "127.0.0.1", port: int = 0) -> None:
        if host not in ("127.0.0.1", "::1", "localhost"):
            raise ValueError("API yalniz loopback'e baglanir")
        self.snapshot_path = snapshot_path
        self.token = token
        self.data = data
        self.requests = 0
        self.unauthorized = 0
        self._server = ThreadingHTTPServer((host, port), self._handler_class())
        self._server.daemon_threads = True
        self._thread: threading.Thread | None = None

    @property
    def address(self) -> tuple[str, int]:
        h, p = self._server.server_address[:2]
        return str(h), int(p)

    @property
    def url(self) -> str:
        h, p = self.address
        return f"http://{h}:{p}/?token={self.token}"

    def start(self) -> "ApiServer":
        self._thread = threading.Thread(target=self._server.serve_forever, name="cci-api", daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    def route(self, path: str, query: Mapping[str, list[str]], token_header: str | None) -> tuple[int, Any, str]:
        """(durum, govde, icerik turu). Saf-ish; testlerde dogrudan cagrilir."""
        if path == "/health":
            return 200, {"status": "ok", "version": __version__}, "application/json"
        if path == "/":
            return 200, DASHBOARD_HTML, "text/html; charset=utf-8"
        supplied = token_header or (query.get("token") or [None])[0]
        if not supplied or not secrets.compare_digest(str(supplied), self.token):
            self.unauthorized += 1
            return 401, {"error": "token gerekli (X-CCI-Token ya da ?token=)"}, "application/json"
        self.requests += 1
        if path == "/api/v1/snapshot":
            snap = read_snapshot(self.snapshot_path)
            return (200, snap, "application/json") if snap else (404, {"error": "snapshot yok"}, "application/json")
        if path.startswith("/api/v1/"):
            rest = path[len("/api/v1/"):]
            name, _, ident = rest.partition("/")
            if name in ("today", "sessions", "session", "quota", "doctor"):
                try:
                    body = self.data(name, ident or None)
                except Exception as exc:  # icerik yok; sinif adi yeter
                    return 500, {"error": type(exc).__name__}, "application/json"
                return (200, body, "application/json") if body is not None else (404, {"error": "yok"}, "application/json")
        return 404, {"error": "unknown path"}, "application/json"

    def _handler_class(self):
        api = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
                return

            def do_GET(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                status, body, ctype = api.route(parsed.path, parse_qs(parsed.query), self.headers.get("X-CCI-Token"))
                data = (body if isinstance(body, str) else json.dumps(body, ensure_ascii=False, default=str)).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Content-Security-Policy", CSP)
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(data)

        return Handler
