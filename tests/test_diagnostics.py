from datetime import UTC, datetime, timedelta

from cci.analytics.diagnostics import (attention_for, diagnose_session, health_score, worst_attention)
from cci.events import Envelope, SourceRef
from cci.model import EvidenceClass, Figure

NOW = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
SRC = SourceRef(collector="otlp", instance_id="otlp:claude-code", collector_version="0.0.1", schema_version=1)


def ev(i, type_, payload, session="s1"):
    return Envelope(type=type_, ts=NOW + timedelta(seconds=i), source=SRC, provider="anthropic", session_id=session,
                    payload=payload)


def tool(i, name="Read", success=True, duration=100, size=10, error=None, session="s1", result_size=None):
    p = {"tool_name": name, "tool_use_id": f"t{i}", "success": success, "duration_ms": duration, "input_size_bytes": size}
    if error:
        p["error_type"] = error
    if result_size is not None:
        p["result_size_bytes"] = result_size
    return ev(i, "tool.call", p, session=session)


def test_healthy_session_is_ok():
    # farkli dosyalar: girdi/cikti boyutlari degisir -> dongu degil
    events = [ev(i, "usage.request", {"provider": "anthropic"}) for i in range(5)] + \
             [tool(10 + i, duration=50 + i, size=10 + i, result_size=100 * i) for i in range(6)]
    d = diagnose_session("s1", events)
    assert d.requests == 5 and d.tool_calls == 6 and d.loops == () and d.health == 100 and d.attention == "ok"
    assert d.tools[0].tool_name == "Read" and d.tools[0].p95_ms == 55 and d.tools[0].is_slow is False
    assert d.evidence_class is EvidenceClass.DERIVED and d.estimator.id == "diagnostics_v1"


def test_loop_fingerprint_and_failures_ladder():
    events = [tool(i, "Bash", success=False, duration=20, size=42, error="exit_code") for i in range(4)] + [tool(9, "Read")]
    d = diagnose_session("s1", events)
    assert len(d.loops) == 1 and d.loops[0].count == 4 and d.loops[0].severity == "high" and d.loops[0].tool_name == "Bash"
    assert d.tool_failures == 4 and d.attention == "failures" and any("dongu" in r for r in d.reasons)
    assert d.health < 100


def test_errors_and_compactions_lower_health_and_context_risk():
    events = ([ev(i, "usage.request", {}) for i in range(4)] + [ev(10, "usage.error", {"status_code": 529, "attempt": 2})] * 2
              + [ev(20, "session.compacted", {"trigger": "auto"})] * 2
              + [ev(30, "statusline.tick", {"context_window": {"used_percentage": 90}})])
    d = diagnose_session("s1", events)
    assert d.errors == 2 and d.retry_events == 2 and d.compactions == 2 and d.context.risk == "critical"
    assert d.health == round(100 - (2 / 6) * 30 - 15 - 10) and d.attention in ("critical", "context")
    assert d.health == health_score(error_rate=2 / 6, loops=0, timeout_rate=0, context_risk="critical", compactions=2)


def test_cost_and_latency_attention():
    expensive = Figure.observed(2_500_000_000, "nanoUSD")
    att, reasons = attention_for(health=95, tool_failures=0, context_risk=None, loops=0, cost=expensive, max_p95_ms=None)
    assert att == "cost" and reasons == ("maliyet $2.50 >= $1",)
    att, _ = attention_for(health=95, tool_failures=0, context_risk=None, loops=0, cost=None, max_p95_ms=61_000)
    assert att == "latency"
    withheld = Figure.withheld("nanoUSD", EvidenceClass.ESTIMATED, "yok")
    assert attention_for(health=95, tool_failures=0, context_risk=None, loops=0, cost=withheld, max_p95_ms=None)[0] == "ok"
    assert attention_for(health=70, tool_failures=0, context_risk=None, loops=0, cost=None, max_p95_ms=None)[0] == "warning"
    assert attention_for(health=40, tool_failures=3, context_risk="warn", loops=2, cost=None, max_p95_ms=None)[0] == "critical"


def test_same_tool_same_sizes_repeated_is_a_loop_even_when_successful():
    d = diagnose_session("s1", [tool(i, "Read", size=10, result_size=500) for i in range(3)])
    assert len(d.loops) == 1 and d.loops[0].severity == "medium" and d.attention == "loops"


def test_timeouts_and_slow_tools():
    events = [tool(i, "WebFetch", duration=35_000, size=i, error="timeout" if i % 2 else None) for i in range(4)]
    d = diagnose_session("s1", events)
    t = d.tools[0]
    assert t.timeouts == 2 and t.is_slow and d.tool_timeouts == 2 and d.health < 100


def test_events_from_other_sessions_are_ignored_and_worst_attention():
    events = [tool(1, "Read", session="s2", success=False)] + [ev(2, "usage.request", {})]
    d = diagnose_session("s1", events)
    assert d.tool_calls == 0 and d.attention == "ok"
    assert worst_attention(["ok", "warning", "loops", "ok"]) == "loops" and worst_attention([]) == "ok"
