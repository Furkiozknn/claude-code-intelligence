# -*- coding: utf-8 -*-
"""README terminal demosunu uretir: gercek `cci` komutlari, SENTETIK ornek veri.

Akis: scripts/ornek-veri.py ile uydurma bir Claude Code kurulumu yazilir, sonra
asagidaki komutlar GERCEKTEN calistirilir ve ciktilari (cikis koduyla) kaydedilir.
Cikti uydurulmaz; kullanicinin kendi verisine hic bakilmaz (CLAUDE_CONFIG_DIR
sentetik dizine, --data-dir gecici dizine gider).

Uretilenler (--cikti <dizin>):
  komutlar.txt   her komut: tam satir, gercek cikti, cikis kodu, tarih
  demo.gif       README icin (720 px, sentetik-veri etiketli)
  terminal.mp4   dikey 1080x1920, sessiz, etiketsiz ham kayit (video hatti icin)

Gerekenler: ffmpeg PATH'te; Pillow (`uv run --with pillow python scripts/demo-uret.py ...`).
Yazi tipi: JetBrains Mono (OFL) - --font ile TTF yolu verilir.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
KOMUTLAR = [["scan"], ["daily"], ["sessions", "--limit", "3"], ["advise"]]
# Videoya girmez; komutlar.txt'te yardim ve hata mesajlarinin kaniti olarak durur.
EK = [["--help"], ["today"], ["--data-dir", "%TMP%/dosya", "today"], ["session", "yok"]]

# FRK-OS: siyah zemin, krem yazi, sari vurgu (sosyal/uret/tema.mjs "klasik" ile ayni degerler).
ZEMIN, KREM, SARI, CAMGOBEGI, SOLUK = "#0e0d0b", "#f1ece2", "#ffc21a", "#19d3e6", "#9a958a"


def kos(tmp: Path) -> list[tuple[str, str, int]]:
    cfg = tmp / "cfg"
    subprocess.run([sys.executable, str(KOK / "scripts" / "ornek-veri.py"), str(cfg)], check=True, capture_output=True)
    env = {**os.environ, "CLAUDE_CONFIG_DIR": str(cfg), "CCI_TZ": "UTC", "PYTHONIOENCODING": "utf-8"}
    sonuc = []
    dosya = tmp / "dosya"
    dosya.write_text("x", encoding="utf-8")
    for arg in KOMUTLAR + EK:
        arg = [str(dosya) if a == "%TMP%/dosya" else a for a in arg]
        d = [] if "--data-dir" in arg else ["--data-dir", str(tmp / "veri")]
        p = subprocess.run([sys.executable, "-m", "cci.cli", *d, *arg],
                           capture_output=True, text=True, encoding="utf-8", cwd=KOK, env=env)
        cikti = (p.stdout + p.stderr).rstrip("\n").replace(str(tmp), "<tmp>")   # gecici yol komutlar.txt'e girmesin
        sonuc.append(("cci " + " ".join(arg).replace(str(tmp), "<tmp>"), cikti, p.returncode))
    return sonuc


def metin_dosyasi(sonuc, yol: Path) -> None:
    parca = [f"# SENTETIK ornek veri (scripts/ornek-veri.py). Gercek komutlar, gercek cikti. {date.today().isoformat()}\n"]
    for komut, cikti, kod in sonuc:
        parca.append(f"$ {komut}\n{cikti}\n[cikis kodu {kod}]\n")
    yol.write_text("\n".join(parca), encoding="utf-8")


def satirlar(sonuc, kol: int):
    """(metin, tur) listesi. Uzun cikti satirlari kelime sinirindan kirilir (yalniz gosterim; komutlar.txt kirilmaz)."""
    out = []
    for komut, cikti, _ in sonuc:
        out.append(("$ " + komut, "komut"))
        for s in cikti.splitlines():
            girinti = ""
            while len(s) > kol:                 # kelime sinirindan kir, devam satirini girintile
                k = s.rfind(" ", len(girinti) + 8, kol)
                k = kol if k < 0 else k
                out.append((s[:k], "cikti")); s = "      " + s[k:].lstrip(); girinti = "      "
            out.append((s, "cikti"))
    return out


def renk_parcalari(metin: str, tur: str):
    if tur == "komut":
        yield "$ ", SARI
        yield metin[2:], KREM
        return
    for tok in re.split(r"(\s+)", metin):
        if not tok:
            continue
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}|\d\d-\d\d", tok): c = CAMGOBEGI
        elif tok.startswith("$"): c = SARI
        elif tok.startswith("[") or tok.endswith("]") or tok.endswith("]"): c = SOLUK
        elif re.fullmatch(r"[\d,]+", tok): c = KREM
        else: c = "#cfc9bd"
        yield tok, c


def kare_ciz(Image, ImageDraw, font, W, H, gorunen, imlec, etiket, boyut):
    im = Image.new("RGB", (W, H), ZEMIN)
    d = ImageDraw.Draw(im)
    mx, my, sy = int(boyut * 1.4), int(boyut * (3.2 if etiket else 2.0)), int(boyut * 1.38)
    cw = font.getlength("M")
    if etiket:
        d.text((mx, my - boyut * 1.9), "cci  ·  sentetik ornek veri", font=font, fill=SOLUK)
    for i, (metin, tur) in enumerate(gorunen):
        x, y = mx, my + i * sy
        for parca, c in renk_parcalari(metin, tur):
            d.text((x, y), parca, font=font, fill=c)
            x += cw * len(parca)
        if imlec and i == len(gorunen) - 1:
            d.rectangle([x + 2, y + 2, x + cw - 2, y + boyut * 1.15], fill=SARI)
    return im


def kareler(sonuc, W, H, boyut, fontyolu, etiket, fps=12):
    from PIL import Image, ImageDraw, ImageFont
    font = ImageFont.truetype(fontyolu, boyut)
    kol = int((W - 2 * boyut * 1.4) // font.getlength("M"))
    tum = satirlar(sonuc[:len(KOMUTLAR)], kol)
    sat_max = int((H - boyut * 4) // (boyut * 1.38))
    # zaman cizelgesi: komut satiri harf harf, cikti satir satir
    olay = []           # her kare icin (satir sayisi, yazilan_karakter_yalniz_son_komut)
    gorunen: list[tuple[str, str]] = []
    def kare(imlec=True):
        goster = gorunen[-sat_max:]
        olay.append((list(goster), imlec))
    kare(); [kare() for _ in range(int(fps * 0.6))]
    for i, (metin, tur) in enumerate(tum):
        if tur == "komut":
            for n in range(2, len(metin) + 1):
                gorunen.append((metin[:n], tur)) if n == 2 else gorunen.__setitem__(-1, (metin[:n], tur))
                kare()
            gorunen[-1] = (metin, tur); kare()
            [kare() for _ in range(int(fps * 0.35))]
        else:
            gorunen.append((metin, tur))
            kare()
            if tum[i + 1:i + 2] and tum[i + 1][1] == "komut":
                [kare() for _ in range(int(fps * 1.6))]      # okunma payi
    [kare() for _ in range(int(fps * 4))]
    for goster, imlec in olay:      # tembel: tum kareleri bellekte tutma (1080x1920 x ~250)
        yield kare_ciz(Image, ImageDraw, font, W, H, goster, imlec, etiket, boyut)


def kodla(kareler_, cikti: Path, fps: int, filtre: str | None, bicim: str) -> None:
    if bicim == "mp4":
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(fps), "-i", "-", "-an",
               "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-crf", "20", str(cikti)]
    else:
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(fps), "-i", "-",
               "-vf", filtre or "", str(cikti)]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    import io
    for im in kareler_:
        b = io.BytesIO(); im.save(b, "PNG"); p.stdin.write(b.getvalue())
    p.stdin.close()
    if p.wait():
        raise SystemExit("ffmpeg basarisiz")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cikti", required=True, help="komutlar.txt / terminal.mp4 dizini")
    ap.add_argument("--gif", default=None, help="README GIF yolu (docs/demo/demo.gif)")
    ap.add_argument("--font", required=True, help="JetBrainsMono-Regular.ttf yolu")
    a = ap.parse_args()
    cikti = Path(a.cikti); cikti.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as t:
        sonuc = kos(Path(t))
    metin_dosyasi(sonuc, cikti / "komutlar.txt")
    fps = 12
    kodla(kareler(sonuc, 1080, 1920, 28, a.font, False, fps), cikti / "terminal.mp4", fps, None, "mp4")
    if a.gif:
        Path(a.gif).parent.mkdir(parents=True, exist_ok=True)
        fl = "scale=720:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=32[p];[b][p]paletteuse=dither=none"
        kodla(kareler(sonuc, 1200, 675, 20, a.font, True, fps), Path(a.gif), fps, fl, "gif")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
