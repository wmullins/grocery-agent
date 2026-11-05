from __future__ import annotations

from typing import Any

from ..models import utc_now
from .schema import _json


class AuditStore:
    def __init__(self, connect) -> None:
        self._connect = connect

    def audit(self, action: str, entity: str, entity_id: str | None, detail: dict[str, Any]) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO audit_log(action, entity, entity_id, detail_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (action, entity, entity_id, _json(detail), utc_now()),
            )
