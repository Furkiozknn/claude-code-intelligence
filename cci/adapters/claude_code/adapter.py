"""ClaudeCodeAdapter - Stage 2 iskeleti.

Stage 2: discover / probe_roots / capabilities / health.
Stage 3 (toplayicilar) `collect`'i, Stage 5 (normalizasyon) `normalize`'i doldurur;
simdilik bos ama sozlesmeye uygun donerler (NotImplementedError degil: cekirdek
adaptorun varligini ve yollarini `doctor`'da gostermeli).
"""

from __future__ import annotations

import os
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Mapping

from cci.adapters.base import (Capabilities, Cursor, Health, ProbeRoot, ProviderAdapter, RawBatch)
from cci.model.ids import SourceInstance

from .paths import (config_dirs, credentials_path, find_transcripts, instance_for, projects_dir,
                    unique_labels)

# Sema dogrulamasinin tarihi: notes/02 (resmi belgeler) + tycho SCHEMA.md + ccusage
# adaptor kurallari bu tarihte okundu. Format degisirse bu tarih ve fixture'lar yenilenir.
SCHEMA_VERIFIED_AT = date(2026, 9, 7)


class ClaudeCodeAdapter(ProviderAdapter):
    name = "claude_code"
    provider = "anthropic"

    def __init__(self, env: Mapping[str, str] | None = None, home: Path | None = None) -> None:
        self._env = dict(os.environ if env is None else env)
        self._home = home if home is not None else Path.home()
        self._last_success: datetime | None = None

    # --- kesif -----------------------------------------------------------
    def roots(self) -> tuple[Path, ...]:
        return config_dirs(self._env, self._home)

    def discover(self) -> tuple[SourceInstance, ...]:
        caps = self.capabilities()
        return tuple(
            instance_for(root, label=label, schema_verified=caps.schema_verified,
                         verified_at=caps.verified_at)
            for root, label in unique_labels(self.roots(), self._home)
        )

    def probe_roots(self) -> tuple[ProbeRoot, ...]:
        out: list[ProbeRoot] = []
        raw = self._env.get("CLAUDE_CONFIG_DIR", "").strip()
        candidates = ([Path(os.path.expandvars(p.strip())).expanduser() for p in raw.split(",") if p.strip()]
                      if raw else [self._home / ".claude", self._home / ".config" / "claude"])
        for c in candidates:
            out.append(ProbeRoot(path=str(c), label="config dir", exists=c.is_dir()))
            out.append(ProbeRoot(path=str(projects_dir(c)), label="projects (transcripts)",
                                 exists=projects_dir(c).is_dir()))
            out.append(ProbeRoot(path=str(credentials_path(c)), label="credentials (yalniz varlik)",
                                 exists=credentials_path(c).is_file()))
        return tuple(out)

    def capabilities(self) -> Capabilities:
        return Capabilities(
            tokens=True, cost_vendor=True, quota=True, sessions=True, tools=True,
            attribution=True, realtime=True, history_days=30, account_scope="local",
            schema_verified=True, verified_at=SCHEMA_VERIFIED_AT,
            retroactive_reconciliation=False,
        )

    # --- toplama (Stage 3'te dolacak) -------------------------------------
    def collect(self, instance: SourceInstance, cursor: Cursor) -> RawBatch:
        return RawBatch(instance=instance, items=(), complete=True, next_cursor=cursor)

    def normalize(self, batch: RawBatch) -> tuple[Any, ...]:
        return ()

    # --- saglik ------------------------------------------------------------
    def health(self) -> Health:
        roots = self.roots()
        if not roots:
            return Health(status="down", error_class="no_config_dir",
                          detail="Claude Code kok dizini bulunamadi")
        transcripts = sum(len(find_transcripts(r)) for r in roots)
        if transcripts == 0:
            return Health(status="degraded", error_class="no_transcripts",
                          detail="projects/ altinda transcript yok")
        return Health(status="ok", last_success_at=datetime.now(UTC),
                      detail=f"{len(roots)} kok, {transcripts} transcript")
