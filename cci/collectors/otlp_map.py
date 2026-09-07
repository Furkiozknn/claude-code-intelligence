"""OTLP/JSON `ExportLogsServiceRequest` -> Envelope demeti (docs/EVENTS.md §3, notes/02 §A).

Ilkeler:
- Yalniz allow-list'teki oznitelikler kopyalanir; `prompt`, `response`, `error`,
  `tool_parameters`, `tool_input`, `body`, `user.email` ASLA kopyalanmaz.
- `api_request_body` / `api_response_body` olaylari her zaman dusurulur (sayacla);
  Research Mode ayri alici kullanir.
- Bilinmeyen olay adi -> dusur + sayac (hata degil).
- `user.account_uuid` -> account_key (tek hesap kimligi kaynagi, R-9).
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Iterable, Mapping

from cci import __version__
from cci.adapters.claude_code.adapter import SCHEMA_VERIFIED_AT
from cci.adapters.claude_code.models import model_ref
from cci.events.envelope import Envelope, SourceRef
from cci.model.evidence import EvidenceClass
from cci.model.figure import Figure, usd_to_nano
from cci.model.ids import AccountRef, SessionRef, SourceInstance
from cci.model.usage import (Attribution, CollectorRef, Cost, Flags, Timing, Tokens, UsageRecord)

COLLECTOR_NAME = "otlp"
COLLECTOR_VERSION = "0.0.1"
SCHEMA_VERSION = 1
PROVIDER = "anthropic"

RAW_BODY_EVENTS = frozenset({"api_request_body", "api_response_body"})
EVENT_MAP: dict[str, str] = {
    "api_request": "usage.request",
    "api_error": "usage.error",
    "api_refusal": "usage.refusal",
    "tool_result": "tool.call",
    "tool_decision": "tool.decision",
    "user_prompt": "prompt.submitted",
    "assistant_response": "prompt.responded",
    "permission_mode_changed": "permission.mode_changed",
    "mcp_server_connection": "mcp.connection",
}
# olay -> (kaynak oznitelik, hedef anahtar) ciftleri; listede olmayan hicbir sey gecmez
SIMPLE_FIELDS: dict[str, tuple[tuple[str, str], ...]] = {
    "usage.error": (("model", "model"), ("status_code", "status_code"), ("attempt", "attempt"),
                    ("duration_ms", "duration_ms"), ("error_class", "error_class"),
                    ("request_id", "request_id"), ("prompt.id", "prompt_id"), ("query_source", "query_source")),
    "usage.refusal": (("model", "model"), ("attempt", "attempt"), ("category", "category"),
                      ("request_id", "request_id"), ("prompt.id", "prompt_id")),
    "tool.call": (("tool_name", "tool_name"), ("tool_use_id", "tool_use_id"), ("success", "success"),
                  ("duration_ms", "duration_ms"), ("error_type", "error_type"),
                  ("tool_input_size_bytes", "input_size_bytes"), ("tool_result_size_bytes", "result_size_bytes"),
                  ("mcp_server_scope", "mcp_server_scope"), ("decision_source", "decision_source"),
                  ("decision_type", "decision_type"), ("prompt.id", "prompt_id")),
    "tool.decision": (("tool_name", "tool_name"), ("tool_use_id", "tool_use_id"), ("decision", "decision"),
                      ("tool_source", "tool_source"), ("source", "source"), ("prompt.id", "prompt_id")),
    "prompt.submitted": (("prompt.id", "prompt_id"), ("prompt_length", "prompt_length"),
                         ("command_name", "command_name"), ("command_source", "command_source"),
                         ("message.uuid", "message_uuid")),
    "prompt.responded": (("prompt.id", "prompt_id"), ("response_length", "response_length"),
                         ("model", "model"), ("request_id", "request_id"), ("message.uuid", "message_uuid"),
                         ("query_source", "query_source")),
    "permission.mode_changed": (("from_mode", "from_mode"), ("to_mode", "to_mode"), ("trigger", "trigger"),
                                ("prompt.id", "prompt_id")),
    "mcp.connection": (("server_name", "server_name"), ("status", "status"), ("transport_type", "transport_type"),
                       ("duration_ms", "duration_ms"), ("error_code", "error_code"),
                       ("server_scope", "server_scope"), ("is_plugin", "is_plugin")),
}

OTLP_SOURCE = SourceInstance(provider=PROVIDER, instance_id="otlp:claude-code", label="Claude Code (OTLP)",
                             kind="cli", network=False, schema_verified=True, verified_at=SCHEMA_VERIFIED_AT)
COLLECTOR = CollectorRef(name=COLLECTOR_NAME, version=COLLECTOR_VERSION, schema_version=SCHEMA_VERSION)


def any_value(v: Mapping[str, Any]) -> Any:
    """OTLP AnyValue -> Python."""
    if "stringValue" in v:
        return v["stringValue"]
    if "intValue" in v:
        try:
            return int(v["intValue"])
        except (TypeError, ValueError):
            return None
    if "doubleValue" in v:
        return float(v["doubleValue"])
    if "boolValue" in v:
        return bool(v["boolValue"])
    if "arrayValue" in v:
        return [any_value(x) for x in v["arrayValue"].get("values", []) if isinstance(x, Mapping)]
    if "kvlistValue" in v:
        return {kv.get("key"): any_value(kv.get("value", {})) for kv in v["kvlistValue"].get("values", [])
                if isinstance(kv, Mapping)}
    return None


def attributes(items: Iterable[Mapping[str, Any]] | None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for kv in items or ():
        if isinstance(kv, Mapping) and isinstance(kv.get("key"), str) and isinstance(kv.get("value"), Mapping):
            out[kv["key"]] = any_value(kv["value"])
    return out


def _ts(rec: Mapping[str, Any]) -> datetime:
    raw = rec.get("timeUnixNano") or rec.get("observedTimeUnixNano") or 0
    ns = int(raw) if raw else 0
    return datetime.fromtimestamp(ns / 1e9, UTC) if ns else datetime.now(UTC)


def event_name(rec: Mapping[str, Any], attrs: Mapping[str, Any]) -> str | None:
    for cand in (attrs.get("event.name"), attrs.get("event_name"),
                 (rec.get("body") or {}).get("stringValue") if isinstance(rec.get("body"), Mapping) else None):
        if isinstance(cand, str) and cand:
            return cand.removeprefix("claude_code.")
    return None


def _int(v: Any) -> int | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float) and v.is_integer():
        return int(v)
    if isinstance(v, str) and v.strip().lstrip("-").isdigit():
        return int(v)
    return None


def usage_record(attrs: Mapping[str, Any], resource: Mapping[str, Any], ts: datetime,
                 account: AccountRef | None) -> UsageRecord:
    tokens = Tokens(input=_int(attrs.get("input_tokens")) or 0, output=_int(attrs.get("output_tokens")) or 0,
                    cache_read=_int(attrs.get("cache_read_tokens")) or 0,
                    cache_write_total=_int(attrs.get("cache_creation_tokens")) or 0)
    vendor: Figure | None = None
    micros = _int(attrs.get("cost_usd_micros"))
    if micros is not None:
        vendor = Figure(value=Decimal(micros) * 1000, unit="nanoUSD", evidence_class=EvidenceClass.VENDOR_ESTIMATED,
                        released=True, released_as="reconciled")
    elif isinstance(attrs.get("cost_usd"), (int, float)) and not isinstance(attrs.get("cost_usd"), bool):
        vendor = Figure(value=usd_to_nano(attrs["cost_usd"]), unit="nanoUSD",
                        evidence_class=EvidenceClass.VENDOR_ESTIMATED, released=True, released_as="reconciled")
    session_id = str(resource.get("session.id") or attrs.get("session.id") or "unknown-session")
    qs = attrs.get("query_source")
    speed = attrs.get("speed")
    return UsageRecord(
        provider=PROVIDER, source=OTLP_SOURCE, account=account,
        session=SessionRef(session_id=session_id),
        prompt_id=attrs.get("prompt.id") if isinstance(attrs.get("prompt.id"), str) else None,
        request_id=attrs.get("request_id") if isinstance(attrs.get("request_id"), str) else None,
        uuid=attrs.get("client_request_id") if isinstance(attrs.get("client_request_id"), str) else None,
        ts=ts, model=model_ref(attrs.get("model") if isinstance(attrs.get("model"), str) else None),
        tokens=tokens,
        cost=Cost(usd=Figure.withheld("nanoUSD", EvidenceClass.ESTIMATED, "fiyat tablosu henuz uygulanmadi"),
                  vendor_usd=vendor),
        timing=Timing(duration_ms=_int(attrs.get("duration_ms"))),
        attribution=Attribution(
            query_source=qs if qs in ("main", "subagent", "auxiliary") else None,
            agent=attrs.get("agent.name") if isinstance(attrs.get("agent.name"), str) else None,
            skill=attrs.get("skill.name") if isinstance(attrs.get("skill.name"), str) else None,
            plugin=attrs.get("plugin.name") if isinstance(attrs.get("plugin.name"), str) else None,
            mcp_server=attrs.get("mcp_server.name") if isinstance(attrs.get("mcp_server.name"), str) else None,
            mcp_tool=attrs.get("mcp_tool.name") if isinstance(attrs.get("mcp_tool.name"), str) else None,
            marketplace=attrs.get("marketplace.name") if isinstance(attrs.get("marketplace.name"), str) else None,
            speed="fast" if speed == "fast" else ("standard" if speed in ("normal", "standard") else None),
            effort=attrs.get("effort") if isinstance(attrs.get("effort"), str) else None,
        ),
        flags=Flags(), evidence_class=EvidenceClass.OBSERVED, collector=COLLECTOR,
    )


class OtlpLogMapper:
    def __init__(self) -> None:
        self.counters: Counter[str] = Counter()

    def map_request(self, doc: Mapping[str, Any]) -> list[Envelope]:
        out: list[Envelope] = []
        for rl in doc.get("resourceLogs", []) or []:
            if not isinstance(rl, Mapping):
                continue
            resource = attributes((rl.get("resource") or {}).get("attributes"))
            for sl in rl.get("scopeLogs", []) or []:
                if not isinstance(sl, Mapping):
                    continue
                for rec in sl.get("logRecords", []) or []:
                    if isinstance(rec, Mapping):
                        env = self.map_record(rec, resource)
                        if env is not None:
                            out.append(env)
        return out

    def map_record(self, rec: Mapping[str, Any], resource: Mapping[str, Any]) -> Envelope | None:
        attrs = attributes(rec.get("attributes"))
        merged = {**resource, **attrs}
        name = event_name(rec, attrs)
        if name is None:
            self.counters["dropped_no_event_name"] += 1
            return None
        if name in RAW_BODY_EVENTS:
            self.counters["dropped_raw_body"] += 1
            return None
        etype = EVENT_MAP.get(name)
        if etype is None:
            self.counters["dropped_unknown_event"] += 1
            return None
        ts = _ts(rec)
        account_uuid = merged.get("user.account_uuid")
        account = AccountRef(provider=PROVIDER, account_key=str(account_uuid)) if account_uuid else None
        session_id = merged.get("session.id")
        source = SourceRef(collector=COLLECTOR_NAME, instance_id=OTLP_SOURCE.instance_id,
                           collector_version=COLLECTOR_VERSION, schema_version=SCHEMA_VERSION)
        if etype == "usage.request":
            record = usage_record(merged, resource, ts, account)
            payload = record.model_dump(mode="json")
        else:
            payload = {}
            for src, dst in SIMPLE_FIELDS[etype]:
                v = merged.get(src)
                if v is not None and isinstance(v, (str, int, float, bool)):
                    payload[dst] = v
        self.counters["mapped"] += 1
        return Envelope(type=etype, ts=ts, source=source, provider=PROVIDER,
                        account_key=account.account_key if account else None,
                        session_id=str(session_id) if session_id else None,
                        privacy_class="internal", evidence_class=EvidenceClass.OBSERVED, payload=payload)
