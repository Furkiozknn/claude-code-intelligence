"""Stage 9 - loopback HTTP API + statik web panosu (docs/PRODUCT.md §3, PRIVACY §5).

- Yalniz 127.0.0.1; her API istegi `X-CCI-Token` basligini ister (token dosyasi
  `api_token`, 0600, ilk baslatmada uretilir). Token URL SORGU DIZESINE
  konmaz; pano onu adres fragment'inden okur (bkz. `ApiServer.url`).
- `GET /`            -> satir ici HTML/JS pano (CDN yok, CSP: default-src 'none')
- `GET /health`      -> token gerektirmez; yalniz {"status":"ok"}
- `GET /api/v1/snapshot|today|sessions|session/<id>|quota|doctor`
- Veri: snapshot dosyasi + istek basina salt okunur depo (thread guvenligi icin).
- Yol/govde loglanmaz.
"""

from __future__ import annotations

import base64
import hashlib
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

DataFn = Callable[[str, str | None], Any]   # (kaynak adi, kimlik) -> JSON'lanabilir nesne | None


def _csp_hash(source: str) -> str:
    """CSP3 `'sha256-...'` kaynak ifadesi - satir ici <style>/<script> icin.

    Sayfa degismez bir sabit oldugu icin karma da sabittir; hash ile
    'unsafe-inline' kaldirilabiliyor, yani bir yerden enjekte edilen ikinci
    bir <script> artik calismiyor. Karma metnin uzerinden ANINDA hesaplanir,
    elle yazilmaz: elle yazilan bir karma sessizce eskir ve pano bos acilir.
    """
    digest = hashlib.sha256(source.encode("utf-8")).digest()
    return "'sha256-" + base64.b64encode(digest).decode("ascii") + "'"


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


DASHBOARD_CSS = """
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
"""

# Panodaki HER dinamik deger taranmis transcript'lerden gelir - yani baska bir
# programin yazdigi metindir. Bu metin daha once innerHTML ile birlestiriliyordu:
# bir model adi, bir uyari mesaji ya da bir Figure metni icine yazilan
# "<img src=x onerror=...>" panoda CALISIYORDU ve panonun API token'i ayni
# origin'de duruyordu. Bu yuzden asagida tek bir innerHTML yok: her deger
# textContent ile metin dugumu olarak yazilir, yapinin tamami createElement ile
# kurulur. Bu kural bozulursa CSP ikinci savunma hattidir (bkz. CSP sabiti).
DASHBOARD_JS = """
// Token adres FRAGMENT'inden gelir, sorgu dizesinden degil. Fragment sunucuya
// hicbir zaman gonderilmez: erisim gunlugune de, Referer basligina da dusmez.
// Okunur okunmaz sessionStorage'a alinip replaceState ile adres cubugundan
// silinir, boylece gecmis girdisinde ve paylasilan bir ekran goruntusunde de
// kalmaz. Yenilemede sessionStorage'daki kopya kullanilir.
function readToken(){
  let t='';
  try{t=sessionStorage.getItem('cci_token')||''}catch(e){}
  const fromHash=new URLSearchParams(location.hash.replace(/^#/,'')).get('token');
  if(fromHash){
    t=fromHash;
    try{sessionStorage.setItem('cci_token',t)}catch(e){}
    history.replaceState(null,'',location.pathname);
  }
  return t;
}
const token=readToken();
const badge={observed:'\\u25cf',derived:'\\u25d0',vendor_estimated:'\\u2248',estimated:'\\u2248',predicted:'~',inferred:'?'};
function fig(f){return f?(f.text+(f.released?'':' ('+(f.withheld_because||'')+')')):'-'}

function el(tag,cls,text){
  const n=document.createElement(tag);
  if(cls)n.className=cls;
  if(text!==undefined&&text!==null)n.textContent=String(text);
  return n;
}
function txt(s){return document.createTextNode(String(s))}
function fill(id,nodes){document.getElementById(id).replaceChildren(...nodes)}
// Sinif adi da veriden geliyor. Metin dugumu olmadigi icin kacisi ayrica
// yapilir: harf/rakam disindaki her sey atilir ki veri yeni bir secici -
// ya da bir tirnak kacisi - uyduramasin.
function slug(v){return String(v).replace(/[^a-z0-9_-]/gi,'')}

function quotaRow(w){
  const pct=w.utilization_pct==null?null:w.utilization_pct;
  const cls=pct>=90?'crit':pct>=70?'warn':'';
  const row=el('div');
  row.append(txt(w.kind+(w.model?' ['+w.model+']':'')+' '));
  row.append(el('b',null,pct==null?'--':pct+'%'+(w.badge||'')));
  if(w.pace)row.append(txt(' '+(w.pace.delta_pct>0?'\\u21e1':'\\u21e3')+Math.abs(w.pace.delta_pct)+'%\\u25d0 '+w.pace.stage+(w.pace.eta_s?(' ~'+Math.round(w.pace.eta_s/60)+' dk'):'')));
  if(w.stale)row.append(el('span','muted',' (eski)'));
  const bar=el('div',cls?'bar '+cls:'bar');
  const meter=el('i');
  // CSSOM uzerinden, style= ozniteligi ile degil: oznitelik yazmak CSP'nin
  // style-src karmasina takilirdi, bu atama takilmaz.
  meter.style.width=(Number(pct)||0)+'%';
  bar.append(meter);
  row.append(bar);
  return row;
}

function row(cells,tag){
  const tr=el('tr');
  for(const c of cells)tr.append(el(tag||'td',null,c));
  return tr;
}
function todayNodes(t){
  const head=el('table');
  head.append(row(['istek','token','maliyet','sat\\u0131c\\u0131'],'th'));
  head.append(row([t.requests,t.tokens.input_total.toLocaleString()+' / '+t.tokens.output.toLocaleString(),fig(t.cost)+'\\u2248',fig(t.vendor_cost)]));
  const models=el('table');
  for(const m of (t.models||[]))models.append(row([m.display,m.requests,fig(m.cost)]));
  const nodes=[head,models];
  if(!t.conservation_ok)nodes.push(el('b','att-critical','koruma yasas\\u0131 ihlali'));
  return nodes;
}

function alertNode(x){
  const d=el('div');
  d.append(el('b',null,x.severity));
  d.append(txt(' '+x.rule_id+': '+x.message));
  return d;
}

async function load(){
  const r=await fetch('/api/v1/snapshot',{headers:{'X-CCI-Token':token}});
  if(!r.ok){document.getElementById('att').textContent='yetkisiz ('+r.status+')';return}
  const s=await r.json();
  document.getElementById('gen').textContent=' \\u00b7 '+s.generated_at;
  const q=s.quota||{};
  document.getElementById('qmeta').textContent=q.placeholder?q.placeholder:('kaynak '+q.source+' \\u00b7 '+Math.round(q.age_s||0)+' sn \\u00f6nce'+(q.authoritative===false?' \\u00b7 authoritative=false!':''));
  const windows=(q.windows||[]).map(quotaRow);
  fill('quota',windows.length?windows:[el('span','muted','--')]);
  const a=s.attention||'ok';
  fill('att',[el('span','att-'+slug(a),a)]);
  if(s.today)fill('today',todayNodes(s.today));
  const alerts=(s.alerts||[]).map(alertNode);
  fill('alerts',alerts.length?alerts:[txt('yok')]);
  document.getElementById('health').textContent=JSON.stringify(s.health||{},null,1);
  const next=new Date(s.next_display_change_at)-Date.now();
  setTimeout(load,Math.min(Math.max(next,5000),60000));
}
load();
"""

DASHBOARD_HTML = (
    '<!doctype html><html lang="tr"><head><meta charset="utf-8"><title>cci</title>\n'
    '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
    "<style>" + DASHBOARD_CSS + "</style></head><body>\n"
    '<h1>CLAUDE CODE INTELLIGENCE <span id="gen" class="muted"></span></h1>\n'
    '<section><b>Kota</b> <span id="qmeta" class="muted"></span><div id="quota"></div></section>\n'
    '<section><b>Dikkat</b>: <span id="att"></span></section>\n'
    '<section><b>Bugün</b><div id="today" class="muted">veri yok</div></section>\n'
    '<section><b>Uyarılar</b><div id="alerts" class="muted">yok</div></section>\n'
    '<section><b>Sağlık</b><pre id="health" class="muted"></pre></section>\n'
    "<script>" + DASHBOARD_JS + "</script></body></html>"
)

# 'unsafe-inline' yerine karma. Eskiden script-src 'unsafe-inline' idi, yani
# sayfaya bir sekilde giren HER satir ici script calisirdi - panonun DOM'u
# taranmis transcript'lerden geliyorken bu, XSS icin ikinci savunma hattinin
# hic olmamasi demekti. Karma yalniz asagidaki iki sabit bloga izin verir.
CSP = (
    "default-src 'none'; "
    f"script-src {_csp_hash(DASHBOARD_JS)}; "
    f"style-src {_csp_hash(DASHBOARD_CSS)}; "
    "connect-src 'self'; img-src data:; base-uri 'none'; form-action 'none'"
)


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
        """Operatore basilan adres. Token FRAGMENT'te, sorgu dizesinde degil.

        `?token=...` tarayici gecmisine, Referer basligina ve onunde bir sey
        varsa erisim gunlugune dusuyordu - loopback'te bile bu, token'i disari
        sizdiran uc ayri yoldur. Fragment sunucuya hic gonderilmez; pano onu
        okur okumaz adres cubugundan da siler (readToken).
        """
        h, p = self.address
        return f"http://{h}:{p}/#token={self.token}"

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
        # Yalniz baslik. `?token=` kabul edildigi surece token bir URL'de
        # tasinabiliyordu, ve URL'ler gecmise, Referer'a ve gunluklere yazilir.
        # `query` imzada kaliyor: yol/sorgu ayristirmasi cagiranin isi degil.
        supplied = token_header
        if not supplied or not secrets.compare_digest(str(supplied), self.token):
            self.unauthorized += 1
            return 401, {"error": "token gerekli (X-CCI-Token basligi)"}, "application/json"
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
