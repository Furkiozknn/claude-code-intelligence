"""Transcript izleyici (Claude Code `~/.claude/projects/**/*.jsonl`).

Ilkeler:
- ARTIMLI: dosya basina (size, mtime_ns, bytes_consumed) imleci (VibeBill manifest
  kalibi). Yarim kalan son satir tuketilmez; dosya kuculmusse bastan okunur.
- ICERIK SOYMA OKUMA ANINDA: `strip_content` yalniz allow-list'teki anahtarlari
  birakir. `message.content`, `toolUseResult`, prompt metni vb. RawItem'a bile
  girmez. Arac kullanimindan yalniz arac adi + `file_path` alinir (VibeBill).
- Bozuk satir: atla + say (`skipped`); tek bozuk dosya digerlerini dusurmez.
- SALT OKUNUR: hicbir dosyaya yazilmaz.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

from cci.adapters.base import Cursor, FileCursor, RawBatch, RawItem
from cci.adapters.claude_code.paths import find_transcripts, projects_dir
from cci.model.ids import SourceInstance

COLLECTOR_NAME = "transcript"
COLLECTOR_VERSION = "0.0.1"
SCHEMA_VERSION = 1

# tycho SCHEMA.md zarf alanlari + atif alanlari. Icerik tasiyan hicbir alan yok.
TRANSCRIPT_KEEP_TOP: frozenset[str] = frozenset({
    "type", "uuid", "parentUuid", "timestamp", "sessionId", "session_id", "requestId",
    "cwd", "gitBranch", "version", "isSidechain", "agentId", "isApiErrorMessage",
    "isCompactSummary", "isMeta", "attributionSkill", "attributionAgent", "attributionPlugin",
    "attributionMcpServer", "attributionMcpTool", "advisorModel", "slug", "costUSD",
    "durationMs", "userType", "entrypoint",
})
TRANSCRIPT_KEEP_MESSAGE: frozenset[str] = frozenset({
    "id", "model", "role", "type", "stop_reason", "usage",
})
ITERATION_KEEP: frozenset[str] = frozenset({"type", "model", "usage"})
EDIT_TOOLS: frozenset[str] = frozenset({"Edit", "Write", "MultiEdit", "NotebookEdit"})


def _strip_usage(usage: Any) -> Any:
    if not isinstance(usage, Mapping):
        return usage
    out: dict[str, Any] = {}
    for k, v in usage.items():
        if k == "iterations" and isinstance(v, list):
            out[k] = [{kk: vv for kk, vv in it.items() if kk in ITERATION_KEEP}
                      for it in v if isinstance(it, Mapping)]
        elif isinstance(v, (int, float, str, bool)) or v is None:
            out[k] = v
        elif isinstance(v, Mapping):
            # cache_creation{ephemeral_5m_input_tokens, ephemeral_1h_input_tokens}, server_tool_use{...}
            out[k] = {kk: vv for kk, vv in v.items() if isinstance(vv, (int, float, str, bool)) or vv is None}
    return out


def _tool_uses(content: Any) -> list[dict[str, str]]:
    """Icerik bloklarindan YALNIZ arac adi ve (duzenleme araclarinda) dosya yolu."""
    if not isinstance(content, list):
        return []
    out: list[dict[str, str]] = []
    for block in content:
        if not isinstance(block, Mapping) or block.get("type") != "tool_use":
            continue
        name = block.get("name")
        if not isinstance(name, str):
            continue
        item: dict[str, str] = {"name": name}
        inp = block.get("input")
        if name in EDIT_TOOLS and isinstance(inp, Mapping):
            fp = inp.get("file_path") or inp.get("notebook_path")
            if isinstance(fp, str):
                item["file_path"] = fp
        out.append(item)
    return out


def strip_content(record: Mapping[str, Any]) -> dict[str, Any]:
    """Allow-list soyma. Donen sozlukte icerik alani yoktur (test: yasak anahtar taramasi)."""
    out: dict[str, Any] = {}
    for k, v in record.items():
        if k in TRANSCRIPT_KEEP_TOP and (isinstance(v, (int, float, str, bool)) or v is None):
            out[k] = v
    msg = record.get("message")
    if isinstance(msg, Mapping):
        m: dict[str, Any] = {}
        for k, v in msg.items():
            if k == "usage":
                m["usage"] = _strip_usage(v)
            elif k in TRANSCRIPT_KEEP_MESSAGE and (isinstance(v, (int, float, str, bool)) or v is None):
                m[k] = v
        tools = _tool_uses(msg.get("content"))
        if tools:
            m["tool_uses"] = tools
        out["message"] = m
    return out


def read_new_lines(path: Path, start: int, max_line_bytes: int = 1_000_000
                   ) -> tuple[int, list[tuple[int, dict[str, Any]]], int]:
    """`start` baytindan itibaren tam satirlari okur.
    Doner: (yeni bytes_consumed, [(offset, kayit)], atlanan satir sayisi).
    Yarim son satir tuketilmez; asiri uzun satir atlanir ama tuketilir."""
    with path.open("rb") as fh:
        fh.seek(start)
        data = fh.read()
    if not data:
        return start, [], 0
    records: list[tuple[int, dict[str, Any]]] = []
    skipped = 0
    consumed = start
    pos = 0
    while True:
        nl = data.find(b"\n", pos)
        if nl < 0:
            break  # yarim satir: birakip cik
        line = data[pos:nl]
        offset = start + pos
        pos = nl + 1
        consumed = start + pos
        stripped = line.strip()
        if not stripped:
            continue
        if len(stripped) > max_line_bytes:
            skipped += 1
            continue
        try:
            obj = json.loads(stripped)
        except ValueError:
            skipped += 1
            continue
        if isinstance(obj, dict):
            records.append((offset, obj))
        else:
            skipped += 1
    return consumed, records, skipped


class TranscriptCollector:
    name = COLLECTOR_NAME
    version = COLLECTOR_VERSION
    schema_version = SCHEMA_VERSION

    def __init__(self, max_line_bytes: int = 1_000_000) -> None:
        self._max_line = max_line_bytes

    def collect(self, instance: SourceInstance, cursor: Cursor) -> RawBatch:
        if not instance.root_path:
            return RawBatch(instance=instance, complete=True, next_cursor=cursor)
        root = Path(instance.root_path)
        base = projects_dir(root)
        items: list[RawItem] = []
        files: dict[str, FileCursor] = {}
        skipped = 0
        for path in find_transcripts(root):
            key = path.relative_to(base).as_posix()  # projects/ altina goreli (proje/oturum yolu)
            try:
                st = path.stat()
            except OSError:
                skipped += 1
                continue
            prev = cursor.files.get(key)
            start = 0
            if prev is not None and st.st_size >= prev.size and prev.bytes_consumed <= st.st_size:
                start = prev.bytes_consumed
            if start == st.st_size and prev is not None and prev.mtime_ns == st.st_mtime_ns:
                files[key] = prev
                continue
            try:
                consumed, records, n_skip = read_new_lines(path, start, self._max_line)
            except OSError:
                skipped += 1
                files[key] = prev if prev is not None else FileCursor(size=0, mtime_ns=0, bytes_consumed=0)
                continue
            skipped += n_skip
            for offset, obj in records:
                items.append(RawItem(kind="transcript_record", ref=f"{key}@{offset}",
                                     payload=strip_content(obj)))
            files[key] = FileCursor(size=st.st_size, mtime_ns=st.st_mtime_ns, bytes_consumed=consumed)
        return RawBatch(instance=instance, items=tuple(items), complete=True,
                        next_cursor=Cursor(files=files, since=datetime.now(UTC)), skipped=skipped)
