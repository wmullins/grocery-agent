from __future__ import annotations

import sqlite3
from typing import Any

from ..models import utc_now
from .schema import _json


class NoteStore:
    def __init__(self, connect) -> None:
        self._connect = connect

    def upsert_note(
        self,
        *,
        path: str,
        title: str,
        folder: str,
        frontmatter: dict[str, Any],
        content_hash: str,
        body: str,
        chunks: list[tuple[int, str, str]],
    ) -> int:
        with self._connect() as connection:
            now = utc_now()
            connection.execute(
                "INSERT INTO notes(path, title, folder, frontmatter_json, content_hash, body, indexed_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(path) DO UPDATE SET"
                " title=excluded.title, folder=excluded.folder,"
                " frontmatter_json=excluded.frontmatter_json,"
                " content_hash=excluded.content_hash, body=excluded.body,"
                " indexed_at=excluded.indexed_at",
                (path, title, folder, _json(frontmatter), content_hash, body, now),
            )
            row = connection.execute("SELECT id FROM notes WHERE path = ?", (path,)).fetchone()
            if row is None:
                raise RuntimeError(f"Failed to insert note: {path}")
            note_id = int(row["id"])
            connection.execute("DELETE FROM note_chunks WHERE note_id = ?", (note_id,))
            connection.execute("DELETE FROM note_chunks_fts WHERE note_id = ?", (note_id,))
            for index, heading, content in chunks:
                connection.execute(
                    "INSERT INTO note_chunks(note_id, chunk_index, heading, content) VALUES (?, ?, ?, ?)",
                    (note_id, index, heading, content),
                )
                connection.execute(
                    "INSERT INTO note_chunks_fts(content, heading, note_id, chunk_index) VALUES (?, ?, ?, ?)",
                    (content, heading, note_id, index),
                )
            return note_id

    def delete_notes_not_in(self, paths: set[str]) -> int:
        if not paths:
            with self._connect() as connection:
                rows = connection.execute("SELECT id FROM notes").fetchall()
                for row in rows:
                    connection.execute("DELETE FROM note_chunks_fts WHERE note_id = ?", (row["id"],))
                connection.execute("DELETE FROM notes")
                return len(rows)
        placeholders = ",".join("?" for _ in paths)
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT id, path FROM notes WHERE path NOT IN ({placeholders})",
                tuple(paths),
            ).fetchall()
            for row in rows:
                connection.execute("DELETE FROM note_chunks_fts WHERE note_id = ?", (row["id"],))
                connection.execute("DELETE FROM notes WHERE id = ?", (row["id"],))
            return len(rows)

    def note_by_path(self, path: str) -> sqlite3.Row | None:
        with self._connect() as connection:
            return connection.execute("SELECT * FROM notes WHERE path = ?", (path,)).fetchone()

    def note_count(self) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM notes").fetchone()
            return int(row["count"]) if row else 0

    def search_notes(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        tokens = [token for token in query.replace('"', " ").split() if token]
        if not tokens:
            return []
        match = " AND ".join(f'"{token}"' for token in tokens)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT n.path, n.title, c.heading,"
                " snippet(note_chunks_fts, 0, '[', ']', '...', 18) AS snippet"
                " FROM note_chunks_fts"
                " JOIN note_chunks c ON c.note_id = note_chunks_fts.note_id"
                " AND c.chunk_index = note_chunks_fts.chunk_index"
                " JOIN notes n ON n.id = note_chunks_fts.note_id"
                " WHERE note_chunks_fts MATCH ?"
                " ORDER BY rank LIMIT ?",
                (match, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_notes(self, limit: int = 100) -> list[sqlite3.Row]:
        with self._connect() as connection:
            return connection.execute("SELECT * FROM notes ORDER BY path LIMIT ?", (limit,)).fetchall()
