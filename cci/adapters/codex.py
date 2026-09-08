"""Stage 15 - Codex adaptoru (docs/PROVIDERS.md §5, doğrulanmış format gerçekleri).

`~/.codex/sessions/**/rollout-*.jsonl`:
  {"type":"event_msg","payload":{"type":"token_count","last_token_usage":{...}}}
  input_tokens cache DAHIL -> input = input_tokens - cached_input_tokens
  model `turn_context`ten; yoksa codex-unknown (sifir fiyatli, unknown=True)
  session_meta.payload.thread_source=="subagent" -> tum olaylar sidechain
  dedup: codex:<dosya>:<index> (dosya bazli)
ponytail: govde yok, yalniz sayilar; fiyat tablosu Anthropic'e ozel oldugundan
maliyet withheld (Codex fiyatlari eklenince PricingTable'a openai snapshot'i konur.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Mapping

from cci.adapters.base import Capabilities, Cursor, FileCursor, Health, ProbeRoot, ProviderAdapter, RawBatch, RawItem
from cci.collectors.transcript import read_new_lines
from cci.model.evidence import EvidenceClass
from cci.model.figure import Figure
from cci.model.ids import SessionRef, SourceInstance
from cci.model.usage import Attribution, CollectorRef, Cost, Flags, ModelRef, Tokens, UsageRecord

SCHEMA_VERIFIED_AT = date(2026, 9, 7)
COLLECTOR = CollectorRef(name="codex-rollout", version="0.0.1", schema_version=1)
UNKNOWN_MODEL = "codex-unknown"


def sessions_dir(env: Mapping[str, str] | None = None, home: Path | None = None) -> Path:
    env = os.environ if env is None else env
    base = Path(env["CODEX_HOME"]).expanduser() if env.get("CODEX_HOME") else (home or Path.home()) / ".codex"
    return base / "sessions"


def _int(v: Any) -> int:
    return max(0, int(v)) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0


def records_from_rollout(lines: list[tuple[int, dict]], instance: SourceInstance, rel: str) -> list[UsageRecord]:
    """Bir rollout dosyasinin satirlari -> UsageRecord'lar. Saf."""
    out: list[UsageRecord] = []
    model: str | None = None
    first_model: str | None = None
    sidechain = False
    session_id = rel
    for index, obj in lines:
        payload = obj.get("payload") if isinstance(obj.get("payload"), dict) else {}
        ptype = payload.get("type") or obj.get("type")
        if ptype == "session_meta":
            if payload.get("thread_source") == "subagent":
                sidechain = True
            if isinstance(payload.get("id"), str):
                session_id = payload["id"]
            continue
        if ptype == "turn_context":
            m = payload.get("model")
            if isinstance(m, str) and m:
                model = m
                first_model = first_model or m
            continue
        if ptype != "token_count":
            continue
        usage = payload.get("last_token_usage")
        if not isinstance(usage, Mapping):
            continue
        cached = _int(usage.get("cached_input_tokens"))
        total_in = _int(usage.get("input_tokens"))
        ts_raw = obj.get("timestamp")
        try:
            ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00")) if ts_raw else None
        except ValueError:
            ts = None
        if ts is None:
            continue
        out.append(UsageRecord(
            provider="openai", source=instance, session=SessionRef(session_id=session_id, is_sidechain=sidechain),
            uuid=f"codex:{rel}:{index}", ts=ts if ts.tzinfo else ts.replace(tzinfo=UTC),
            model=ModelRef(id=model or UNKNOWN_MODEL, display=model or UNKNOWN_MODEL, unknown=model is None),
            tokens=Tokens(input=max(0, total_in - cached), output=_int(usage.get("output_tokens")), cache_read=cached,
                          reasoning=_int(usage.get("reasoning_output_tokens")) or None),
            cost=Cost(usd=Figure.withheld("nanoUSD", EvidenceClass.ESTIMATED, "Codex fiyat tablosu yok")),
            attribution=Attribution(query_source="subagent" if sidechain else None), flags=Flags(), collector=COLLECTOR))
    if first_model:  # geri doldurma: ilk turn_context'ten once gelen kayitlar
        out = [r if not r.model.unknown else r.model_copy(update={"model": ModelRef(id=first_model, display=first_model)})
               for r in out]
    return out


class CodexAdapter(ProviderAdapter):
    name = "codex"
    provider = "openai"

    def __init__(self, env: Mapping[str, str] | None = None, home: Path | None = None) -> None:
        self._env = dict(os.environ if env is None else env)
        self._home = home or Path.home()

    def root(self) -> Path:
        return sessions_dir(self._env, self._home)

    def discover(self) -> tuple[SourceInstance, ...]:
        root = self.root()
        if not root.is_dir():
            return ()
        return (SourceInstance(provider="openai", instance_id="codex:local", label="Codex", kind="cli",
                               root_path=str(root), schema_verified=True, verified_at=SCHEMA_VERIFIED_AT),)

    def probe_roots(self) -> tuple[ProbeRoot, ...]:
        root = self.root()
        return (ProbeRoot(path=str(root), label="codex sessions", exists=root.is_dir()),)

    def capabilities(self) -> Capabilities:
        return Capabilities(tokens=True, sessions=True, attribution=False, history_days=None, account_scope="local",
                            schema_verified=True, verified_at=SCHEMA_VERIFIED_AT)

    def collect(self, instance: SourceInstance, cursor: Cursor) -> RawBatch:
        root = Path(instance.root_path or "")
        items: list[RawItem] = []
        files: dict[str, FileCursor] = {}
        skipped = 0
        for path in sorted(root.rglob("rollout-*.jsonl")):
            key = path.relative_to(root).as_posix()
            try:
                st = path.stat()
            except OSError:
                skipped += 1
                continue
            prev = cursor.files.get(key)
            start = prev.bytes_consumed if prev and st.st_size >= prev.size else 0
            if prev and start == st.st_size and prev.mtime_ns == st.st_mtime_ns:
                files[key] = prev
                continue
            consumed, records, n_skip = read_new_lines(path, start)
            skipped += n_skip
            for offset, obj in records:
                items.append(RawItem(kind="codex_rollout", ref=f"{key}@{offset}", payload=_strip(obj)))
            files[key] = FileCursor(size=st.st_size, mtime_ns=st.st_mtime_ns, bytes_consumed=consumed)
        return RawBatch(instance=instance, items=tuple(items), complete=True,
                        next_cursor=Cursor(files=files, since=datetime.now(UTC)), skipped=skipped)

    def normalize(self, batch: RawBatch) -> tuple[UsageRecord, ...]:
        groups: dict[str, list[tuple[int, dict]]] = {}
        for item in batch.items:
            rel, _, off = item.ref.partition("@")
            groups.setdefault(rel, []).append((int(off or 0), item.payload))
        out: list[UsageRecord] = []
        for rel, lines in groups.items():
            out.extend(records_from_rollout(sorted(lines), batch.instance, rel))
        return tuple(out)

    def health(self) -> Health:
        root = self.root()
        if not root.is_dir():
            return Health(status="down", error_class="no_codex_dir", detail="~/.codex/sessions yok")
        n = sum(1 for _ in root.rglob("rollout-*.jsonl"))
        return Health(status="ok" if n else "degraded", last_success_at=datetime.now(UTC) if n else None,
                      error_class=None if n else "no_rollouts", detail=f"{n} rollout")


KEEP = frozenset({"type", "timestamp", "payload"})
KEEP_PAYLOAD = frozenset({"type", "model", "thread_source", "id", "last_token_usage"})
KEEP_USAGE = frozenset({"input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens", "total_tokens"})


def _strip(obj: Mapping[str, Any]) -> dict[str, Any]:
    """Icerik soyma: yalniz sayi/kimlik alanlari (prompt/response asla)."""
    out = {k: v for k, v in obj.items() if k in KEEP and not isinstance(v, (dict, list))}
    p = obj.get("payload")
    if isinstance(p, Mapping):
        pp = {k: v for k, v in p.items() if k in KEEP_PAYLOAD and isinstance(v, (str, int, float, bool))}
        u = p.get("last_token_usage")
        if isinstance(u, Mapping):
            pp["last_token_usage"] = {k: v for k, v in u.items() if k in KEEP_USAGE and isinstance(v, (int, float))}
        out["payload"] = pp
    return out
