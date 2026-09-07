"""Allow-list ingest kapisi (cacheeconomics kalibi; docs/PRIVACY.md §2).

Kurallar:
1. Olay turu basina izinli anahtar kumesi; disi -> RED (`rejected_extra_key`).
2. `FORBIDDEN_KEYS` ozyinelemeli tarama -> RED (`rejected_forbidden_key`);
   red gerekcesi ANAHTAR ADINI ICERMEZ (log'a sizmasin).
3. Zarf > 64 KB -> RED (`rejected_too_large`).
4. Bilinmeyen tur -> DUSUR (`dropped_unknown_type`); hata degil.
Sayaclar `collector.health` ve `doctor` icin.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from cci.events.envelope import EVENT_TYPES, Envelope, canonical_json
from cci.model.quota import QuotaSnapshot
from cci.model.usage import UsageRecord

MAX_ENVELOPE_BYTES = 64 * 1024

FORBIDDEN_KEYS: frozenset[str] = frozenset({
    "content", "prompt", "messages", "body", "text", "arguments", "args", "tool_input",
    "tool_output", "transcript", "response", "completion", "stdout", "stderr", "diff", "patch",
    "token", "access_token", "refresh_token", "api_key", "authorization", "cookie",
    "password", "secret", "email", "user_email",
})
FORBIDDEN_SUFFIXES: tuple[str, ...] = ("_content", "_text", "_token", "_secret", "_body")


def _model_keys(model: type) -> frozenset[str]:
    return frozenset(model.model_fields) | frozenset(getattr(model, "model_computed_fields", {}))


_HEALTH = frozenset({"status", "last_success_at", "lag_s", "error_class", "retry_after_s", "detail",
                     "queue_depth", "dropped", "rejected", "parse_errors", "events_per_s"})
_SESSION = frozenset({"start_type", "entrypoint", "version", "reason", "trigger",
                      "tokens_before", "tokens_after", "seconds", "kind"})
_TOOL = frozenset({"tool_name", "tool_use_id", "success", "duration_ms", "error_type",
                   "input_size_bytes", "result_size_bytes", "mcp_server_scope", "decision_source",
                   "decision_type", "decision", "tool_source", "source", "prompt_id"})

EVENT_ALLOWLIST: dict[str, frozenset[str]] = {
    "usage.request": _model_keys(UsageRecord),
    "usage.error": frozenset({"model", "status_code", "attempt", "duration_ms", "error_class",
                              "request_id", "prompt_id", "query_source"}),
    "usage.refusal": frozenset({"model", "attempt", "category", "request_id", "prompt_id"}),
    "usage.metric_delta": frozenset({"metric", "type", "model", "delta", "query_source"}),
    "quota.snapshot": _model_keys(QuotaSnapshot),
    "quota.reset_observed": frozenset({"window_kind", "previous_resets_at", "new_resets_at"}),
    "session.started": _SESSION, "session.ended": _SESSION, "session.compacted": _SESSION,
    "session.active_time": _SESSION,
    "prompt.submitted": frozenset({"prompt_id", "prompt_length", "command_name", "command_source",
                                   "message_uuid"}),
    "prompt.responded": frozenset({"prompt_id", "response_length", "model", "request_id",
                                   "message_uuid", "query_source"}),
    "tool.call": _TOOL, "tool.decision": _TOOL,
    "permission.mode_changed": frozenset({"from_mode", "to_mode", "trigger", "prompt_id"}),
    "mcp.connection": frozenset({"server_name", "status", "transport_type", "duration_ms",
                                 "error_code", "server_scope", "is_plugin"}),
    "code.lines": frozenset({"added", "removed", "model"}),
    "code.commit": frozenset({"count"}), "code.pr": frozenset({"count"}),
    "statusline.tick": frozenset({"context_window", "prompt_cache", "cost_total_usd", "model",
                                  "effort", "fast_mode", "rate_limits", "version"}),
    "provider.health": _HEALTH, "collector.health": _HEALTH,
    "provider.schema_change": frozenset({"field_added", "field_removed", "sample_hash",
                                         "unclassified_windows", "kind"}),
    "estimate.published": frozenset({"estimator", "target", "value", "band", "confidence",
                                     "estimate_id", "inputs_hash"}),
    "alert.raised": frozenset({"alert_id", "rule_id", "severity", "basis", "evidence", "subject",
                               "dedupe_key", "message"}),
    "alert.resolved": frozenset({"alert_id", "rule_id", "resolved_at"}),
    "recommendation.issued": frozenset({"rec_id", "kind", "plan_hash", "expected", "why"}),
    "recommendation.applied": frozenset({"rec_id", "plan_hash"}),
    "recommendation.reverted": frozenset({"rec_id", "plan_hash"}),
    "recommendation.evaluated": frozenset({"rec_id", "realized", "verdict"}),
}
assert set(EVENT_ALLOWLIST) == set(EVENT_TYPES), "allow-list ile olay katalogu ayni kume olmali"


def find_forbidden_key(obj: Any, depth: int = 0) -> bool:
    """Herhangi bir seviyede yasak anahtar var mi (ad DONDURULMEZ)."""
    if depth > 32:
        return True
    if isinstance(obj, Mapping):
        for k, v in obj.items():
            ks = str(k).lower()
            if ks in FORBIDDEN_KEYS or ks.endswith(FORBIDDEN_SUFFIXES):
                return True
            if find_forbidden_key(v, depth + 1):
                return True
    elif isinstance(obj, (list, tuple, set)):
        return any(find_forbidden_key(v, depth + 1) for v in obj)
    return False


@dataclass(frozen=True)
class Decision:
    accepted: bool
    reason: str  # "ok" | "dropped_unknown_type" | "rejected_forbidden_key" | "rejected_extra_key" | "rejected_too_large"

    @property
    def dropped(self) -> bool:
        return self.reason == "dropped_unknown_type"


class IngestGate:
    def __init__(self, allowlist: Mapping[str, frozenset[str]] | None = None,
                 max_bytes: int = MAX_ENVELOPE_BYTES) -> None:
        self._allow = dict(EVENT_ALLOWLIST if allowlist is None else allowlist)
        self._max = max_bytes
        self.counters: Counter[str] = Counter()

    def check(self, env: Envelope) -> Decision:
        if env.type not in self._allow:
            return self._count("dropped_unknown_type", accepted=False)
        if find_forbidden_key(env.payload):
            return self._count("rejected_forbidden_key", accepted=False)
        extra = set(env.payload) - self._allow[env.type]
        if extra:
            return self._count("rejected_extra_key", accepted=False)
        size = len(canonical_json(env.model_dump(mode="json")).encode("utf-8"))
        if size > self._max:
            return self._count("rejected_too_large", accepted=False)
        return self._count("ok", accepted=True)

    def filter(self, envelopes: Iterable[Envelope]) -> list[Envelope]:
        return [e for e in envelopes if self.check(e).accepted]

    def _count(self, reason: str, *, accepted: bool) -> Decision:
        self.counters[reason] += 1
        return Decision(accepted=accepted, reason=reason)
