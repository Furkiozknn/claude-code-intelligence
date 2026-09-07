import json

import pytest
from pydantic import ValidationError

from cci.model import F, SessionRef
from cci.model.schema import ALL_MODELS, check_privacy, export, iter_field_privacy


def test_every_field_has_an_allowed_privacy_tag():
    for model in ALL_MODELS:
        for path, privacy in iter_field_privacy(model):
            assert privacy in {"public", "internal", "sensitive"}, (model.__name__, path, privacy)


def test_no_secret_field_anywhere_and_no_forbidden_names():
    assert check_privacy() == []


def test_secret_tag_is_refused_structurally():
    with pytest.raises(ValueError):
        F("secret")


def test_unknown_keys_are_rejected():
    with pytest.raises(ValidationError):
        SessionRef(session_id="s1", prompt="merhaba")  # type: ignore[call-arg]


def test_forbidden_name_would_be_caught():
    from pydantic import BaseModel

    class Bad(BaseModel):
        prompt: str = F("internal")

    problems = check_privacy((Bad,))
    assert any("yasak alan adi" in p for p in problems)


def test_schema_export_forbids_additional_properties(tmp_path):
    written = export(tmp_path)
    assert len(written) == len(ALL_MODELS)
    for path in written:
        schema = json.loads(path.read_text(encoding="utf-8"))
        assert schema.get("additionalProperties") is False, path.name
        for name, prop in schema.get("properties", {}).items():
            assert "privacy" in prop, (path.name, name)
