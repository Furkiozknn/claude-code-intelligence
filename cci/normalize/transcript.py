"""Soyulmus transcript kaydi (collectors.transcript.strip_content ciktisi) -> UsageRecord.

Kurallar (tycho SCHEMA.md, ccusage adaptor README, VibeBill contracts):
- yalniz `type == "assistant"` ve `message.usage` olan kayitlar;
- sentetik (`model == "<synthetic>"` / `isApiErrorMessage`) -> token 0, flags.synthetic;
- `usage.cache_creation.ephemeral_5m/1h` -> 5m/1h; toplamla uyusmazsa kirilim None + sayac;
- `usage.iterations[type=advisor_message]` -> AYRI kayit (`<id>:advisor:<i>`, request_id yok);
  ust seviye usage sifir ve advisor disi iterasyon varsa toplamlari kullan;
- atif: attributionSkill/Agent/Plugin/McpServer/McpTool; `agentId` varsa query_source=subagent;
- proje anahtari = sha256(cwd)[:16] (sensitive alan, hash'li).
"""

from __future__ import annotations

import hashlib
from collections import Counter
from datetime import UTC, datetime
from typing import Any, Mapping

from cci.adapters.base import RawBatch
from cci.adapters.claude_code.models import SYNTHETIC, model_ref
from cci.collectors.transcript import COLLECTOR_NAME, COLLECTOR_VERSION, SCHEMA_VERSION
from cci.model.evidence import EvidenceClass
from cci.model.figure import Figure, usd_to_nano
from cci.model.ids import AccountRef, SessionRef, SourceInstance
from cci.model.usage import (Attribution, CollectorRef, Cost, Flags, Tokens, Timing, UsageRecord, Workspace)

COLLECTOR = CollectorRef(name=COLLECTOR_NAME, version=COLLECTOR_VERSION, schema_version=SCHEMA_VERSION)
ADVISOR = "advisor_message"


def _int(v: Any) -> int:
    if isinstance(v, bool):
        return 0
    if isinstance(v, int):
        return max(0, v)
    if isinstance(v, float) and v.is_integer():
        return max(0, int(v))
    return 0


def _ts(raw: Any) -> datetime | None:
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        # ms epoch (Pi tarzi) - tycho: yanlis alan yil 58486 uretir; sinir sonra dogrulanir
        return datetime.fromtimestamp(float(raw) / 1000.0, UTC) if raw > 1e11 else datetime.fromtimestamp(float(raw), UTC)
    if isinstance(raw, str) and raw:
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    return None


def _tokens(usage: Mapping[str, Any], counters: Counter[str]) -> Tokens:
    total = _int(usage.get("cache_creation_input_tokens"))
    split = usage.get("cache_creation")
    five = one = None
    if isinstance(split, Mapping):
        five = _int(split.get("ephemeral_5m_input_tokens"))
        one = _int(split.get("ephemeral_1h_input_tokens"))
        if five + one != total:
            if total == 0 and five + one > 0:
                total = five + one  # bazi surumlerde toplam alani eksik
            else:
                counters["cache_ttl_mismatch"] += 1
                five = one = None
    return Tokens(input=_int(usage.get("input_tokens")), output=_int(usage.get("output_tokens")),
                  cache_read=_int(usage.get("cache_read_input_tokens")), cache_write_5m=five,
                  cache_write_1h=one, cache_write_total=total)


def _zero(t: Tokens) -> bool:
    return t.billable_total == 0


def _sum_iterations(iterations: list[Mapping[str, Any]], counters: Counter[str]) -> Tokens | None:
    acc = Counter()
    n = 0
    for it in iterations:
        if it.get("type") == ADVISOR or not isinstance(it.get("usage"), Mapping):
            continue
        u = it["usage"]
        for k in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"):
            acc[k] += _int(u.get(k))
        n += 1
    if n == 0:
        return None
    counters["iterations_summed"] += 1
    return Tokens(input=acc["input_tokens"], output=acc["output_tokens"], cache_read=acc["cache_read_input_tokens"],
                  cache_write_total=acc["cache_creation_input_tokens"])


def records_from_transcript(payload: Mapping[str, Any], instance: SourceInstance,
                            account: AccountRef | None, counters: Counter[str] | None = None) -> list[UsageRecord]:
    counters = counters if counters is not None else Counter()
    if payload.get("type") != "assistant":
        counters["skipped_non_assistant"] += 1
        return []
    msg = payload.get("message")
    if not isinstance(msg, Mapping) or not isinstance(msg.get("usage"), Mapping):
        counters["skipped_no_usage"] += 1
        return []
    ts = _ts(payload.get("timestamp"))
    if ts is None:
        counters["skipped_bad_timestamp"] += 1
        return []
    session_id = payload.get("sessionId") or payload.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        counters["skipped_no_session"] += 1
        return []
    usage: Mapping[str, Any] = msg["usage"]
    model_id = msg.get("model") if isinstance(msg.get("model"), str) else None
    synthetic = model_id == SYNTHETIC or bool(payload.get("isApiErrorMessage"))
    agent_id = payload.get("agentId") if isinstance(payload.get("agentId"), str) else None
    session = SessionRef(session_id=session_id, agent_id=agent_id, is_sidechain=bool(payload.get("isSidechain")))
    cwd = payload.get("cwd") if isinstance(payload.get("cwd"), str) and payload.get("cwd") else None
    workspace = Workspace(project_key=hashlib.sha256(cwd.encode("utf-8")).hexdigest()[:16],
                          git_branch=payload.get("gitBranch") if isinstance(payload.get("gitBranch"), str) else None) if cwd else None
    attribution = Attribution(
        query_source="subagent" if agent_id else None,
        agent=payload.get("attributionAgent") if isinstance(payload.get("attributionAgent"), str) else None,
        skill=payload.get("attributionSkill") if isinstance(payload.get("attributionSkill"), str) else None,
        plugin=payload.get("attributionPlugin") if isinstance(payload.get("attributionPlugin"), str) else None,
        mcp_server=payload.get("attributionMcpServer") if isinstance(payload.get("attributionMcpServer"), str) else None,
        mcp_tool=payload.get("attributionMcpTool") if isinstance(payload.get("attributionMcpTool"), str) else None,
        speed="fast" if usage.get("speed") == "fast" else None,
    )
    vendor = None
    if isinstance(payload.get("costUSD"), (int, float)) and not isinstance(payload.get("costUSD"), bool):
        vendor = Figure(value=usd_to_nano(payload["costUSD"]), unit="nanoUSD", released=True,
                        released_as="reconciled", evidence_class=EvidenceClass.VENDOR_ESTIMATED)
    base = dict(provider="anthropic", source=instance, account=account, session=session,
                message_id=msg.get("id") if isinstance(msg.get("id"), str) else None,
                request_id=payload.get("requestId") if isinstance(payload.get("requestId"), str) else None,
                uuid=payload.get("uuid") if isinstance(payload.get("uuid"), str) else None,
                ts=ts, attribution=attribution, workspace=workspace, collector=COLLECTOR,
                timing=Timing(duration_ms=_int(payload.get("durationMs")) or None),
                evidence_class=EvidenceClass.OBSERVED)
    withheld = Figure.withheld("nanoUSD", EvidenceClass.ESTIMATED, "fiyat tablosu henuz uygulanmadi")

    out: list[UsageRecord] = []
    tokens = _tokens(usage, counters)
    iterations = [it for it in usage.get("iterations", []) if isinstance(it, Mapping)] if isinstance(usage.get("iterations"), list) else []
    if synthetic:
        counters["synthetic"] += 1
        tokens = Tokens(input=0, output=0)
        flags = Flags(synthetic=True, api_error=True)
    else:
        if _zero(tokens) and iterations:
            summed = _sum_iterations(iterations, counters)
            if summed is not None:
                tokens = summed
        flags = Flags()
    out.append(UsageRecord(**base, model=model_ref(model_id), tokens=tokens,
                           cost=Cost(usd=withheld, vendor_usd=vendor), flags=flags))

    for i, it in enumerate(iterations):
        if it.get("type") != ADVISOR or not isinstance(it.get("usage"), Mapping):
            continue
        counters["advisor"] += 1
        adv = {**base, "message_id": f"{base['message_id'] or base['uuid']}:advisor:{i}", "request_id": None,
               "uuid": None}
        out.append(UsageRecord(**adv, model=model_ref(it.get("model") if isinstance(it.get("model"), str) else None),
                               tokens=_tokens(it["usage"], counters), cost=Cost(usd=withheld, vendor_usd=None),
                               flags=Flags(advisor=True, iteration_index=i)))
    return out


def normalize_transcript_batch(batch: RawBatch, account: AccountRef | None = None) -> tuple[list[UsageRecord], Counter[str]]:
    counters: Counter[str] = Counter()
    records: list[UsageRecord] = []
    for item in batch.items:
        if item.kind != "transcript_record":
            counters["skipped_kind"] += 1
            continue
        try:
            records.extend(records_from_transcript(item.payload, batch.instance, account, counters))
        except ValueError:
            counters["skipped_invalid"] += 1
    return records, counters
