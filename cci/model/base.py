"""Ortak taban model ve alan yardimcisi.

Kurallar (docs/DATA_MODEL.md, docs/PRIVACY.md):
- extra="forbid": sema disi anahtar kabul edilmez (allow-list ilkesi).
- frozen=True: kayitlar degismez; turetimler yeni nesne uretir (determinizm).
- Her alan `privacy` etiketi tasir; `secret` etiketi tanimlanamaz (yapisal engel).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pydantic_core import PydanticUndefined

PRIVACY_CLASSES_ALLOWED = ("public", "internal", "sensitive")


class CciModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def F(privacy: str, default: Any = PydanticUndefined, **kwargs: Any) -> Any:
    """`Field` sarmalayicisi: gizlilik etiketini json_schema_extra'ya yazar.

    `secret` bilerek reddedilir: kimlik bilgisi veya icerik tasiyan bir alan
    hicbir tipte tanimlanamaz (docs/PRIVACY.md §1).
    """
    if privacy not in PRIVACY_CLASSES_ALLOWED:
        raise ValueError(
            f"gizlilik etiketi {privacy!r} kabul edilmez; izinli: {PRIVACY_CLASSES_ALLOWED}"
        )
    extra = dict(kwargs.pop("json_schema_extra", None) or {})
    extra["privacy"] = privacy
    return Field(default, json_schema_extra=extra, **kwargs)
