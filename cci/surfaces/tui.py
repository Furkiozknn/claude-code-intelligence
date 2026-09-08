"""Stage 16 - TUI: snapshot dosyasini okuyup 80x24'te canli gosterir. Hesap yapmaz.

ponytail: curses yerine ANSI temizleme + input yok; `q` icin Ctrl-C yeter.
Ekran metni saf fonksiyonda (`render`), testli; dongu GUI tarafi.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Mapping

from cci.api.snapshot import read_snapshot

BAR_W = 24


def _bar(pct: float | None, width: int = BAR_W) -> str:
    if pct is None:
        return "─" * width
    filled = int(round(min(max(pct, 0), 100) / 100 * width))
    return "█" * filled + "░" * (width - filled)


def render(snapshot: Mapping[str, Any] | None, *, width: int = 80) -> str:
    if not snapshot:
        return "CCI — snapshot yok. `cci run` ya da `cci snapshot` calistir."
    lines = [f"CLAUDE CODE INTELLIGENCE{'':<4}{snapshot.get('generated_at', '')[:19]}", "─" * width]
    q = snapshot.get("quota") or {}
    if q.get("placeholder"):
        lines.append("KOTA  --  (hesap kimligi/snapshot yok)")
    for w in q.get("windows", []):
        pct = w.get("utilization_pct")
        pace = w.get("pace") or {}
        fc = w.get("forecast") or {}
        tail = ""
        if pace:
            tail += f"  {'⇡' if pace['delta_pct'] > 0 else '⇣'}{abs(pace['delta_pct']):.0f}%"
        if fc.get("projected_at_reset"):
            tail += f"  ~%{fc['projected_at_reset']['median_pct']:.0f} ({fc['verdict']})"
        elif fc:
            tail += f"  [{fc['verdict']}]"
        lines.append(f"{w['kind']:<14}{_bar(pct)} {('--' if pct is None else f'{pct:5.1f}%')}{w.get('badge', '')}{tail}")
    lines.append("─" * width)
    t = snapshot.get("today")
    if t:
        lines.append(f"BUGUN  istek {t['requests']:<5} token {t['tokens']['input_total']:>10,}/{t['tokens']['output']:<8,} "
                     f"maliyet {t['cost']['text']}")
        for m in (t.get("models") or [])[:4]:
            lines.append(f"   {m['display']:<16} {m['requests']:>4} istek  {m['cost']['text']}")
    lines.append(f"DIKKAT  {snapshot.get('attention', 'ok')}")
    for a in (snapshot.get("alerts") or [])[:3]:
        lines.append(f"  ! [{a['severity']}] {a['rule_id']}: {a['message'][:width - 20]}")
    lines.append("─" * width)
    lines.append("Ctrl-C cikis · cci advise · cci doctor")
    return "\n".join(lines)


def run_tui(snapshot_path: Path, *, interval: float = 2.0) -> None:  # pragma: no cover - dongu
    try:
        while True:
            print("\033[2J\033[H" + render(read_snapshot(snapshot_path)), flush=True)
            time.sleep(interval)
    except KeyboardInterrupt:
        print()
