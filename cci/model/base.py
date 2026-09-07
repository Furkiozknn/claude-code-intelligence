"""Ortak taban model ve alan yardimcisi.

Kurallar (docs/DATA_MODEL.md, docs/PRIVACY.md):
- extra="forbid": sema disi anahtar kabul edilmez (allow-list ilkesi).
- frozen=True: kayitlar degismez; turetimler yeni nesne uretir (determinizm).
- Her alan `privacy` etiketi tasir; `secret` etiketi tanimlanamaz (yapisal engel).
"""

from __future__ import annotations

import typing
from typing import Any, Iterator, Mapping

from pydantic import BaseModel, ConfigDict, Field
from pydantic_core import PydanticUndefined

PRIVACY_CLASSES_ALLOWED = ("public", "internal", "sensitive")


def _submodels(annotation: object) -> Iterator[type[BaseModel]]:
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        yield annotation
        return
    for arg in typing.get_args(annotation):
        yield from _submodels(arg)


def strip_computed(model: type[BaseModel], data: Any) -> Any:
    """`model_dump` ciktisindan hesaplanan alanlari (ic modeller dahil) atar; boylece
    `extra="forbid"` altinda geri yuklenebilir (payload -> model)."""
    if not isinstance(data, Mapping):
        return data
    computed = set(getattr(model, "model_computed_fields", {}))
    out: dict[str, Any] = {}
    for key, value in data.items():
        if key in computed:
            continue
        info = model.model_fields.get(key)
        subs = list(_submodels(info.annotation)) if info is not None else []
        if subs and isinstance(value, Mapping):
            out[key] = strip_computed(subs[0], value)
        elif subs and isinstance(value, (list, tuple)):
            out[key] = [strip_computed(subs[0], v) if isinstance(v, Mapping) else v for v in value]
        else:
            out[key] = value
    return out


class CciModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    @classmethod
    def from_payload(cls, data: Mapping[str, Any]):
        """Olay payload'undan (model_dump(mode="json") ciktisi) geri yukleme."""
        return cls.model_validate(strip_computed(cls, data))


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
