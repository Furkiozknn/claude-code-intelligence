"""Alert ve Recommendation (docs/DATA_MODEL.md §7, PRODUCT.md §6, ANALYTICS.md §5)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import field_validator, model_validator

from .base import CciModel, F
from .figure import Figure
from .usage import validate_ts

AlertSeverity = Literal["info", "warning", "critical"]
Basis = Literal["certain", "probable"]  # Observed/Derived -> certain; Predicted -> probable
RecStatus = Literal["issued", "applied", "reverted", "evaluated", "dismissed"]
ActionType = Literal["none", "settings_change", "env_change", "archive", "session_hint", "wait"]


class Evidence(CciModel):
    metric: str = F("internal", min_length=1)
    value: Decimal = F("internal")
    baseline: Decimal | None = F("internal", default=None)
    ratio: Decimal | None = F("internal", default=None)
    evidence_class: str = F("public", min_length=1)


class Subject(CciModel):
    kind: Literal["session", "project", "quota_window", "provider", "collector", "model"] = F("public")
    id: str = F("internal", min_length=1)


class Alert(CciModel):
    alert_id: str = F("internal", min_length=1)
    rule_id: str = F("public", min_length=1)
    severity: AlertSeverity = F("public")
    basis: Basis = F("public")
    raised_at: datetime = F("internal")
    resolved_at: datetime | None = F("internal", default=None)
    subject: Subject = F("internal")
    evidence: tuple[Evidence, ...] = F("internal", default=())
    dedupe_key: str = F("internal", min_length=1)
    cooldown_until: datetime | None = F("internal", default=None)
    message: str = F("internal", min_length=1)  # ne oldu / kanit / ne yapilabilir - icerik degil

    _validate_raised = field_validator("raised_at")(validate_ts)

    @field_validator("resolved_at", "cooldown_until")
    @classmethod
    def _opt_ts(cls, v: datetime | None) -> datetime | None:
        return None if v is None else validate_ts(v)

    @model_validator(mode="after")
    def _order(self) -> "Alert":
        if self.resolved_at is not None and self.resolved_at < self.raised_at:
            raise ValueError("resolved_at < raised_at")
        return self


class Action(CciModel):
    type: ActionType = F("public")
    reversible: bool = F("public")
    plan_hash: str | None = F("internal", default=None)
    summary: str = F("internal", min_length=1)

    @model_validator(mode="after")
    def _reversible_needs_plan(self) -> "Action":
        if self.type in ("settings_change", "env_change", "archive"):
            if not self.reversible or not self.plan_hash:
                raise ValueError("dosya degistiren eylem geri alinabilir ve plan_hash'li olmali (act gunlugu)")
        return self


class Recommendation(CciModel):
    rec_id: str = F("internal", min_length=1)
    kind: str = F("public", min_length=1)
    title: str = F("internal", min_length=1)
    why: tuple[Evidence, ...] = F("internal", min_length=1)
    action: Action = F("internal")
    expected: Figure = F("internal")
    realized: Figure | None = F("internal", default=None)
    status: RecStatus = F("public", default="issued")
    issued_at: datetime = F("internal")

    _validate_issued = field_validator("issued_at")(validate_ts)

    @model_validator(mode="after")
    def _status(self) -> "Recommendation":
        if self.status == "evaluated" and self.realized is None:
            raise ValueError("evaluated durumunda realized zorunlu")
        return self
