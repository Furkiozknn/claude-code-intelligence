"""Arastirma katalogu araci.

Repo kesif/puanlama veri setini yonetir. Veri: research/catalog.jsonl
(her satir bir JSON nesnesi). Elle duzenlenmez; ingest ile birlestirilir.

Kullanim:
  python research/tools/catalog.py ingest research/inbox/batch-01.json
  python research/tools/catalog.py stats
  python research/tools/catalog.py list [--category X] [--approach Y] [--depth D]
  python research/tools/catalog.py score           # toplamlari yeniden hesapla
  python research/tools/catalog.py top 20
  python research/tools/catalog.py report          # research/reports/catalog.md
  python research/tools/catalog.py gaps            # kategori/yaklasim bosluklari

Bagimlilik yok.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # research/
CATALOG = ROOT / "catalog.jsonl"
REPORTS = ROOT / "reports"

# MASTER_PROMPT §5 — toplam 100
WEIGHTS: dict[str, int] = {
    "data_collection": 15,
    "analytics": 12,
    "architecture": 12,
    "accuracy": 10,
    "prediction": 10,
    "observability": 8,
    "ux": 7,
    "extensibility": 7,
    "privacy": 6,
    "performance": 4,
    "documentation": 3,
    "community": 3,
    "cross_provider": 3,
}
assert sum(WEIGHTS.values()) == 100, "agirliklar 100 etmeli"

DEPTH_RANK = {"shallow": 0, "fetched": 1, "deep": 2}
LIST_FIELDS = ("categories", "approach", "surfaces", "source_queries")

# Faz 1 tamamlanma olcutu icin beklenen kategoriler (research/README.md)
EXPECTED_CATEGORIES = [
    "claude-code", "llm-usage", "cost", "quota", "dev-productivity",
    "coding-agent", "observability", "proxy", "local-first", "timeseries",
    "desktop", "terminal", "cross-provider", "privacy",
]
EXPECTED_APPROACHES = [
    "api-polling", "jsonl-parsing", "proxy", "stdin-statusline", "hooks",
    "otlp", "sdk-instrumentation", "browser-scrape", "os-monitor",
    "log-parsing", "sqlite-inspection",
]


# ---------------------------------------------------------------- yardimci

def norm_url(url: str) -> str:
    u = url.strip().lower().split("?", 1)[0].split("#", 1)[0]
    if u.endswith(".git"):
        u = u[:-4]
    return u.rstrip("/")


def name_from_url(url: str) -> str:
    u = norm_url(url)
    marker = "github.com/"
    if marker in u:
        tail = u.split(marker, 1)[1]
        parts = [p for p in tail.split("/") if p]
        if len(parts) >= 2:
            return f"{parts[0]}/{parts[1]}"
    return u


def load() -> dict[str, dict]:
    if not CATALOG.exists():
        return {}
    out: dict[str, dict] = {}
    for line in CATALOG.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        entry = json.loads(line)
        out[norm_url(entry["url"])] = entry
    return out


def save(entries: dict[str, dict]) -> None:
    CATALOG.parent.mkdir(parents=True, exist_ok=True)
    rows = sorted(entries.values(), key=lambda e: e.get("name", "").lower())
    with CATALOG.open("w", encoding="utf-8") as fh:
        for e in rows:
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")


def total(scores: dict) -> float:
    t = 0.0
    for key, weight in WEIGHTS.items():
        val = scores.get(key)
        if val is None:
            continue
        t += max(0.0, min(10.0, float(val))) / 10.0 * weight
    return round(t, 1)


def scored_weight(scores: dict) -> int:
    """Kac puanlik kriter doldurulmus — eksik veriyle hesaplanan toplam
    bunun altinda kaliyorsa okuyucu bunu bilmeli."""
    return sum(w for k, w in WEIGHTS.items() if scores.get(k) is not None)


def merge(old: dict, new: dict) -> dict:
    out = dict(old)
    for key, val in new.items():
        if val is None:
            continue
        if key in LIST_FIELDS:
            out[key] = sorted(set(out.get(key) or []) | set(val))
        elif key == "depth":
            if DEPTH_RANK.get(val, 0) >= DEPTH_RANK.get(out.get("depth", "shallow"), 0):
                out[key] = val
        elif key in ("scores", "score_notes"):
            merged = dict(out.get(key) or {})
            merged.update(val)
            out[key] = merged
        elif key == "summary":
            if len(str(val)) >= len(str(out.get("summary", ""))):
                out[key] = val
        elif key == "stars":
            # bilinen sayi bilinmeyeni ezer; ikisi de biliniyorsa yeni kalir
            out[key] = val
        else:
            out[key] = val
    return out


def _recompute(entries: dict[str, dict]) -> None:
    for e in entries.values():
        scores = e.get("scores")
        if scores:
            e["total"] = total(scores)
            e["scored_weight"] = scored_weight(scores)
        else:
            e.pop("total", None)
            e.pop("scored_weight", None)


# ---------------------------------------------------------------- komutlar

def cmd_ingest(path: str) -> int:
    entries = load()
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("entries", [])
    today = date.today().isoformat()
    added = updated = skipped = 0
    for e in data:
        url = e.get("url")
        if not url or "github.com/" not in url.lower():
            skipped += 1
            continue
        e.setdefault("name", name_from_url(url))
        e.setdefault("depth", "shallow")
        e.setdefault("found_at", today)
        if e.get("scores") and e["depth"] == "shallow":
            # Puan uydurma yasagi: README okunmadan puan kabul edilmez
            print(f"  [!] {e['name']}: depth=shallow ama scores var — puan atlandi",
                  file=sys.stderr)
            e.pop("scores", None)
            e.pop("score_notes", None)
        key = norm_url(url)
        if key in entries:
            entries[key] = merge(entries[key], e)
            updated += 1
        else:
            entries[key] = e
            added += 1
    _recompute(entries)
    save(entries)
    print(f"eklendi {added} · güncellendi {updated} · atlandı {skipped} · toplam {len(entries)}")
    return 0


def cmd_stats() -> int:
    entries = load()
    n = len(entries)
    print(f"toplam repo: {n}")
    if not n:
        return 0
    depth = Counter(e.get("depth", "shallow") for e in entries.values())
    print("derinlik  :", dict(depth))
    scored = sum(1 for e in entries.values() if e.get("scores"))
    print(f"puanlı    : {scored}")
    stars_known = [e["stars"] for e in entries.values() if isinstance(e.get("stars"), int)]
    print(f"yıldız bilinen: {len(stars_known)}"
          + (f" · medyan {sorted(stars_known)[len(stars_known)//2]}" if stars_known else ""))

    def show(field: str, title: str) -> None:
        c: Counter = Counter()
        for e in entries.values():
            for v in e.get(field) or []:
                c[v] += 1
        print(f"\n{title}")
        for k, v in c.most_common():
            print(f"  {k:<22} {v}")

    show("categories", "kategori")
    show("approach", "veri toplama yaklaşımı")
    show("surfaces", "yüzey")
    return 0


def cmd_gaps() -> int:
    """Faz 1 olcutu: her kategori >=3, her yaklasim >=2."""
    entries = load()
    cat: Counter = Counter()
    app: Counter = Counter()
    for e in entries.values():
        for v in e.get("categories") or []:
            cat[v] += 1
        for v in e.get("approach") or []:
            app[v] += 1
    eksik = 0
    print(f"toplam {len(entries)} / hedef ≥100")
    print("\nkategori (hedef ≥3):")
    for c in EXPECTED_CATEGORIES:
        n = cat.get(c, 0)
        mark = "ok " if n >= 3 else "EKSİK"
        if n < 3:
            eksik += 1
        print(f"  {mark} {c:<18} {n}")
    print("\nyaklaşım (hedef ≥2):")
    for a in EXPECTED_APPROACHES:
        n = app.get(a, 0)
        mark = "ok " if n >= 2 else "EKSİK"
        if n < 2:
            eksik += 1
        print(f"  {mark} {a:<18} {n}")
    print(f"\neksik alan: {eksik}")
    return 0 if (eksik == 0 and len(entries) >= 100) else 1


def cmd_list(category: str | None, approach: str | None, depth: str | None) -> int:
    entries = load()
    rows = []
    for e in entries.values():
        if category and category not in (e.get("categories") or []):
            continue
        if approach and approach not in (e.get("approach") or []):
            continue
        if depth and e.get("depth") != depth:
            continue
        rows.append(e)
    rows.sort(key=lambda e: (-(e.get("total") or 0), -(e.get("stars") or 0), e.get("name", "")))
    for e in rows:
        stars = e.get("stars")
        stars_s = f"{stars:>6}" if isinstance(stars, int) else "     ?"
        tot = e.get("total")
        tot_s = f"{tot:5.1f}" if tot is not None else "    -"
        print(f"{tot_s} {stars_s} {e.get('depth','?'):<8} {e.get('name','?'):<45} "
              f"{','.join(e.get('approach') or [])}")
    print(f"\n{len(rows)} kayıt")
    return 0


def cmd_score() -> int:
    entries = load()
    _recompute(entries)
    save(entries)
    scored = [e for e in entries.values() if e.get("total") is not None]
    print(f"{len(scored)} kayıt puanlandı")
    return 0


def cmd_top(n: int) -> int:
    entries = load()
    scored = [e for e in entries.values() if e.get("total") is not None]
    scored.sort(key=lambda e: -e["total"])
    for i, e in enumerate(scored[:n], 1):
        conf = e.get("confidence", "?")
        print(f"{i:>2}. {e['total']:5.1f}  ({e.get('scored_weight', 0):>3}/100 kriter) "
              f"{conf:<6} {e['name']:<45} {','.join(e.get('categories') or [])}")
    return 0


def cmd_report() -> int:
    entries = load()
    REPORTS.mkdir(parents=True, exist_ok=True)
    rows = sorted(entries.values(),
                  key=lambda e: (-(e.get("total") or -1), -(e.get("stars") or 0), e.get("name", "")))
    lines = ["# Araştırma kataloğu", "",
             f"Toplam {len(rows)} repo · üretim: {date.today().isoformat()}", "",
             "| # | Repo | ⭐ | Derinlik | Toplam | Kategoriler | Yaklaşım | Yüzey |",
             "|--:|---|--:|---|--:|---|---|---|"]
    for i, e in enumerate(rows, 1):
        stars = e.get("stars")
        tot = e.get("total")
        lines.append(
            f"| {i} | [{e.get('name')}]({e.get('url')}) | "
            f"{stars if isinstance(stars, int) else '?'} | {e.get('depth','?')} | "
            f"{tot if tot is not None else '—'} | "
            f"{', '.join(e.get('categories') or [])} | "
            f"{', '.join(e.get('approach') or [])} | "
            f"{', '.join(e.get('surfaces') or [])} |")
    lines += ["", "## Özetler", ""]
    for e in rows:
        lines.append(f"### {e.get('name')}")
        lines.append(f"{e.get('url')}  ")
        lines.append(e.get("summary", "").strip() or "_özet yok_")
        notes = e.get("score_notes") or {}
        if notes:
            lines.append("")
            for k, v in notes.items():
                lines.append(f"- **{k}** ({(e.get('scores') or {}).get(k)}): {v}")
        lines.append("")
    (REPORTS / "catalog.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"yazıldı: {REPORTS / 'catalog.md'} ({len(rows)} kayıt)")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Araştırma kataloğu")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("ingest"); s.add_argument("path")
    sub.add_parser("stats")
    sub.add_parser("gaps")
    s = sub.add_parser("list")
    s.add_argument("--category"); s.add_argument("--approach"); s.add_argument("--depth")
    sub.add_parser("score")
    s = sub.add_parser("top"); s.add_argument("n", type=int, nargs="?", default=20)
    sub.add_parser("report")
    a = p.parse_args()
    if a.cmd == "ingest":
        return cmd_ingest(a.path)
    if a.cmd == "stats":
        return cmd_stats()
    if a.cmd == "gaps":
        return cmd_gaps()
    if a.cmd == "list":
        return cmd_list(a.category, a.approach, a.depth)
    if a.cmd == "score":
        return cmd_score()
    if a.cmd == "top":
        return cmd_top(a.n)
    if a.cmd == "report":
        return cmd_report()
    return 2


if __name__ == "__main__":
    sys.exit(main())
