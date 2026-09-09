# -*- coding: utf-8 -*-
"""README gorsellerini uretir: assets/banner.svg ve assets/terminal.svg.

Neden bir betik ve neden depoda: terminal gorseli GERCEK `cci daily`
ciktisindan uretiliyor. Elle cizilmis bir ekran goruntusu, cikti degistigi
anda sessizce yalan olur; bu betik yeniden calistirilinca dogruyu yazar.

Yazi tipi kardes depolarin banner'larindaki gomulu JetBrains Mono'dan
aliniyor, boylece ekosistemin gorunumu tek parca kaliyor ve burada ikinci
bir font kopyasi tutulmuyor.

Kullanim:
    python scripts/gorsel-uret.py            # gercek `cci daily` cikti alir
    python scripts/gorsel-uret.py cikti.txt  # hazir bir ciktidan uretir
"""
from __future__ import annotations

import html
import re
import subprocess
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
ASSETS = KOK / "assets"
# Kardes depolardan biri; yalniz gomulu @font-face bloklari icin okunuyor.
FONT_KAYNAGI = KOK.parent / "mcp-vet" / "assets" / "banner.svg"

# Kimlik: gozlem/olcum araci -> mavi-kehribar. projects.svg'de bu depo
# "TOOLING & INFRASTRUCTURE" sutununda ve #6cb6ff ile isaretli.
MAVI, KEHRIBAR, YESIL, KIRMIZI = "#6cb6ff", "#ffd76d", "#6dff9e", "#ff7b72"
METIN, SOLUK, COK_SOLUK = "#e6edf3", "#9aa4b2", "#6b7280"


def font_bloklari() -> str:
    """Kardes banner'daki iki @font-face blogunu oldugu gibi al."""
    if not FONT_KAYNAGI.exists():
        return ""  # font yoksa Consolas'a duser, gorsel yine calisir
    s = FONT_KAYNAGI.read_text(encoding="utf-8")
    return "\n".join(m.group(0) for m in re.finditer(r"@font-face\s*\{.*?\}", s, re.S))


def daily_ciktisi(argv: list[str]) -> list[str]:
    if len(argv) > 1:
        ham = Path(argv[1]).read_text(encoding="utf-8")
    else:
        exe = KOK / ".venv" / "Scripts" / "cci.exe"
        cmd = [str(exe)] if exe.exists() else [sys.executable, "-m", "cci.cli"]
        ham = subprocess.run(cmd + ["daily"], capture_output=True, text=True,
                             encoding="utf-8", cwd=KOK).stdout
    satirlar = [s.rstrip() for s in ham.splitlines() if s.strip()]
    if not satirlar:
        raise SystemExit("cci daily bos dondu - once `cci scan` calistir")
    return satirlar[-11:]          # son gunler, gorsele sigacak kadar


def renklendir(satir: str) -> str:
    """Bir cikti satirini renkli <tspan>'lere cevir.

    Kural basit ve kasitli: rakamlar ve para one cikar, "withheld" gibi
    durum sozleri soluk kalir. Amac ciktiyi susleme degil, ekranda
    okundugu gibi gostermek.
    """
    parcalar: list[str] = []
    for tok in re.split(r"(\s+)", satir):
        if not tok:
            continue
        if tok.isspace():
            parcalar.append(html.escape(tok).replace(" ", "&#160;"))
            continue
        e = html.escape(tok)
        if tok.startswith("$"):
            renk = KEHRIBAR
        elif tok == "✓":
            renk = YESIL
        elif tok == "✗":
            renk = KIRMIZI
        elif re.fullmatch(r"\d{4}-\d{2}-\d{2}", tok):
            renk = MAVI
        elif re.fullmatch(r"[\d,]+", tok):
            renk = METIN
        elif tok.startswith("[") or tok.endswith("]"):
            renk = COK_SOLUK
        else:
            renk = SOLUK
        parcalar.append(f'<tspan fill="{renk}">{e}</tspan>')
    return "".join(parcalar)


def terminal_svg(satirlar: list[str]) -> str:
    sat_y, ust, alt, sol = 19, 62, 22, 26
    yuk = ust + len(satirlar) * sat_y + alt
    gen = 1200
    govde = "\n".join(
        f'    <text x="{sol}" y="{ust + i * sat_y}" xml:space="preserve">{renklendir(s)}</text>'
        for i, s in enumerate(satirlar)
    )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {gen} {yuk}" width="{gen}" height="{yuk}" role="img" aria-label="cci daily komutunun gercek ciktisi: gun basina istek, token ve tahmini maliyet, model kirilimiyla">
  <defs><style>{font_bloklari()}</style></defs>
  <rect width="{gen}" height="{yuk}" rx="10" fill="#0d1117" stroke="#30363d" stroke-width="1.4"/>
  <rect width="{gen}" height="36" rx="10" fill="#161b22"/>
  <rect y="26" width="{gen}" height="10" fill="#161b22"/>
  <line x1="0" y1="36" x2="{gen}" y2="36" stroke="#30363d" stroke-width="1"/>
  <g><circle cx="22" cy="18" r="5.5" fill="#ff5f57"/><circle cx="42" cy="18" r="5.5" fill="#febc2e"/><circle cx="62" cy="18" r="5.5" fill="#28c840"/></g>
  <text x="88" y="23" font-family="'JetBrains Mono', Consolas, monospace" font-size="12.5" fill="{COK_SOLUK}">cci daily</text>
  <g font-family="'JetBrains Mono', Consolas, monospace" font-size="13.5">
{govde}
  </g>
</svg>
"""


def banner_svg() -> str:
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 320" width="1200" height="320" role="img" aria-label="claude-code-intelligence - nereye gitti, ne tuttu, ne zaman bitiyor">
  <defs>
    <style>{font_bloklari()}</style>
    <radialGradient id="bg" cx="50%" cy="40%" r="80%">
      <stop offset="0%" stop-color="#101a26"/><stop offset="60%" stop-color="#0b1017"/><stop offset="100%" stop-color="#070a0e"/>
    </radialGradient>
    <linearGradient id="title" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#9ed0ff"/><stop offset="55%" stop-color="{MAVI}"/><stop offset="100%" stop-color="{KEHRIBAR}"/>
    </linearGradient>
    <filter id="glow" x="-80%" y="-80%" width="260%" height="260%">
      <feGaussianBlur stdDeviation="7" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
    <pattern id="grid" width="34" height="34" patternUnits="userSpaceOnUse">
      <path d="M34 0H0V34" fill="none" stroke="{MAVI}" stroke-opacity="0.05" stroke-width="1"/>
    </pattern>
  </defs>

  <rect width="1200" height="320" fill="url(#bg)"/>
  <rect width="1200" height="320" fill="url(#grid)"/>
  <g fill="{MAVI}" opacity="0.06"><circle cx="190" cy="250" r="140"/><circle cx="1030" cy="70" r="115"/></g>

  <g font-family="'JetBrains Mono', Consolas, monospace" font-size="13" letter-spacing="0.5">
    <rect x="36" y="30" width="150" height="28" rx="14" fill="none" stroke="{MAVI}" stroke-opacity="0.5" stroke-width="1.2"/>
    <text x="111" y="48" text-anchor="middle" fill="{MAVI}">local-first</text>
    <rect x="1014" y="30" width="150" height="28" rx="14" fill="none" stroke="{KEHRIBAR}" stroke-opacity="0.5" stroke-width="1.2"/>
    <text x="1089" y="48" text-anchor="middle" fill="{KEHRIBAR}">MIT licensed</text>
  </g>

  <!-- olcum motifi: yukselen sutunlar + tavan cizgisi. Kota tam da bu:
       biriken kullanim ve uzerinde durmayan bir sinir. -->
  <g transform="translate(96,118)" filter="url(#glow)">
    <g fill="{MAVI}" opacity="0.85">
      <rect x="0"  y="74" width="15" height="34" rx="3"/>
      <rect x="24" y="56" width="15" height="52" rx="3"/>
      <rect x="48" y="30" width="15" height="78" rx="3"/>
      <rect x="72" y="44" width="15" height="64" rx="3"/>
      <rect x="96" y="12" width="15" height="96" rx="3"/>
    </g>
    <path d="M-6 6 L117 6" stroke="{KEHRIBAR}" stroke-width="2.5" stroke-dasharray="7 6" stroke-linecap="round"/>
    <text x="123" y="11" font-family="'JetBrains Mono', Consolas, monospace" font-size="12" fill="{KEHRIBAR}">kota</text>
  </g>

  <text x="266" y="152" font-family="'JetBrains Mono', Consolas, monospace" font-size="52" font-weight="700" fill="url(#title)">claude-code-intelligence</text>
  <text x="268" y="192" font-family="'JetBrains Mono', Consolas, monospace" font-size="17" fill="{METIN}" opacity="0.9">Token nereye gitti, ne tuttu, kota ne zaman bitiyor.</text>
  <text x="268" y="220" font-family="'JetBrains Mono', Consolas, monospace" font-size="14" fill="{SOLUK}">Hepsi yerelde. Tahmin edilen rakam tahmin diye isaretlenir.</text>

  <g font-family="'JetBrains Mono', Consolas, monospace" font-size="13" fill="{COK_SOLUK}">
    <text x="268" y="262">OTLP alici</text>
    <text x="378" y="262">·</text><text x="398" y="262">transcript tarama</text>
    <text x="558" y="262">·</text><text x="578" y="262">kota takibi</text>
    <text x="688" y="262">·</text><text x="708" y="262">256 test</text>
  </g>
  <line x1="268" y1="278" x2="800" y2="278" stroke="{MAVI}" stroke-opacity="0.25" stroke-width="1"/>
</svg>
"""


def main() -> int:
    ASSETS.mkdir(exist_ok=True)
    (ASSETS / "banner.svg").write_text(banner_svg(), encoding="utf-8")
    satirlar = daily_ciktisi(sys.argv)
    (ASSETS / "terminal.svg").write_text(terminal_svg(satirlar), encoding="utf-8")
    for ad in ("banner.svg", "terminal.svg"):
        print(f"{ad}: {(ASSETS / ad).stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
