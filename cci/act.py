"""Stage 14 - act gunlugu (codeburn kalibi, sade): dosya degisikligi = yedek -> hash -> yaz -> gunluk; geri alinabilir.

<data_dir>/act/journal.jsonl  + <data_dir>/act/<id>/backup
ponytail: tek dosyalik plan; cok dosyali plan gerekince listeye cevir.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path

from cci.events.envelope import new_ulid


def _sha(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def _journal(data_dir: Path) -> Path:
    return data_dir / "act" / "journal.jsonl"


def _append(data_dir: Path, rec: dict) -> dict:
    j = _journal(data_dir)
    j.parent.mkdir(parents=True, exist_ok=True)
    with j.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def list_records(data_dir: Path) -> list[dict]:
    j = _journal(data_dir)
    if not j.exists():
        return []
    return [json.loads(line) for line in j.read_text(encoding="utf-8").splitlines() if line.strip()]


def apply_file_change(data_dir: Path, path: Path, new_text: str, description: str, *, expected_hash: str | None = None,
                      rec_id: str | None = None) -> dict:
    """Bayat plan korumasi: `expected_hash` verilmis ve dosya degismisse yazmaz."""
    before = _sha(path)
    if expected_hash is not None and before != expected_hash:
        raise RuntimeError(f"{path.name} plan kurulduktan sonra degisti; yeniden planla")
    rid = rec_id or new_ulid()
    backup = None
    if path.exists():
        bdir = data_dir / "act" / rid
        bdir.mkdir(parents=True, exist_ok=True)
        backup = bdir / "backup"
        shutil.copy2(path, backup)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(new_text, encoding="utf-8")
    os.replace(tmp, path)
    return _append(data_dir, {"id": rid, "at": datetime.now(UTC).isoformat(), "kind": "file_change", "path": str(path),
                              "backup": str(backup) if backup else None, "hash_before": before, "hash_after": _sha(path),
                              "description": description, "status": "applied"})


def undo(data_dir: Path, rec_id: str, *, force: bool = False) -> dict:
    recs = [r for r in list_records(data_dir) if r["id"] == rec_id or r["id"].startswith(rec_id)]
    if not recs:
        raise KeyError("kayit yok")
    rec = recs[0]
    if any(r.get("kind") == "undo" and r.get("of") == rec["id"] for r in list_records(data_dir)):
        raise RuntimeError("zaten geri alinmis")
    path = Path(rec["path"])
    if not force and _sha(path) != rec["hash_after"]:
        raise RuntimeError(f"{path.name} uygulandiktan sonra degismis; --force ile zorla")
    if rec["backup"]:
        shutil.copy2(rec["backup"], path)
    elif path.exists():
        path.unlink()
    return _append(data_dir, {"id": new_ulid(), "at": datetime.now(UTC).isoformat(), "kind": "undo", "of": rec["id"],
                              "path": rec["path"], "status": "reverted", "hash_after": _sha(path)})
