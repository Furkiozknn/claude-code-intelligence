from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from cci.adapters import (Capabilities, Cursor, FileCursor, Health, ProbeRoot, ProviderAdapter,
                          RawBatch, Registry, assert_contract)
from cci.model import SourceInstance


class FakeAdapter(ProviderAdapter):
    name = "fake"
    provider = "fakeprov"

    def __init__(self, verified=True, dup=False, wrong_provider=False):
        self._verified, self._dup, self._wrong = verified, dup, wrong_provider

    def _inst(self, i):
        return SourceInstance(provider="other" if self._wrong else "fakeprov",
                              instance_id="fake-1" if self._dup else f"fake-{i}",
                              label=f"Fake {i}", kind="cli", schema_verified=self._verified,
                              verified_at=date(2026, 9, 7) if self._verified else None)

    def discover(self):
        return (self._inst(1), self._inst(2))

    def probe_roots(self):
        return (ProbeRoot(path="/tmp/fake", label="root", exists=False),)

    def capabilities(self):
        return Capabilities(tokens=True, schema_verified=self._verified,
                            verified_at=date(2026, 9, 7) if self._verified else None)

    def collect(self, instance, cursor):
        return RawBatch(instance=instance)

    def normalize(self, batch):
        return ()

    def health(self):
        return Health(status="ok", last_success_at=datetime.now(UTC))


def test_contract_passes_for_well_formed_adapter():
    assert_contract(FakeAdapter())


def test_contract_rejects_duplicate_instance_ids():
    with pytest.raises(AssertionError):
        assert_contract(FakeAdapter(dup=True))


def test_contract_rejects_provider_mismatch():
    with pytest.raises(AssertionError):
        assert_contract(FakeAdapter(wrong_provider=True))


def test_schema_verified_requires_date():
    with pytest.raises(ValidationError):
        Capabilities(schema_verified=True)


def test_unverified_adapter_is_allowed_but_marked():
    a = FakeAdapter(verified=False)
    assert_contract(a)
    assert all(i.schema_verified is False for i in a.discover())


def test_registry_registers_and_lists_instances():
    reg = Registry()
    reg.register(FakeAdapter())
    assert reg.names() == ("fake",)
    assert [i.instance_id for _, i in reg.instances()] == ["fake-1", "fake-2"]
    with pytest.raises(ValueError):
        reg.register(FakeAdapter())


def test_cursor_and_batch_invariants():
    with pytest.raises(ValidationError):
        FileCursor(size=10, mtime_ns=1, bytes_consumed=11)
    c = Cursor(files={"a.jsonl": FileCursor(size=10, mtime_ns=1, bytes_consumed=4)})
    b = RawBatch(instance=FakeAdapter().discover()[0], next_cursor=c, complete=False, skipped=2)
    assert b.next_cursor.files["a.jsonl"].bytes_consumed == 4 and not b.complete


def test_describe_is_json_serialisable():
    d = FakeAdapter().describe()
    assert d["name"] == "fake" and d["capabilities"]["tokens"] is True and len(d["instances"]) == 2
