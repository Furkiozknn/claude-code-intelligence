"""OTLP/JSON `ExportMetricsServiceRequest` -> Envelope demeti.

Claude Code metrikleri kumulatif sayaclardir (`claude_code.token.usage`,
`cost.usage`, `lines_of_code.count`, `commit.count`, `pull_request.count`,
`session.count`, `active_time.total`). Bu modul (metrik, oznitelik kumesi)
basina son degeri tutar ve DELTA uretir; deger duserse (yeniden baslatma)
delta = yeni deger. Metrik deltalari BIRINCIL kaynak degildir (capraz
dogrulama); birincil kaynak `api_request` log olayidir.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from typing import Any, Mapping

from cci.events.envelope import Envelope, SourceRef
from cci.model.evidence import EvidenceClass

from .otlp_map import COLLECTOR_NAME, COLLECTOR_VERSION, OTLP_SOURCE, PROVIDER, SCHEMA_VERSION, attributes

CUMULATIVE = 2  # AGGREGATION_TEMPORALITY_CUMULATIVE
DELTA = 1


def _value(dp: Mapping[str, Any]) -> float | None:
    if "asInt" in dp:
        try:
            return float(int(dp["asInt"]))
        except (TypeError, ValueError):
            return None
    if "asDouble" in dp:
        try:
            return float(dp["asDouble"])
        except (TypeError, ValueError):
            return None
    return None


def _ts(dp: Mapping[str, Any]) -> datetime:
    raw = dp.get("timeUnixNano") or 0
    ns = int(raw) if raw else 0
    return datetime.fromtimestamp(ns / 1e9, UTC) if ns else datetime.now(UTC)


class OtlpMetricMapper:
    def __init__(self) -> None:
        self._last: dict[tuple, float] = {}
        self.counters: Counter[str] = Counter()

    def map_request(self, doc: Mapping[str, Any]) -> list[Envelope]:
        out: list[Envelope] = []
        for rm in doc.get("resourceMetrics", []) or []:
            if not isinstance(rm, Mapping):
                continue
            resource = attributes((rm.get("resource") or {}).get("attributes"))
            for sm in rm.get("scopeMetrics", []) or []:
                if not isinstance(sm, Mapping):
                    continue
                for metric in sm.get("metrics", []) or []:
                    if isinstance(metric, Mapping):
                        out.extend(self._metric(metric, resource))
        return out

    def _metric(self, metric: Mapping[str, Any], resource: Mapping[str, Any]) -> list[Envelope]:
        name = str(metric.get("name") or "").removeprefix("claude_code.")
        body = metric.get("sum") or metric.get("gauge")
        if not name or not isinstance(body, Mapping):
            self.counters["dropped_unsupported_metric"] += 1
            return []
        temporality = int(body.get("aggregationTemporality") or CUMULATIVE) if "sum" in metric else DELTA
        out: list[Envelope] = []
        for dp in body.get("dataPoints", []) or []:
            if not isinstance(dp, Mapping):
                continue
            value = _value(dp)
            if value is None:
                self.counters["dropped_bad_datapoint"] += 1
                continue
            attrs = attributes(dp.get("attributes"))
            merged = {**resource, **attrs}
            key = (name, tuple(sorted((k, str(v)) for k, v in attrs.items())), str(merged.get("session.id")))
            if temporality == CUMULATIVE:
                last = self._last.get(key)
                delta = value if last is None or value < last else value - last
                self._last[key] = value
            else:
                delta = value
            if delta <= 0 and name != "session.count":
                self.counters["skipped_zero_delta"] += 1
                continue
            env = self._envelope(name, delta, merged, _ts(dp))
            if env is not None:
                out.append(env)
        return out

    def _envelope(self, name: str, delta: float, a: Mapping[str, Any], ts: datetime) -> Envelope | None:
        model = a.get("model") if isinstance(a.get("model"), str) else None
        qs = a.get("query_source") if isinstance(a.get("query_source"), str) else None
        if name == "token.usage":
            etype, payload = "usage.metric_delta", {"metric": "token.usage", "type": str(a.get("type") or "unknown"),
                                                    "model": model, "delta": delta, "query_source": qs}
        elif name == "cost.usage":
            etype, payload = "usage.metric_delta", {"metric": "cost.usage", "type": "usd", "model": model,
                                                    "delta": delta, "query_source": qs}
        elif name == "lines_of_code.count":
            t = str(a.get("type") or "")
            etype, payload = "code.lines", {"added": delta if t == "added" else 0,
                                            "removed": delta if t == "removed" else 0, "model": model}
        elif name == "commit.count":
            etype, payload = "code.commit", {"count": delta}
        elif name == "pull_request.count":
            etype, payload = "code.pr", {"count": delta}
        elif name == "session.count":
            etype, payload = "session.started", {"start_type": str(a.get("start_type") or "unknown"),
                                                 "version": a.get("app.version") if isinstance(a.get("app.version"), str) else None,
                                                 "entrypoint": a.get("app.entrypoint") if isinstance(a.get("app.entrypoint"), str) else None}
        elif name == "active_time.total":
            etype, payload = "session.active_time", {"seconds": delta, "kind": str(a.get("type") or "unknown")}
        else:
            self.counters["dropped_unknown_metric"] += 1
            return None
        payload = {k: v for k, v in payload.items() if v is not None}
        self.counters["mapped"] += 1
        account = a.get("user.account_uuid")
        return Envelope(type=etype, ts=ts,
                        source=SourceRef(collector=COLLECTOR_NAME, instance_id=OTLP_SOURCE.instance_id,
                                         collector_version=COLLECTOR_VERSION, schema_version=SCHEMA_VERSION),
                        provider=PROVIDER, account_key=str(account) if account else None,
                        session_id=str(a.get("session.id")) if a.get("session.id") else None,
                        privacy_class="internal", evidence_class=EvidenceClass.DERIVED, payload=payload)
