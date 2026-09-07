"""Stage 13 - Research Mode (docs/RESEARCH_MODE.md): ayri dizin, ayri komut, cekirdek depoya yazmaz."""

from .proxy import ResearchProxy, headers_to_quota_snapshot, sanitize_headers
from .unit_estimator import CANDIDATES, estimate_unit, intervals_from

__all__ = ["ResearchProxy", "headers_to_quota_snapshot", "sanitize_headers", "CANDIDATES", "estimate_unit", "intervals_from"]
