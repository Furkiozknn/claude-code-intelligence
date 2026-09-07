"""Claude Code dosya yerlesimi (tycho SCHEMA.md, ccusage adaptor README, notes/02).

- Kok dizinler: `CLAUDE_CONFIG_DIR` (virgulle birden cok) yoksa `~/.claude`
  (+ varsa `~/.config/claude`).
- Transcript'ler `projects/` altinda OZYINELEMELI `*.jsonl`:
  `<proje>/<oturum>.jsonl`, `<proje>/<oturum>/subagents/agent-*.jsonl`,
  `<proje>/<oturum>/subagents/workflows/wf_*/agent-*.jsonl`.
  `workflows/wf_*/journal.jsonl` transcript DEGIL - atlanir.
- Kimlik dosyasi `.credentials.json` yalniz konum olarak bilinir; bu modul
  OKUMAZ.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Iterable, Mapping

from cci.model.ids import SourceInstance

ENV_CONFIG_DIR = "CLAUDE_CONFIG_DIR"
DEFAULT_DIRS = ("~/.claude", "~/.config/claude")
JOURNAL_NAME = "journal.jsonl"


def _expand(p: str) -> Path:
    return Path(os.path.expandvars(p)).expanduser()


def config_dirs(env: Mapping[str, str] | None = None, home: Path | None = None) -> tuple[Path, ...]:
    """Aday kok dizinler (var olanlar), tekrarsiz, sirali."""
    env = os.environ if env is None else env
    raw = env.get(ENV_CONFIG_DIR, "").strip()
    candidates: list[Path] = []
    if raw:
        candidates += [_expand(part.strip()) for part in raw.split(",") if part.strip()]
    else:
        base = home if home is not None else Path.home()
        candidates += [base / ".claude", base / ".config" / "claude"]
    seen: set[Path] = set()
    out: list[Path] = []
    for c in candidates:
        try:
            r = c.resolve()
        except OSError:
            r = c
        if r in seen:
            continue
        seen.add(r)
        if r.is_dir():
            out.append(r)
    return tuple(out)


def projects_dir(root: Path) -> Path:
    return root / "projects"


def credentials_path(root: Path) -> Path:
    return root / ".credentials.json"


def find_transcripts(root: Path) -> tuple[Path, ...]:
    """`projects/` altinda ozyinelemeli *.jsonl; journal dosyalari haric; sirali."""
    pdir = projects_dir(root)
    if not pdir.is_dir():
        return ()
    found = [p for p in pdir.rglob("*.jsonl") if p.is_file() and p.name != JOURNAL_NAME]
    return tuple(sorted(found))


def instance_id_for(root: Path) -> str:
    return "claude-config:" + hashlib.sha256(str(root.resolve()).encode("utf-8")).hexdigest()[:16]


def _base_label(root: Path, home: Path) -> str:
    try:
        if root.resolve() == (home / ".claude").resolve():
            return "Default Claude"
    except OSError:
        pass
    name = root.name.lstrip(".").strip()
    return name or str(root)


def instance_for(root: Path, *, label: str, schema_verified: bool, verified_at) -> SourceInstance:
    return SourceInstance(
        provider="anthropic", instance_id=instance_id_for(root), label=label, kind="cli",
        root_path=str(root), network=False, schema_verified=schema_verified,
        verified_at=verified_at,
    )


def unique_labels(roots: Iterable[Path], home: Path | None = None) -> list[tuple[Path, str]]:
    """Ayni etikete dusen kokler numaralanir (codeburn `makeUniqueLabels`)."""
    home = home if home is not None else Path.home()
    pairs = [(r, _base_label(r, home)) for r in roots]
    counts: dict[str, int] = {}
    for _, lbl in pairs:
        counts[lbl] = counts.get(lbl, 0) + 1
    seen: dict[str, int] = {}
    out: list[tuple[Path, str]] = []
    for r, lbl in pairs:
        if counts[lbl] > 1:
            seen[lbl] = seen.get(lbl, 0) + 1
            out.append((r, f"{lbl} {seen[lbl]}"))
        else:
            out.append((r, lbl))
    return out
