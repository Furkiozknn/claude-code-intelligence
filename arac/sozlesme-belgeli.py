#!/usr/bin/env python3
"""`cci/adapters/` altındaki her genel sembol belgeli mi?

    python3 arac/sozlesme-belgeli.py

Bu paket üçüncü tarafların uzatma noktası: `docs/PROVIDERS.md` bir sağlayıcı
adaptörünün nasıl yazılacağını anlatıyor ve sözleşme `adapters/base.py` içinde
duruyor. Uzatma noktası olduğunu söyleyen bir projede o noktanın belgesiz
olması pratikte kapalı olması demek — sözleşmeyi uygulayacak kişi kaynağı
okuyup niyeti tahmin etmek zorunda kalır, ve tahmin ettiği şey çoğu zaman
imzadan çıkarılamayan şeydir: bir alanı dürüstçe doldurmazsa aşağıda ne kırılır.

Kapı bilerek dar: yalnızca `cci/adapters/`. Deponun geri kalanı için bir
docstring zorunluluğu yok ve olması da gerekmiyor; buradaki kural, dışarıya
açık yüzeyin sessizce belgesizleşmemesi.

Çıkış kodu: eksik varsa 1.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
HEDEF = KOK / "cci" / "adapters"


def eksikler() -> list[tuple[str, int, str]]:
    out: list[tuple[str, int, str]] = []
    for yol in sorted(HEDEF.rglob("*.py")):
        if "__pycache__" in yol.parts:
            continue
        try:
            agac = ast.parse(yol.read_text(encoding="utf-8"))
        except SyntaxError as ex:
            out.append((str(yol.relative_to(KOK)), ex.lineno or 0, "<ayristirilamadi>"))
            continue
        for dugum in agac.body:
            if not isinstance(dugum, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if dugum.name.startswith("_"):
                continue
            if not ast.get_docstring(dugum):
                out.append((str(yol.relative_to(KOK)), dugum.lineno, dugum.name))
    return out


def main() -> int:
    if not HEDEF.is_dir():
        print("cci/adapters yok", file=sys.stderr)
        return 2
    eksik = eksikler()
    toplam = sum(
        1
        for y in HEDEF.rglob("*.py")
        if "__pycache__" not in y.parts
        for d in ast.parse(y.read_text(encoding="utf-8")).body
        if isinstance(d, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and not d.name.startswith("_")
    )
    if eksik:
        print("Belgesiz genel sembol (%d/%d):" % (len(eksik), toplam))
        for yol, satir, ad in eksik:
            print("  %s:%d  %s" % (yol, satir, ad))
        print()
        print("Burasi ucuncu taraflarin uzatma noktasi. Belgesiz bir sozlesme,")
        print("uygulayacak kisiyi kaynaktan niyet tahmin etmeye birakir.")
        return 1
    print("cci/adapters: %d genel sembolun %d'si belgeli" % (toplam, toplam))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
