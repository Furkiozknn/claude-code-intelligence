"""Nazik kota poller (docs/PROVIDERS.md §3-4; sentez P4).

- aralik >= 180 s; 429 -> retry_after (basliktan/govdeden, min 60, varsayilan 300)
- 401 -> kimlik dosyasini bir kez yeniden oku, tekrar dene; hala 401 -> degraded
- diger 4xx -> terminal; 5xx/ag -> transient, ustel geri cekilme <= 900 s
- suresi dolmus token -> yeniden oku; hala dolmus -> degraded, istek YOK
- ASLA token yenileme/rotasyon; kendi User-Agent
- health.detail redakte (sanitize_error)
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable, Mapping

from cci import __version__
from cci.adapters.base import Health
from cci.adapters.claude_code.quota_map import QuotaParseError, parse_usage_response
from cci.model.ids import AccountRef
from cci.model.quota import QuotaSnapshot

from .credentials import Credential, CredentialError, load_credential, sanitize_error

ENDPOINT = "https://api.anthropic.com/api/oauth/usage"
USER_AGENT = f"cci/{__version__} (+https://github.com/Furkiozknn)"
MIN_INTERVAL_S = 180
MAX_BACKOFF_S = 900
DEFAULT_RETRY_AFTER_S = 300
MIN_RETRY_AFTER_S = 60


@dataclass(frozen=True)
class FetchResult:
    status: int
    headers: Mapping[str, str]
    body: bytes


FetchFn = Callable[[str], FetchResult]


def http_fetch(token: str, *, timeout_s: float = 15.0) -> FetchResult:
    req = urllib.request.Request(ENDPOINT, method="GET", headers={
        "Authorization": f"Bearer {token}", "Accept": "application/json",
        "anthropic-beta": "oauth-2025-04-20", "User-Agent": USER_AGENT,
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:  # noqa: S310 (izinli host)
            return FetchResult(resp.status, {k.lower(): v for k, v in resp.headers.items()}, resp.read())
    except urllib.error.HTTPError as exc:
        return FetchResult(exc.code, {k.lower(): v for k, v in exc.headers.items()}, exc.read() or b"")


@dataclass(frozen=True)
class PollResult:
    snapshot: QuotaSnapshot | None
    health: Health
    next_in_s: int
    unknown_keys: tuple[str, ...] = ()


def _retry_after(res: FetchResult) -> int:
    val = res.headers.get("retry-after")
    parsed: float | None = None
    if val is not None:
        try:
            parsed = float(val)
        except ValueError:
            parsed = None
    if parsed is None:
        try:
            hint = json.loads(res.body.decode("utf-8") or "{}").get("retry_after")
            parsed = float(hint) if isinstance(hint, (int, float, str)) else None
        except (ValueError, AttributeError):
            parsed = None
    return max(MIN_RETRY_AFTER_S, int(parsed) if parsed is not None else DEFAULT_RETRY_AFTER_S)


class QuotaPoller:
    def __init__(self, credentials_path: Path, *, fetch: FetchFn = http_fetch,
                 interval_s: int = MIN_INTERVAL_S, account: AccountRef | None = None,
                 now: Callable[[], datetime] | None = None) -> None:
        self._path = credentials_path
        self._fetch = fetch
        self._interval = max(MIN_INTERVAL_S, int(interval_s))
        self._account = account
        self._now = now or (lambda: datetime.now(UTC))
        self._backoff = self._interval
        self.last_snapshot: QuotaSnapshot | None = None
        self.last_health: Health = Health(status="degraded", error_class="not_started")

    def set_account(self, account: AccountRef | None) -> None:
        self._account = account

    # --- yardimcilar ------------------------------------------------------
    def _credential(self) -> Credential | None:
        return load_credential(self._path)

    def _bump_backoff(self) -> int:
        self._backoff = min(MAX_BACKOFF_S, max(self._interval, self._backoff * 2))
        return self._backoff

    def _reset_backoff(self) -> None:
        self._backoff = self._interval

    def _result(self, snapshot: QuotaSnapshot | None, status: str, next_in: int, *,
                error_class: str | None = None, detail: str = "", retry_after: int | None = None,
                unknown: tuple[str, ...] = ()) -> PollResult:
        health = Health(status=status, error_class=error_class, detail=sanitize_error(detail),
                        retry_after_s=retry_after,
                        last_success_at=self.last_snapshot.fetched_at if self.last_snapshot else None)
        self.last_health = health
        return PollResult(snapshot=snapshot, health=health, next_in_s=next_in, unknown_keys=unknown)

    # --- tek tur ----------------------------------------------------------
    def poll_once(self) -> PollResult:
        now = self._now()
        now_ms = int(now.timestamp() * 1000)
        try:
            cred = self._credential()
        except (CredentialError, UnicodeDecodeError) as exc:
            return self._result(None, "down", self._interval, error_class="credentials_unsafe", detail=str(exc))
        if cred is None:
            return self._result(None, "down", self._interval, error_class="no_credentials",
                                detail="Claude Code kimlik dosyasi yok; 'claude' ile giris yap")
        if cred.is_expired(now_ms):
            cred2 = self._credential()
            if cred2 is None or cred2.is_expired(now_ms):
                return self._result(None, "degraded", self._interval, error_class="expired",
                                    detail="token suresi dolmus; Claude Code yenileyene kadar bekleniyor")
            cred = cred2

        try:
            res = self._fetch(cred.access_token)
            if res.status == 401:
                cred2 = self._credential()
                if cred2 is None or cred2.access_token == cred.access_token:
                    return self._result(None, "degraded", self._bump_backoff(), error_class="unauthorized",
                                        detail="401; kimlik dosyasi degismedi")
                res = self._fetch(cred2.access_token)
        except Exception as exc:  # ag hatasi: transient
            return self._result(None, "degraded", self._bump_backoff(), error_class="network", detail=str(exc))

        if res.status == 429:
            wait = _retry_after(res)
            return self._result(None, "degraded", wait, error_class="rate_limited",
                                detail="429; retry_after uygulaniyor", retry_after=wait)
        if 400 <= res.status < 500:
            return self._result(None, "down", MAX_BACKOFF_S, error_class=f"http_{res.status}",
                                detail="saglayici istegi reddetti")
        if res.status >= 500 or res.status != 200:
            return self._result(None, "degraded", self._bump_backoff(), error_class=f"http_{res.status}",
                                detail="gecici sunucu hatasi")

        try:
            body = json.loads(res.body.decode("utf-8"))
            snap, unknown = parse_usage_response(body, account=self._account, fetched_at=now, raw_bytes=res.body)
        except (ValueError, QuotaParseError) as exc:
            return self._result(None, "degraded", self._bump_backoff(), error_class="malformed_response",
                                detail=str(exc))
        self._reset_backoff()
        self.last_snapshot = snap
        detail = "ok" if snap.authoritative else "ok (authoritative=false: siniflanamayan/tekrarli pencere)"
        if unknown:
            detail += f"; bilinmeyen anahtar: {len(unknown)}"
        return self._result(snap, "ok", self._interval, detail=detail, unknown=tuple(unknown))

    def run_forever(self, sleep: Callable[[float], None] = time.sleep,
                    on_result: Callable[[PollResult], None] | None = None) -> None:
        while True:
            result = self.poll_once()
            if on_result is not None:
                on_result(result)
            sleep(result.next_in_s)
