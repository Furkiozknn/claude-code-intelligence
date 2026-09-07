"""Stage 4 - ham olay deposu: SQLite `events` (append-only).

- WAL + synchronous=NORMAL + busy_timeout 5 s; tek yazar (daemon), CLI salt okur.
- Idempotent yazim: `idempotency_key = sha256(type | ts | instance_id | payload_hash)`
  UNIQUE. Ayni olay ikinci kez gelirse yazilmaz (at-least-once kaynaklar).
- Saklama (R-12): satirlar `retention_days` (30) sonra silinir; istenirse payload
  daha erken NULL'lanir (`prune_payloads`), zarf + hash kalir.
- Dosya 0600, dizin 0700 (POSIX; Windows'ta ACL kullaniciya ait).
- `sensitive` alanlar burada oldugu gibi durur (yerel, kullanici disi erisim yok);
  disari cikan tek sey snapshot/API katmaninda hash'lenir (PRIVACY §5).
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Iterable, Iterator

from cci.events.envelope import Envelope, SourceRef

SCHEMA_VERSION = 1

_DDL = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events (
  event_id        TEXT PRIMARY KEY,
  idempotency_key TEXT NOT NULL UNIQUE,
  type            TEXT NOT NULL,
  ts              TEXT NOT NULL,
  received_at     TEXT NOT NULL,
  collector       TEXT NOT NULL,
  instance_id     TEXT NOT NULL,
  collector_version TEXT NOT NULL,
  schema_version  INTEGER NOT NULL,
  provider        TEXT,
  account_key     TEXT,
  session_id      TEXT,
  privacy_class   TEXT NOT NULL,
  evidence_class  TEXT NOT NULL,
  payload         TEXT,
  payload_hash    TEXT NOT NULL,
  pruned          INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_events_ts ON events(ts);
CREATE INDEX IF NOT EXISTS ix_events_type_ts ON events(type, ts);
CREATE INDEX IF NOT EXISTS ix_events_session_ts ON events(session_id, ts);
CREATE INDEX IF NOT EXISTS ix_events_received ON events(received_at);
"""


def idempotency_key(env: Envelope) -> str:
    raw = f"{env.type}|{env.ts.isoformat()}|{env.source.instance_id}|{env.payload_hash}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat(timespec="milliseconds")


class EventStore:
    def __init__(self, path: Path, *, retention_days: int = 30, read_only: bool = False) -> None:
        self.path = Path(path)
        self.retention_days = retention_days
        self.read_only = read_only
        if not read_only:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            _chmod(self.path.parent, 0o700)
        uri = f"file:{self.path.as_posix()}?mode={'ro' if read_only else 'rwc'}"
        self._conn = sqlite3.connect(uri, uri=True, isolation_level=None, check_same_thread=False)
        self._conn.execute("PRAGMA busy_timeout=5000")
        if not read_only:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.executescript(_DDL)
            self._conn.execute("INSERT OR IGNORE INTO meta(key, value) VALUES('schema_version', ?)",
                               (str(SCHEMA_VERSION),))
            _chmod(self.path, 0o600)

    # --- yasam dongusu -------------------------------------------------------
    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "EventStore":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    @property
    def journal_mode(self) -> str:
        return str(self._conn.execute("PRAGMA journal_mode").fetchone()[0])

    def schema_version(self) -> int:
        row = self._conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
        return int(row[0]) if row else 0

    # --- yazma ---------------------------------------------------------------
    def append(self, env: Envelope) -> bool:
        """True = yazildi, False = idempotent tekrar (atlandi)."""
        if self.read_only:
            raise PermissionError("salt okunur depo")
        cur = self._conn.execute(
            "INSERT OR IGNORE INTO events(event_id, idempotency_key, type, ts, received_at, collector, instance_id,"
            " collector_version, schema_version, provider, account_key, session_id, privacy_class, evidence_class,"
            " payload, payload_hash) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (env.event_id, idempotency_key(env), env.type, _iso(env.ts), _iso(env.received_at),
             env.source.collector, env.source.instance_id, env.source.collector_version, env.source.schema_version,
             env.provider, env.account_key, env.session_id, env.privacy_class, env.evidence_class.value,
             json.dumps(env.payload, ensure_ascii=False, sort_keys=True, default=str), env.payload_hash),
        )
        return cur.rowcount == 1

    def append_many(self, envelopes: Iterable[Envelope]) -> tuple[int, int]:
        """(yazilan, atlanan)."""
        written = skipped = 0
        self._conn.execute("BEGIN")
        try:
            for env in envelopes:
                if self.append(env):
                    written += 1
                else:
                    skipped += 1
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise
        return written, skipped

    # --- okuma ---------------------------------------------------------------
    def count(self, type_: str | None = None) -> int:
        if type_ is None:
            return int(self._conn.execute("SELECT COUNT(*) FROM events").fetchone()[0])
        return int(self._conn.execute("SELECT COUNT(*) FROM events WHERE type=?", (type_,)).fetchone()[0])

    def query(self, *, since: datetime | None = None, until: datetime | None = None,
              types: Iterable[str] | None = None, session_id: str | None = None,
              include_pruned: bool = False, limit: int | None = None) -> Iterator[Envelope]:
        sql = ["SELECT event_id, type, ts, received_at, collector, instance_id, collector_version, schema_version,"
               " provider, account_key, session_id, privacy_class, evidence_class, payload, pruned FROM events WHERE 1=1"]
        args: list[object] = []
        if since is not None:
            sql.append("AND ts >= ?"); args.append(_iso(since))
        if until is not None:
            sql.append("AND ts < ?"); args.append(_iso(until))
        if types:
            tl = list(types)
            sql.append(f"AND type IN ({','.join('?' * len(tl))})"); args.extend(tl)
        if session_id is not None:
            sql.append("AND session_id = ?"); args.append(session_id)
        if not include_pruned:
            sql.append("AND pruned = 0")
        sql.append("ORDER BY ts, event_id")
        if limit is not None:
            sql.append("LIMIT ?"); args.append(int(limit))
        for row in self._conn.execute(" ".join(sql), args):
            yield Envelope(
                event_id=row[0], type=row[1], ts=datetime.fromisoformat(row[2]),
                received_at=datetime.fromisoformat(row[3]),
                source=SourceRef(collector=row[4], instance_id=row[5], collector_version=row[6], schema_version=row[7]),
                provider=row[8], account_key=row[9], session_id=row[10], privacy_class=row[11],
                evidence_class=row[12], payload=json.loads(row[13]) if row[13] else {},
            )

    def stats(self) -> dict[str, object]:
        rows = self._conn.execute("SELECT type, COUNT(*) FROM events GROUP BY type ORDER BY type").fetchall()
        oldest = self._conn.execute("SELECT MIN(ts) FROM events").fetchone()[0]
        newest = self._conn.execute("SELECT MAX(ts) FROM events").fetchone()[0]
        size = self.path.stat().st_size if self.path.exists() else 0
        return {"events": self.count(), "by_type": {t: n for t, n in rows}, "oldest_ts": oldest,
                "newest_ts": newest, "db_bytes": size, "schema_version": self.schema_version()}

    # --- saklama --------------------------------------------------------------
    def prune(self, now: datetime | None = None) -> int:
        """`retention_days`'ten eski satirlari siler; silinen sayisini doner."""
        now = now or datetime.now(UTC)
        cutoff = _iso(now - timedelta(days=self.retention_days))
        cur = self._conn.execute("DELETE FROM events WHERE ts < ?", (cutoff,))
        return cur.rowcount

    def prune_payloads(self, older_than_days: int, now: datetime | None = None) -> int:
        """Payload'i NULL'lar, zarf + hash kalir (R-12). Doner: budanan sayisi."""
        now = now or datetime.now(UTC)
        cutoff = _iso(now - timedelta(days=older_than_days))
        cur = self._conn.execute("UPDATE events SET payload=NULL, pruned=1 WHERE ts < ? AND pruned = 0", (cutoff,))
        return cur.rowcount

    def vacuum(self) -> None:
        self._conn.execute("VACUUM")


def _chmod(path: Path, mode: int) -> None:
    if os.name == "nt":
        return
    try:
        os.chmod(path, mode)
    except OSError:
        pass
