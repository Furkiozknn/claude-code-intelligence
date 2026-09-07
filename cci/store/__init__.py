"""Depolama (docs/ARCHITECTURE.md §5, EVENTS.md §4-5)."""

from .sqlite import EventStore, SCHEMA_VERSION, idempotency_key

__all__ = ["EventStore", "SCHEMA_VERSION", "idempotency_key"]
