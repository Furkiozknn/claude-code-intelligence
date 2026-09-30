# -*- coding: utf-8 -*-
"""README terminal gorselini uretir: assets/terminal.svg.

assets/banner.svg artik burada uretilmiyor: tum depolarin banner'i
Furkiozknn/Furkiozknn assets/banner/banner.py sablonundan gelir.

Neden bir betik ve neden depoda: terminal gorseli GERCEK `cci daily`
ciktisindan uretiliyor - ama SENTETIK ornek veri (scripts/ornek-veri.py)
uzerinde; kullanicinin gercek kullanimi gorsele girmez. Elle cizilmis bir ekran goruntusu, cikti degistigi
anda sessizce yalan olur; bu betik yeniden calistirilinca dogruyu yazar.

Yazi tipi, mevcut terminal.svg'deki gomulu JetBrains Mono'dan aliniyor;
boylece yeniden uretim baska bir depoya bagli degil.

Kullanim:
    python scripts/gorsel-uret.py            # sentetik veride `cci daily` calistirir
    python scripts/gorsel-uret.py cikti.txt  # hazir bir ciktidan uretir
"""
from __future__ import annotations

import html
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
ASSETS = KOK / "assets"
# Yalniz gomulu @font-face bloklari icin okunuyor (yeniden yazilmadan once).
FONT_KAYNAGI = KOK / "assets" / "terminal.svg"

# Kimlik: gozlem/olcum araci -> mavi-kehribar. projects.svg'de bu depo
# "TOOLING & INFRASTRUCTURE" sutununda ve #6cb6ff ile isaretli.
MAVI, KEHRIBAR, YESIL, KIRMIZI = "#6cb6ff", "#ffd76d", "#6dff9e", "#ff7b72"
METIN, SOLUK, COK_SOLUK = "#e6edf3", "#9aa4b2", "#6b7280"


def font_bloklari() -> str:
    """Mevcut terminal.svg'deki @font-face bloklarini oldugu gibi al."""
    if not FONT_KAYNAGI.exists():
        return ""  # font yoksa Consolas'a duser, gorsel yine calisir
    s = FONT_KAYNAGI.read_text(encoding="utf-8")
    return "\n".join(m.group(0) for m in re.finditer(r"@font-face\s*\{.*?\}", s, re.S))


def daily_ciktisi(argv: list[str]) -> list[str]:
    """`cci daily` ciktisi - HER ZAMAN sentetik ornek veriden.

    Kullanicinin kendi transcript'lerine bakilmaz: gorsel depoda herkese acik
    duruyor, gercek maliyet/oturum bilgisi sizmamali. `scripts/ornek-veri.py`
    belirlenimci uydurma bir kurulum yazar; cci ona CLAUDE_CONFIG_DIR ile bakar.
    """
    if len(argv) > 1:
        ham = Path(argv[1]).read_text(encoding="utf-8")
    else:
        with tempfile.TemporaryDirectory() as t:
            cfg = Path(t) / "cfg"
            subprocess.run([sys.executable, str(KOK / "scripts" / "ornek-veri.py"), str(cfg)],
                           check=True, capture_output=True)
            env = {**os.environ, "CLAUDE_CONFIG_DIR": str(cfg), "CCI_TZ": "UTC", "PYTHONIOENCODING": "utf-8"}
            cmd = [sys.executable, "-m", "cci.cli", "--data-dir", str(Path(t) / "veri")]
            for alt in (["scan"], ["daily"]):
                sonuc = subprocess.run(cmd + alt, capture_output=True, text=True, encoding="utf-8", cwd=KOK, env=env)
            ham = sonuc.stdout
    satirlar = [s.rstrip() for s in ham.splitlines() if s.strip()]
    if not satirlar:
        raise SystemExit("cci daily bos dondu")
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
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {gen} {yuk}" width="{gen}" height="{yuk}" role="img" aria-label="cci daily komutunun ciktisi (sentetik ornek veri): gun basina istek, token ve tahmini maliyet, model kirilimiyla">
  <defs><style>{font_bloklari()}</style></defs>
  <rect width="{gen}" height="{yuk}" rx="10" fill="#0d1117" stroke="#30363d" stroke-width="1.4"/>
  <rect width="{gen}" height="36" rx="10" fill="#161b22"/>
  <rect y="26" width="{gen}" height="10" fill="#161b22"/>
  <line x1="0" y1="36" x2="{gen}" y2="36" stroke="#30363d" stroke-width="1"/>
  <g><circle cx="22" cy="18" r="5.5" fill="#ff5f57"/><circle cx="42" cy="18" r="5.5" fill="#febc2e"/><circle cx="62" cy="18" r="5.5" fill="#28c840"/></g>
  <text x="88" y="23" font-family="'JetBrains Mono', Consolas, monospace" font-size="12.5" fill="{COK_SOLUK}">cci daily  ·  sentetik ornek veri</text>
  <g font-family="'JetBrains Mono', Consolas, monospace" font-size="13.5">
{govde}
  </g>
</svg>
"""


def main() -> int:
    ASSETS.mkdir(exist_ok=True)
    satirlar = daily_ciktisi(sys.argv)
    (ASSETS / "terminal.svg").write_text(terminal_svg(satirlar), encoding="utf-8")
    for ad in ("terminal.svg",):
        print(f"{ad}: {(ASSETS / ad).stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
