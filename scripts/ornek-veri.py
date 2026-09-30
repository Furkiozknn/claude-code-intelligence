# -*- coding: utf-8 -*-
"""SENTETIK ornek veri: sahte bir Claude Code kurulumu (transcript'ler) uretir.

Neden var: README gorselleri ve demolar kullanicinin kendi kullanim verisiyle
uretilmemeli (maliyet, oturum, proje yolu sizar). Bu betik tamamen uydurma,
belirlenimci (rastgelelik yok) bir `projects/*.jsonl` agaci yazar; `cci` ona
`CLAUDE_CONFIG_DIR` ile bakar. Icerik alani yoktur; yalniz sayac ve zaman.

Kullanim:
    python scripts/ornek-veri.py <hedef-dizin> [--bugune-kaydir]
    CLAUDE_CONFIG_DIR=<hedef-dizin> cci --data-dir <bos-dizin> scan
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# (gun, model, istek sayisi, girdi, cikti, onbellek-yazma, onbellek-okuma) - hepsi uydurma.
PLAN = [
    ("2026-09-01", "claude-sonnet-5", 42, 900, 1_400, 6_000, 90_000),
    ("2026-09-01", "claude-haiku-4-5", 12, 500, 300, 1_000, 8_000),
    ("2026-09-02", "claude-opus-5", 30, 1_100, 2_200, 9_000, 140_000),
    ("2026-09-02", "claude-sonnet-5", 55, 800, 1_300, 5_000, 80_000),
    ("2026-09-03", "claude-opus-5", 64, 1_300, 2_600, 11_000, 170_000),
    ("2026-09-03", "claude-haiku-4-5", 9, 450, 280, 900, 7_000),
    ("2026-09-04", "claude-sonnet-5", 38, 850, 1_250, 5_500, 85_000),
    ("2026-09-05", "claude-opus-5", 21, 1_000, 2_000, 8_000, 120_000),
]
PROJELER = ("-ornek-proje-a", "-ornek-proje-b")


def yaz(kok: Path, bugune_kaydir: bool = False) -> int:
    """`bugune_kaydir`: son plan gunu bugun olacak sekilde tarihleri kaydirir (pano `Bugun` bolumu icin)."""
    n = 0
    kayma = timedelta(0)
    if bugune_kaydir:
        kayma = datetime.now(timezone.utc).date() - datetime.fromisoformat(PLAN[-1][0]).date()
    for i, (gun, model, adet, gi, ci, cw, cr) in enumerate(PLAN):
        oturum = f"ornek-{i + 1:02d}"
        yol = kok / "projects" / PROJELER[i % 2] / f"{oturum}.jsonl"
        yol.parent.mkdir(parents=True, exist_ok=True)
        t0 = datetime.fromisoformat(gun).replace(hour=1, tzinfo=timezone.utc) + kayma
        satirlar = []
        for k in range(adet):
            ts = (t0 + timedelta(seconds=k * 40)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
            satirlar.append(json.dumps({
                "type": "assistant", "uuid": f"{oturum}-{k}", "timestamp": ts,
                "sessionId": oturum, "requestId": f"req_{oturum}_{k}", "cwd": "/ornek/proje",
                "version": "0.0.0-ornek", "isSidechain": False,
                "message": {"id": f"msg_{oturum}_{k}", "model": model, "role": "assistant", "type": "message",
                            "stop_reason": "end_turn",
                            "usage": {"input_tokens": gi, "output_tokens": ci,
                                      "cache_creation_input_tokens": cw, "cache_read_input_tokens": cr,
                                      "service_tier": "standard"},
                            "content": []},
            }))
        yol.write_text("\n".join(satirlar) + "\n", encoding="utf-8")
        n += adet
    return n


if __name__ == "__main__":
    arg = [a for a in sys.argv[1:] if a != "--bugune-kaydir"]
    if len(arg) != 1:
        raise SystemExit(__doc__)
    hedef = Path(arg[0])
    print(f"{yaz(hedef, '--bugune-kaydir' in sys.argv)} sentetik istek yazildi: {hedef}")
