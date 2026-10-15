"""Spending budgets: today's and this month's estimated cost against a limit.

ccusage reports what was spent; Claude Code itself enforces plan quotas, not
money. A user on API billing, or one who simply wants to know when a month
gets expensive, needs a number to compare against. ``[budget]`` in
``config.toml`` sets it::

    [budget]
    daily_usd = 5
    monthly_usd = 100
    warn_pct = 80        # warning from 80 % of a limit (default)

Everything here follows the project's evidence rules:

- **spent** is the sum of the period's daily summary costs, which are
  *derived* from list prices (shown with ``≈``). If any day's cost is
  withheld (an unpriced model), the period total is withheld too, and the
  status is ``unknown`` rather than a number that looks safe.
- **projected** (month only) is a straight-line projection of the month to
  date over the days left, evidence class *predicted*, marked ``(proj)``.
  It only says "at this pace"; it is never presented as observed.

The calendar is the local one (``CCI_TZ`` / ``TZ``), the same days
``cci daily`` prints.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Iterable, Literal, Optional

from cci.analytics.summaries import DailySummary
from cci.model.evidence import EvidenceClass
from cci.model.figure import EstimatorRef, Figure, NANO, sum_figures, usd_to_nano

Period = Literal["day", "month"]
State = Literal["ok", "warning", "exceeded", "projected_over", "unknown"]

PROJECTION_ESTIMATOR = EstimatorRef(id="budget.month_linear", version="1")


@dataclass(frozen=True)
class BudgetStatus:
    period: Period
    start: date
    limit_nano: Decimal
    spent: Figure
    #: Spent / limit in percent; None when ``spent`` is withheld.
    pct: Optional[float]
    #: Month only: month-to-date spend extended linearly to the month's end.
    projected: Optional[Figure]
    state: State

    @property
    def limit_usd(self) -> Decimal:
        return self.limit_nano / NANO

    def as_dict(self) -> dict:
        return {
            "period": self.period,
            "start": self.start.isoformat(),
            "limit_usd": str(self.limit_usd),
            "spent": self.spent.model_dump(mode="json"),
            "pct": self.pct,
            "projected": None if self.projected is None else self.projected.model_dump(mode="json"),
            "state": self.state,
        }


def _spent(days: Iterable[DailySummary]) -> Figure:
    parts = [d.totals.cost for d in days]
    if not parts:
        return Figure.observed(0, "nanoUSD")  # nothing ran in the period: an observed zero
    return sum_figures(parts, unit="nanoUSD")


def _state(pct: Optional[float], warn_pct: float) -> State:
    if pct is None:
        return "unknown"
    if pct >= 100:
        return "exceeded"
    if pct >= warn_pct:
        return "warning"
    return "ok"


def budget_status(
    daily: Iterable[DailySummary],
    today: date,
    *,
    daily_usd: Optional[float],
    monthly_usd: Optional[float],
    warn_pct: float = 80.0,
) -> list[BudgetStatus]:
    """The configured budgets for ``today`` (local date). Pure: summaries in,
    statuses out; a budget that is not configured is not reported."""
    days = list(daily)
    out: list[BudgetStatus] = []
    if daily_usd:
        limit = usd_to_nano(daily_usd)
        spent = _spent(d for d in days if d.day == today)
        pct = float(spent.value / limit * 100) if spent.released else None
        out.append(BudgetStatus("day", today, limit, spent, pct, None, _state(pct, warn_pct)))
    if monthly_usd:
        limit = usd_to_nano(monthly_usd)
        start = today.replace(day=1)
        spent = _spent(d for d in days if start <= d.day <= today)
        pct = float(spent.value / limit * 100) if spent.released else None
        projected = None
        state = _state(pct, warn_pct)
        if spent.released:
            month_days = calendar.monthrange(today.year, today.month)[1]
            elapsed = today.day  # today counts as a (partial) day of spend
            value = (spent.value * month_days / elapsed).quantize(Decimal(1))
            projected = Figure.estimated(value, "nanoUSD", PROJECTION_ESTIMATOR,
                                         evidence_class=EvidenceClass.PREDICTED, projected=True)
            if state in ("ok", "warning") and value >= limit:
                state = "projected_over"
        out.append(BudgetStatus("month", start, limit, spent, pct, projected, state))
    return out
