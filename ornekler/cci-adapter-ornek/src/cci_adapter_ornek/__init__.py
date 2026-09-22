"""Ucuncu taraf adaptor ornegi: CI bunu gercekten kurar ve cci'in gorup
gormedigini sorar. docs/EXTENDING.md §2b bu paketi tarif ediyor."""
from datetime import UTC, date, datetime
from pathlib import Path

from cci.adapters import Capabilities, Health, ProbeRoot, ProviderAdapter, RawBatch
from cci.model import SourceInstance


class OrnekAdapter(ProviderAdapter):
    """Hicbir yerden veri okumaz; var olmasi tek basina bir iddiadir."""

    name = "ornek"
    provider = "ornekprov"

    def __init__(self, env=None, home=None):
        self._home = Path(home) if home else Path.home()

    def discover(self):
        return ()

    def probe_roots(self):
        return (ProbeRoot(path=str(self._home / ".ornek"), label="ornek", exists=False),)

    def capabilities(self):
        return Capabilities(tokens=True, schema_verified=False)

    def collect(self, instance, cursor):
        return RawBatch(instance=instance)

    def normalize(self, batch):
        return ()

    def health(self):
        return Health(status="down", last_success_at=datetime.now(UTC))


def build(env=None, home=None):
    return OrnekAdapter(env=env, home=home)
