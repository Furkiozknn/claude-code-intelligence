"""Kimlikler: hesap, kaynak ornegi, oturum (docs/DATA_MODEL.md §1.4)."""

from __future__ import annotations

from datetime import date
from typing import Literal

from .base import CciModel, F

SourceKind = Literal["cli", "desktop", "ide", "remote", "network"]


class AccountRef(CciModel):
    """Hesap referansi. `account_key` YALNIZ OTel `user.account_uuid`'dir (R-9);
    gizli degerden turetilmis kimlik kullanilmaz. Kimlik yoksa AccountRef
    uretilmez ve hesap seviyesi veri saklanmaz (claude-pace kurali)."""

    provider: str = F("internal", min_length=1)
    account_key: str = F("sensitive", min_length=1)


class SourceInstance(CciModel):
    """Ayni saglayicinin farkli koku (CLAUDE_CONFIG_DIR, Desktop, uzak makine)."""

    provider: str = F("internal", min_length=1)
    instance_id: str = F("internal", min_length=1)
    label: str = F("internal", min_length=1)
    kind: SourceKind = F("internal")
    root_path: str | None = F("sensitive", default=None)
    network: bool = F("public", default=False)
    schema_verified: bool = F("public", default=False)
    verified_at: date | None = F("public", default=None)


class SessionRef(CciModel):
    session_id: str = F("internal", min_length=1)
    parent_session_id: str | None = F("internal", default=None)
    agent_id: str | None = F("internal", default=None)
    is_sidechain: bool = F("internal", default=False)
