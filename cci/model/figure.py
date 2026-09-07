"""Figure: para ve tahmin degerleri icin rakam disiplini (docs/DATA_MODEL.md §1.2).

Kaynak kalip: cacheeconomics `money.Figure` - mutabakat kapisini gecmeyen rakam
basilmaz; toplam en zayif parcayi miras alir.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal, Sequence

from pydantic import model_validator

from .base import CciModel, F
from .evidence import EvidenceClass

Unit = Literal["nanoUSD", "tokens", "percent", "seconds"]
ReleasedAs = Literal["draft", "reconciled", ""]
NANO = Decimal(1_000_000_000)


class EstimatorRef(CciModel):
    id: str = F("internal", min_length=1)
    version: str = F("internal", min_length=1)


class Band(CciModel):
    lo: Decimal = F("internal")
    hi: Decimal = F("internal")

    @model_validator(mode="after")
    def _ordered(self) -> "Band":
        if self.lo > self.hi:
            raise ValueError("band.lo > band.hi")
        return self


class Figure(CciModel):
    value: Decimal | None = F("internal", default=None)
    unit: Unit = F("public")
    evidence_class: EvidenceClass = F("public")
    released: bool = F("public", default=True)
    withheld_because: str = F("public", default="")
    released_as: ReleasedAs = F("public", default="")
    projected: bool = F("public", default=False)
    estimator: EstimatorRef | None = F("internal", default=None)
    band: Band | None = F("internal", default=None)
    confidence: float | None = F("internal", default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _consistency(self) -> "Figure":
        if self.released:
            if self.released_as == "":
                raise ValueError("released=True icin released_as ('draft'|'reconciled') gerekli")
            if self.value is None:
                raise ValueError("released=True icin value gerekli")
            if self.withheld_because:
                raise ValueError("released=True iken withheld_because bos olmali")
        else:
            if not self.withheld_because.strip():
                raise ValueError("released=False icin withheld_because zorunlu")
            if self.released_as != "":
                raise ValueError("released=False iken released_as bos olmali")
        if self.band is not None and self.value is not None:
            if not (self.band.lo <= self.value <= self.band.hi):
                raise ValueError("value bant disinda")
        return self

    # --- kurucular -------------------------------------------------------
    @classmethod
    def observed(cls, value: Decimal | int | str, unit: Unit) -> "Figure":
        return cls(value=Decimal(value), unit=unit, evidence_class=EvidenceClass.OBSERVED,
                   released=True, released_as="reconciled")

    @classmethod
    def derived(cls, value: Decimal | int | str, unit: Unit) -> "Figure":
        return cls(value=Decimal(value), unit=unit, evidence_class=EvidenceClass.DERIVED,
                   released=True, released_as="reconciled")

    @classmethod
    def estimated(
        cls,
        value: Decimal | int | str,
        unit: Unit,
        estimator: EstimatorRef,
        *,
        evidence_class: EvidenceClass = EvidenceClass.ESTIMATED,
        released_as: ReleasedAs = "reconciled",
        band: Band | None = None,
        confidence: float | None = None,
        projected: bool = False,
    ) -> "Figure":
        return cls(value=Decimal(value), unit=unit, evidence_class=evidence_class,
                   released=True, released_as=released_as, estimator=estimator,
                   band=band, confidence=confidence, projected=projected)

    @classmethod
    def withheld(
        cls,
        unit: Unit,
        evidence_class: EvidenceClass,
        because: str,
        *,
        value: Decimal | int | str | None = None,
        projected: bool = False,
    ) -> "Figure":
        return cls(value=None if value is None else Decimal(value), unit=unit,
                   evidence_class=evidence_class, released=False,
                   withheld_because=because, projected=projected)

    # --- gosterim --------------------------------------------------------
    def render(self) -> str:
        """Yalniz released ise sayi doner; aksi halde sebep. Sayi istemenin
        baska yolu yok (yuzeyler bu metodu kullanir)."""
        if not self.released:
            return f"[withheld: {self.withheld_because}]"
        assert self.value is not None
        v = self.value
        if self.unit == "nanoUSD":
            text = f"${(v / NANO).quantize(Decimal('0.01'))}"
        elif self.unit == "tokens":
            text = f"{int(v):,}"
        elif self.unit == "percent":
            text = f"{v.quantize(Decimal('0.1'))}%"
        else:
            text = f"{v.normalize()}s"
        if self.projected:
            text += " (proj)"
        return text


def usd_to_nano(usd: Decimal | float | int | str) -> Decimal:
    return (Decimal(str(usd)) * NANO).quantize(Decimal(1))


def sum_figures(parts: Sequence[Figure], *, unit: Unit | None = None) -> Figure:
    """Toplam, parcalarinin en zayifini miras alir:
    - bir parca withheld -> toplam withheld (sebep: ilk withheld parca)
    - bir parca draft -> toplam draft
    - herhangi biri projected -> toplam projected
    - kanit sinifi = en zayif parca
    - bant/guven yalniz tum parcalarda varsa toplanir / min alinir
    """
    parts = list(parts)
    if not parts:
        if unit is None:
            raise ValueError("bos toplam icin unit gerekli")
        return Figure.withheld(unit, EvidenceClass.DERIVED, "no parts")
    units = {p.unit for p in parts}
    if len(units) != 1:
        raise ValueError(f"birimler karisik: {sorted(units)}")
    the_unit = units.pop()
    if unit is not None and unit != the_unit:
        raise ValueError(f"beklenen birim {unit}, parcalar {the_unit}")

    evidence = EvidenceClass.weakest(p.evidence_class for p in parts)
    projected = any(p.projected for p in parts)
    unreleased = [p for p in parts if not p.released]
    if unreleased:
        return Figure.withheld(the_unit, evidence, unreleased[0].withheld_because,
                               projected=projected)

    total = sum((p.value for p in parts), Decimal(0))
    released_as: ReleasedAs = "draft" if any(p.released_as == "draft" for p in parts) else "reconciled"

    bands = [p.band for p in parts]
    band = None
    if all(b is not None for b in bands):
        band = Band(lo=sum((b.lo for b in bands), Decimal(0)),
                    hi=sum((b.hi for b in bands), Decimal(0)))
    confs = [p.confidence for p in parts]
    confidence = min(confs) if all(c is not None for c in confs) else None
    ests = {(p.estimator.id, p.estimator.version) for p in parts if p.estimator is not None}
    estimator = parts[0].estimator if (len(ests) == 1 and all(p.estimator for p in parts)) else None

    return Figure(value=total, unit=the_unit, evidence_class=evidence, released=True,
                  released_as=released_as, projected=projected, estimator=estimator,
                  band=band, confidence=confidence)
