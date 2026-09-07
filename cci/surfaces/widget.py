"""Masaustu widget (tkinter, stdlib) - snapshot dosyasini okur, hesap yapmaz.

`widget_lines(snapshot)` saf ve testli; `run_widget()` GUI (elle dogrulanir).
120x40 px hedefi: 2 satir; tiklayinca ayrinti (5 satir). Her zaman ustte opsiyonel.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


def _window(snapshot: Mapping[str, Any], kind: str) -> Mapping[str, Any] | None:
    for w in (snapshot.get("quota") or {}).get("windows", []):
        if w.get("kind") == kind:
            return w
    return None


def widget_lines(snapshot: Mapping[str, Any] | None, *, detailed: bool = False) -> list[str]:
    if not snapshot:
        return ["cci --", "snapshot yok"]
    parts = []
    for kind, short in (("session_5h", "5h"), ("weekly_all", "7d")):
        w = _window(snapshot, kind)
        if w is None or w.get("utilization_pct") is None:
            parts.append(f"{short} --")
        else:
            s = f"{short} {w['utilization_pct']:.0f}%{w.get('badge', '')}"
            if w.get("pace"):
                s += f"{'⇡' if w['pace']['delta_pct'] > 0 else '⇣'}{abs(w['pace']['delta_pct']):.0f}"
            parts.append(s)
    lines = [" · ".join(parts)]
    today = snapshot.get("today")
    cost = today["cost"]["text"] + ("≈" if today["cost"]["released"] else "") if today else "$--"
    lines.append(f"{cost} · {snapshot.get('attention', 'ok')}")
    if detailed:
        for kind in ("session_5h", "weekly_all"):
            w = _window(snapshot, kind)
            if w and w.get("resets_at"):
                lines.append(f"{kind}: reset {w['resets_at'][5:16].replace('T', ' ')}"
                             + (f" · ~{round(w['pace']['eta_s'] / 60)} dk" if w.get("pace") and w["pace"].get("eta_s") else ""))
        if today:
            lines.append(f"istek {today['requests']} · token {today['tokens']['input_total']:,}/{today['tokens']['output']:,}")
        for a in (snapshot.get("alerts") or [])[:2]:
            lines.append(f"! {a.get('rule_id')}: {a.get('message', '')[:40]}")
    return lines


def run_widget(snapshot_path: Path, *, always_on_top: bool = True, poll_ms: int = 5000) -> None:  # pragma: no cover - GUI
    import tkinter as tk

    root = tk.Tk()
    root.title("cci")
    root.overrideredirect(True)
    root.attributes("-topmost", always_on_top)
    root.configure(bg="#1e1e1e")
    state = {"detailed": False, "x": 0, "y": 0}
    label = tk.Label(root, text="cci", fg="#e6e6e6", bg="#1e1e1e", font=("Segoe UI", 9), justify="left", padx=8, pady=4)
    label.pack()

    def refresh() -> None:
        try:
            snap = json.loads(snapshot_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            snap = None
        label.configure(text="\n".join(widget_lines(snap, detailed=state["detailed"])))
        root.after(poll_ms, refresh)

    def toggle(_e=None) -> None:
        state["detailed"] = not state["detailed"]
        refresh()

    def press(e) -> None:
        state["x"], state["y"] = e.x, e.y

    def drag(e) -> None:
        root.geometry(f"+{root.winfo_x() + e.x - state['x']}+{root.winfo_y() + e.y - state['y']}")

    label.bind("<Double-Button-1>", toggle)
    label.bind("<ButtonPress-1>", press)
    label.bind("<B1-Motion>", drag)
    label.bind("<Button-3>", lambda e: root.destroy())
    refresh()
    root.mainloop()
