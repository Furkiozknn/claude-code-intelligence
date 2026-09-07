"""Konfigurasyon: `<data_dir>/config.toml` (stdlib tomllib), varsayilanlarla birlestirilir."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AlertConfig:
    quota_warning_pct: float = 70.0
    quota_critical_pct: float = 90.0
    cost_attention_usd: float = 1.0
    ratio_warning: float = 2.0
    ratio_critical: float = 4.0
    cooldown_s: int = 1800
    storm_limit_per_minute: int = 3
    quiet_hours: tuple[int, int] | None = None     # (baslangic saat, bitis saat) yerel; None = kapali
    webhook_url: str | None = None                  # yalniz loopback kabul edilir
    notify_min_severity: str = "warning"


@dataclass(frozen=True)
class Config:
    alerts: AlertConfig = field(default_factory=AlertConfig)
    retention_days: int = 30
    otlp_port: int = 4318
    api_port: int = 4319
    raw: dict[str, Any] = field(default_factory=dict)


def load_config(path: Path) -> Config:
    try:
        doc = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        doc = {}
    a = doc.get("alerts", {}) if isinstance(doc.get("alerts"), dict) else {}
    qh = a.get("quiet_hours")
    quiet = (int(qh[0]), int(qh[1])) if isinstance(qh, list) and len(qh) == 2 else None
    webhook = a.get("webhook_url")
    if isinstance(webhook, str) and not (webhook.startswith("http://127.0.0.1") or webhook.startswith("http://localhost")):
        webhook = None  # dis host'a bildirim yok (ag envanteri)
    alerts = AlertConfig(
        quota_warning_pct=float(a.get("quota_warning_pct", 70.0)), quota_critical_pct=float(a.get("quota_critical_pct", 90.0)),
        cost_attention_usd=float(a.get("cost_attention_usd", 1.0)), ratio_warning=float(a.get("ratio_warning", 2.0)),
        ratio_critical=float(a.get("ratio_critical", 4.0)), cooldown_s=int(a.get("cooldown_s", 1800)),
        storm_limit_per_minute=int(a.get("storm_limit_per_minute", 3)), quiet_hours=quiet, webhook_url=webhook,
        notify_min_severity=str(a.get("notify_min_severity", "warning")),
    )
    return Config(alerts=alerts, retention_days=int(doc.get("retention_days", 30)), otlp_port=int(doc.get("otlp_port", 4318)),
                  api_port=int(doc.get("api_port", 4319)), raw=doc)
