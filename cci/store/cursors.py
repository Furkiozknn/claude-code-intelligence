"""Toplayici imlecleri (Cursor) icin kalici dosya: `cursors.json` (atomik yazim, 0600).

Icerik dosya yollari tasidigi icin `sensitive`; yalniz kullanici dizininde.
Bozuk dosya -> bos imlec (sessiz tam yeniden tarama; VibeBill manifest kurali).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import ValidationError

from cci.adapters.base import Cursor


def load_cursors(path: Path) -> dict[str, Cursor]:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out: dict[str, Cursor] = {}
    if isinstance(doc, dict):
        for key, value in doc.items():
            try:
                out[str(key)] = Cursor.model_validate(value)
            except ValidationError:
                continue
    return out


def save_cursors(path: Path, cursors: dict[str, Cursor]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    payload = {k: v.model_dump(mode="json") for k, v in cursors.items()}
    tmp.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    if os.name != "nt":
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
    os.replace(tmp, path)
