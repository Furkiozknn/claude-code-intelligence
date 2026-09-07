"""Estimate ve QuotaForecast (docs/DATA_MODEL.md §6, ANALYTICS.md §2)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import field_validator, model_validator

from .base import CciModel, F
from .evidence import EvidenceClass
from .figure import Band, EstimatorRef, Figure
from .quota import WindowKind
from .usage import validate_ts

Verdict = Literal["at_risk", "watch", "learning", "surplus", "enough"]
Confidence = Literal["learning", "medium", "high"]
LEARNING_MIN_CYCLES = 5  # R-7: 5 tamamlanmis dongu altinda hukum yok

_ESTIMATE_CLASSES = {EvidenceClass.ESTIMATED, EvidenceClass.PREDICTED, EvidenceClass.INFERRED}


class Estimate(CciModel):
    estimate_id: str = F("internal", min_length=1)
    estimator: EstimatorRef = F("internal")
    target: str = F("internal", min_length=1)
    produced_at: datetime = F("internal")
    inputs_hash: str = F("internal", min_length=16)
    value: Figure = F("internal")
    diagnostics: dict[str, float | int | str | None] = F("internal", default_factory=dict)
    realized: Figure | None = F("internal", default=None)

    _validate_produced = field_validator("produced_at")(validate_ts)

    @model_validator(mode="after")
    def _classes(self) -> "Estimate":
        if self.value.evidence_class not in _ESTIMATE_CLASSES:
            raise ValueError("Estimate.value kanit sinifi estimated|predicted|inferred olmali")
        if self.value.released and self.value.estimator != self.estimator:
            raise ValueError("Estimate.value.estimator ile Estimate.estimator ayni olmali")
        if self.realized is not None and self.realized.evidence_class not in (
            EvidenceClass.OBSERVED, EvidenceClass.DERIVED
        ):
            raise ValueError("realized yalniz observed|derived olabilir")
        return self


class ProjectedAtReset(CciModel):
    median: Decimal = F("internal", ge=0)
    band: Band = F("internal")

    @model_validator(mode="after")
    def _inside(self) -> "ProjectedAtReset":
        if not (self.band.lo <= self.median <= self.band.hi):
            raise ValueError("median bant disinda")
        return self


class QuotaForecast(Estimate):
    window_kind: WindowKind = F("public")
    current_utilization: float = F("internal", ge=0.0, le=1.0)
    projected_at_reset: ProjectedAtReset | None = F("internal", default=None)
    verdict: Verdict = F("public")
    confidence: Confidence = F("public")
    confidence_score: float = F("internal", ge=0.0, le=1.0)
    run_out_at: datetime | None = F("internal", default=None)
    target_remaining_pct: float = F("internal", ge=0.0, le=100.0)
    cycles_completed: int = F("public", ge=0)

    @field_validator("run_out_at")
    @classmethod
    def _run_out(cls, v: datetime | None) -> datetime | None:
        return None if v is None else validate_ts(v)

    @model_validator(mode="after")
    def _learning_gate(self) -> "QuotaForecast":
        learning = self.cycles_completed < LEARNING_MIN_CYCLES or self.confidence == "learning"
        if learning:
            if self.verdict != "learning":
                raise ValueError("R-7: yeterli dongu yokken hukum 'learning' olmali")
            if self.projected_at_reset is not None:
                raise ValueError("R-7: ogrenme asamasinda nokta projeksiyon yayinlanmaz")
            if self.value.released:
                raise ValueError("R-7: ogrenme asamasinda deger withheld olmali")
        elif self.verdict == "learning":
            raise ValueError("yeterli dongu ve guven varken hukum 'learning' olamaz")
        return self
