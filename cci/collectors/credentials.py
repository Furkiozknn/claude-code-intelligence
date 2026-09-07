"""Kimlik dosyasi guvenli okuma (docs/PROVIDERS.md §3; kaynak: codeburn readSecureFile).

- symlink reddi, duzenli dosya, boyut <= 64 KB, POSIX mod bitleri (grup/diger yok)
- token YALNIZ bellekte; repr/log redakte; diske asla
- yenileme/rotasyon yok: bu modul yalniz okur
"""

from __future__ import annotations

import json
import os
import re
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

MAX_CREDENTIAL_BYTES = 64 * 1024

_REDACT_PATTERNS = [
    re.compile(r"Bearer\s+[^\s,;\"']+", re.I),
    re.compile(r"sk-ant-[A-Za-z0-9_\-]+", re.I),
    re.compile(r"sk-[A-Za-z0-9_\-]{8,}", re.I),
    re.compile(r"ya29\.[A-Za-z0-9._\-]+"),
    re.compile(r"gh[opusr]_[A-Za-z0-9_]+"),
    re.compile(r"eyJ[A-Za-z0-9._\-]{10,}"),
]


def sanitize_error(error: BaseException | str) -> str:
    text = str(error).replace("\0", "")
    for pat in _REDACT_PATTERNS:
        text = pat.sub("[REDACTED]", text)
    return text[:240]


class CredentialError(RuntimeError):
    pass


@dataclass(frozen=True)
class Credential:
    access_token: str = field(repr=False)
    expires_at_ms: int | None = None
    subscription_type: str | None = None
    rate_limit_tier: str | None = None

    def __repr__(self) -> str:  # token asla repr'e girmez
        return (f"Credential(access_token='[REDACTED]', expires_at_ms={self.expires_at_ms}, "
                f"subscription_type={self.subscription_type!r})")

    def is_expired(self, now_ms: int, grace_ms: int = 5 * 60_000) -> bool:
        return self.expires_at_ms is not None and self.expires_at_ms - now_ms <= grace_ms


def _assert_safe(st: os.stat_result, path: Path) -> None:
    if not stat.S_ISREG(st.st_mode):
        raise CredentialError(f"duzenli dosya degil: {path.name}")
    if st.st_size > MAX_CREDENTIAL_BYTES:
        raise CredentialError(f"kimlik dosyasi cok buyuk: {path.name}")
    if os.name != "nt" and (st.st_mode & 0o077):
        raise CredentialError(f"kimlik dosyasi izinleri genis: {path.name}")


def read_secure_file(path: Path, max_bytes: int = MAX_CREDENTIAL_BYTES) -> str | None:
    """Yoksa None; guvensizse CredentialError. Icerik yalniz donus degerinde."""
    try:
        before = os.lstat(path)
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(before.st_mode):
        raise CredentialError(f"symlink reddedildi: {path.name}")
    _assert_safe(before, path)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    fd = os.open(path, flags)
    try:
        after = os.fstat(fd)
        _assert_safe(after, path)
        if after.st_size > max_bytes:
            raise CredentialError("kimlik dosyasi cok buyuk")
        data = os.read(fd, max_bytes + 1)
    finally:
        os.close(fd)
    if len(data) > max_bytes:
        raise CredentialError("kimlik dosyasi cok buyuk")
    return data.decode("utf-8", errors="strict")


def parse_credential(raw: str) -> Credential | None:
    clean = raw.replace("\r", "")
    try:
        doc: Any = json.loads(clean)
    except ValueError as exc:
        raise CredentialError("kimlik dosyasi JSON degil") from exc
    oauth = doc.get("claudeAiOauth") if isinstance(doc, dict) else None
    if not isinstance(oauth, dict):
        return None
    token = oauth.get("accessToken")
    if not isinstance(token, str) or not token:
        return None
    exp = oauth.get("expiresAt")
    return Credential(
        access_token=token,
        expires_at_ms=int(exp) if isinstance(exp, (int, float)) else None,
        subscription_type=oauth.get("subscriptionType") if isinstance(oauth.get("subscriptionType"), str) else None,
        rate_limit_tier=oauth.get("rateLimitTier") if isinstance(oauth.get("rateLimitTier"), str) else None,
    )


def load_credential(path: Path) -> Credential | None:
    raw = read_secure_file(path)
    return None if raw is None else parse_credential(raw)
