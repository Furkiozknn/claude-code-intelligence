from decimal import Decimal

import pytest
from pydantic import ValidationError

from cci.model import Band, EstimatorRef, EvidenceClass, Figure, sum_figures, usd_to_nano

EST = EstimatorRef(id="pace", version="1.0")


def test_observed_money_renders_two_decimals():
    f = Figure.observed(usd_to_nano("1.5"), "nanoUSD")
    assert f.render() == "$1.50"
    assert f.evidence_class is EvidenceClass.OBSERVED and f.released_as == "reconciled"


def test_withheld_never_renders_a_number():
    f = Figure.withheld("nanoUSD", EvidenceClass.ESTIMATED, "mutabakat yok", value=123)
    out = f.render()
    assert "withheld" in out and "mutabakat yok" in out and "$" not in out and "123" not in out


def test_released_requires_released_as_and_value():
    with pytest.raises(ValidationError):
        Figure(value=1, unit="tokens", evidence_class=EvidenceClass.OBSERVED, released=True)
    with pytest.raises(ValidationError):
        Figure(value=None, unit="tokens", evidence_class=EvidenceClass.OBSERVED,
               released=True, released_as="reconciled")


def test_withheld_requires_reason():
    with pytest.raises(ValidationError):
        Figure(value=None, unit="tokens", evidence_class=EvidenceClass.DERIVED, released=False)


def test_value_must_be_inside_band():
    with pytest.raises(ValidationError):
        Figure.estimated(50, "percent", EST, band=Band(lo=60, hi=70))


def test_sum_inherits_withheld_from_first_withheld_part():
    parts = [Figure.observed(10, "tokens"),
             Figure.withheld("tokens", EvidenceClass.ESTIMATED, "fiyat yok"),
             Figure.withheld("tokens", EvidenceClass.ESTIMATED, "ikinci sebep")]
    total = sum_figures(parts)
    assert total.released is False and total.withheld_because == "fiyat yok"
    assert total.evidence_class is EvidenceClass.ESTIMATED
    assert "10" not in total.render()


def test_sum_draft_wins_and_projected_propagates():
    a = Figure.observed(5, "tokens")
    b = Figure.estimated(7, "tokens", EST, released_as="draft", projected=True)
    total = sum_figures([a, b])
    assert total.value == Decimal(12)
    assert total.released_as == "draft" and total.projected is True
    assert total.evidence_class is EvidenceClass.ESTIMATED
    assert total.render().endswith("(proj)")


def test_sum_weakest_evidence_wins():
    total = sum_figures([Figure.observed(1, "tokens"),
                         Figure.derived(1, "tokens"),
                         Figure.estimated(1, "tokens", EST, evidence_class=EvidenceClass.INFERRED)])
    assert total.evidence_class is EvidenceClass.INFERRED


def test_sum_mixed_units_raises():
    with pytest.raises(ValueError):
        sum_figures([Figure.observed(1, "tokens"), Figure.observed(1, "percent")])


def test_sum_empty_is_withheld():
    total = sum_figures([], unit="tokens")
    assert total.released is False and total.withheld_because == "no parts"


def test_sum_bands_add_and_confidence_is_min():
    a = Figure.estimated(10, "percent", EST, band=Band(lo=8, hi=12), confidence=0.9)
    b = Figure.estimated(20, "percent", EST, band=Band(lo=15, hi=25), confidence=0.4)
    total = sum_figures([a, b])
    assert total.band == Band(lo=23, hi=37)
    assert total.confidence == 0.4
    assert total.estimator == EST


def test_sum_mixed_estimators_drop_estimator():
    a = Figure.estimated(1, "tokens", EST)
    b = Figure.estimated(1, "tokens", EstimatorRef(id="blend", version="2.0"))
    assert sum_figures([a, b]).estimator is None


def test_figures_are_frozen():
    f = Figure.observed(1, "tokens")
    with pytest.raises(ValidationError):
        f.value = Decimal(2)  # type: ignore[misc]
