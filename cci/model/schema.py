"""JSON sema disa aktarimi ve gizlilik etiketi denetimi.

`python -m cci.model.schema [dizin]` -> her model icin <Ad>.json (varsayilan docs/schema/).
"""

from __future__ import annotations

import json
import sys
import typing
from pathlib import Path
from typing import Iterator

from pydantic import BaseModel

from .alert import Action, Alert, Evidence, Recommendation, Subject
from .base import PRIVACY_CLASSES_ALLOWED
from .estimate import Estimate, ProjectedAtReset, QuotaForecast
from .figure import Band, EstimatorRef, Figure
from .ids import AccountRef, SessionRef, SourceInstance
from .quota import QuotaSnapshot, QuotaWindow, Spend, WindowScope
from .usage import (Attribution, CollectorRef, Cost, Flags, ModelRef, Timing, Tokens,
                    UsageRecord, Workspace)

ALL_MODELS: tuple[type[BaseModel], ...] = (
    EstimatorRef, Band, Figure,
    AccountRef, SourceInstance, SessionRef,
    Tokens, ModelRef, Attribution, Flags, Workspace, Timing, Cost, CollectorRef, UsageRecord,
    WindowScope, QuotaWindow, Spend, QuotaSnapshot,
    Estimate, ProjectedAtReset, QuotaForecast,
    Evidence, Subject, Alert, Action, Recommendation,
)

# Icerik tasiyabilecek alan adlari: semada gorunmeleri yasak (PRIVACY.md §2).
FORBIDDEN_FIELD_NAMES = frozenset({
    "content", "prompt", "messages", "body", "text", "arguments", "tool_input",
    "transcript", "response", "completion", "stdout", "stderr", "diff", "patch",
    "token", "access_token", "api_key", "authorization", "password", "secret",
})
FORBIDDEN_SUFFIXES = ("_content", "_text", "_token", "_secret")


def _submodels(annotation: object) -> Iterator[type[BaseModel]]:
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        yield annotation
        return
    for arg in typing.get_args(annotation):
        yield from _submodels(arg)


def iter_field_privacy(model: type[BaseModel], prefix: str = "") -> Iterator[tuple[str, str | None]]:
    """(alan yolu, gizlilik etiketi) ciftleri; ic modeller ozyinelemeli."""
    for name, info in model.model_fields.items():
        extra = info.json_schema_extra if isinstance(info.json_schema_extra, dict) else {}
        yield f"{prefix}{name}", extra.get("privacy")
        for sub in _submodels(info.annotation):
            yield from iter_field_privacy(sub, f"{prefix}{name}.")
    for name, info in model.model_computed_fields.items():
        extra = info.json_schema_extra if isinstance(info.json_schema_extra, dict) else {}
        yield f"{prefix}{name}", extra.get("privacy")


def check_privacy(models: tuple[type[BaseModel], ...] = ALL_MODELS) -> list[str]:
    """Ihlal listesi (bos = temiz)."""
    problems: list[str] = []
    for m in models:
        for path, privacy in iter_field_privacy(m):
            leaf = path.rsplit(".", 1)[-1]
            if privacy not in PRIVACY_CLASSES_ALLOWED:
                problems.append(f"{m.__name__}.{path}: gizlilik etiketi yok/yasak ({privacy!r})")
            if leaf in FORBIDDEN_FIELD_NAMES or leaf.endswith(FORBIDDEN_SUFFIXES):
                problems.append(f"{m.__name__}.{path}: yasak alan adi")
    return problems


def export(directory: Path) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for m in ALL_MODELS:
        schema = m.model_json_schema()
        path = directory / f"{m.__name__}.json"
        path.write_text(json.dumps(schema, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        written.append(path)
    return written


def main(argv: list[str]) -> int:
    problems = check_privacy()
    if problems:
        for p in problems:
            print("HATA:", p, file=sys.stderr)
        return 1
    target = Path(argv[1]) if len(argv) > 1 else Path("docs/schema")
    for p in export(target):
        print(p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
