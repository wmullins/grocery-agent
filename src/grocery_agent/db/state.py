from __future__ import annotations

from typing import Any

from ..models import Preference, utc_now
from .schema import _json, _loads


class StateStore:
    def __init__(self, connect) -> None:
        self._connect = connect

    def set_preference(self, preference: Preference) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO preferences(key, value_json, confidence, source, evidence, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json,"
                " confidence=excluded.confidence, source=excluded.source,"
                " evidence=excluded.evidence, updated_at=excluded.updated_at",
                (
                    preference.key,
                    _json(preference.value),
                    preference.confidence,
                    preference.source,
                    preference.evidence,
                    utc_now(),
                ),
            )

    def get_preference(self, key: str) -> Preference | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM preferences WHERE key = ?", (key,)).fetchone()
        if row is None:
            return None
        return Preference(
            key=str(row["key"]),
            value=_loads(row["value_json"], None),
            confidence=float(row["confidence"]),
            source=str(row["source"]),
            evidence=str(row["evidence"]),
        )

    def list_preferences(self) -> list[Preference]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM preferences ORDER BY key").fetchall()
        return [
            Preference(
                key=str(row["key"]),
                value=_loads(row["value_json"], None),
                confidence=float(row["confidence"]),
                source=str(row["source"]),
                evidence=str(row["evidence"]),
            )
            for row in rows
        ]

    def set_setting(self, key: str, value: Any) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO settings(key, value_json) VALUES (?, ?)"
                " ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json",
                (key, _json(value)),
            )

    def get_setting(self, key: str, default: Any = None) -> Any:
        with self._connect() as connection:
            row = connection.execute("SELECT value_json FROM settings WHERE key = ?", (key,)).fetchone()
        if row is None:
            return default
        return _loads(row["value_json"], default)
