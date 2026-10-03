"""SQLite mínimo: uma conexão por operação (o arquivo é local, o custo é desprezível), WAL e
migrações versionadas via `PRAGMA user_version`."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

# Para evoluir o esquema, ADICIONE itens no fim (nunca edite os antigos): cada índice é uma versão.
MIGRATIONS: list[str] = [
    """
    CREATE TABLE notes (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        text       TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
    );
    """,
]


class Database:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            with conn:  # commit/rollback
                yield conn
        finally:
            conn.close()

    def migrate(self) -> int:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            for i in range(version, len(MIGRATIONS)):
                conn.executescript(MIGRATIONS[i])
                conn.execute(f"PRAGMA user_version = {i + 1}")
            return len(MIGRATIONS)
