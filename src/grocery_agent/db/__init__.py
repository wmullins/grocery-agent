from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from ..safety import ensure_private_dir, ensure_private_file
from .audit import AuditStore
from .catalog import CatalogStore
from .notes import NoteStore
from .orders import OrderStore
from .plans import PlanStore
from .proposals import ProposalStore
from .schema import SCHEMA, SCHEMA_VERSION
from .state import StateStore


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.notes = NoteStore(self.connect)
        self.catalog = CatalogStore(self.connect)
        self.plans = PlanStore(self.connect)
        self.proposals = ProposalStore(self.connect)
        self.orders = OrderStore(self.connect)
        self.state = StateStore(self.connect)
        self.audit = AuditStore(self.connect)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        ensure_private_dir(self.path.parent)
        with self.connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(SCHEMA)
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        ensure_private_file(self.path)
