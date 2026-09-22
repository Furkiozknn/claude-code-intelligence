"""Model kimligi -> gorunen ad (toktrack normalizasyonu). Fiyat eslemesi Stage 6."""

from __future__ import annotations

import re

from cci.model.usage import ModelRef

_DATE_SUFFIX = re.compile(r"-(\d{8})$")
_CLAUDE = re.compile(r"^(?:.*[./])?(?:anthropic\.)?claude-(?P<family>[a-z]+)-(?P<ver>\d+(?:-\d+)*)")
SYNTHETIC = "<synthetic>"


def normalize_model_id(model_id: str) -> str:
    """Tarih son ekini at, bolge/saglayici onekini birak (`us.anthropic.claude-…` -> `claude-…`)."""
    m = model_id.strip()
    m = _DATE_SUFFIX.sub("", m)
    m = re.sub(r"-v\d+:\d+$", "", m)  # bedrock `-v1:0`
    idx = m.find("claude-")
    if idx > 0:
        m = m[idx:]
    return m


def display_name(model_id: str) -> str:
    """Model kimligini okunur bir ada cevirir; tanimadigini oldugu gibi birakir.

    Tanimadigi bir kimligi tahmin etmiyor. Yanlis bir gorunur ad, raporda dogru
    bir ad gibi durur ve okuyan kisi onu duzeltmez -- oysa ham kimlik, en
    azindan tanimadigini soyler.
    """
    if model_id == SYNTHETIC:
        return "synthetic"
    norm = normalize_model_id(model_id)
    m = _CLAUDE.match(norm)
    if not m:
        return model_id
    family = m.group("family").capitalize()
    ver = m.group("ver").replace("-", ".")
    return f"{family} {ver}"


def model_ref(model_id: str | None) -> ModelRef:
    """Model kimligini bir `ModelRef`e cevirir, bilinmeyenleri isaretleyerek.

    Bos ya da tanimsiz bir kimlik `unknown=True` ile doner. Bu bayrak asagida
    onemli: bilinmeyen bir modelin fiyati da bilinmiyordur, ve bilinmeyen bir
    fiyati sifir saymak toplami sessizce yanlisa dusurur.
    """
    if not model_id:
        return ModelRef(id="unknown", display="unknown", unknown=True)
    if model_id == SYNTHETIC:
        return ModelRef(id=SYNTHETIC, display="synthetic", family=None, unknown=True)
    norm = normalize_model_id(model_id)
    m = _CLAUDE.match(norm)
    if not m:
        return ModelRef(id=norm, display=model_id, unknown=True)
    return ModelRef(id=norm, display=display_name(model_id), family=m.group("family"), unknown=False)
