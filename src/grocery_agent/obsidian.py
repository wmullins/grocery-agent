from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

from .db import Database
from .safety import (
    AGENT_MARKER,
    SafetyError,
    assert_within,
    atomic_write_text,
    is_agent_owned,
)

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
INLINE_TAG_RE = re.compile(r"(?<![\w/#])#([A-Za-z0-9_/-]{2,})")
SKIP_DIRS = {".obsidian", ".trash", ".git", "node_modules", "__pycache__", ".venv"}
DEFAULT_EXCLUDES = ("99 Templates",)


@dataclass
class Note:
    path: str
    title: str
    folder: str
    frontmatter: dict[str, Any]
    body: str
    content_hash: str
    chunks: list[tuple[int, str, str]] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text
    raw = text[4:end]
    body = text[end + 5 :]
    try:
        loaded = yaml.safe_load(raw)
    except (yaml.YAMLError, ValueError):
        return {}, text
    if not isinstance(loaded, dict):
        return {}, text
    return _json_safe(loaded), body


def extract_tags(frontmatter: dict[str, Any], body: str) -> list[str]:
    tags: list[str] = []
    raw_tags = frontmatter.get("tags")
    if isinstance(raw_tags, str):
        tags.extend(part.strip() for part in raw_tags.split(",") if part.strip())
    elif isinstance(raw_tags, list):
        tags.extend(str(part).strip() for part in raw_tags if str(part).strip())
    tags.extend(match.group(1).lower() for match in INLINE_TAG_RE.finditer(body))
    seen: set[str] = set()
    ordered: list[str] = []
    for tag in tags:
        normalized = tag.lstrip("#").lower()
        if normalized and normalized not in seen:
            seen.add(normalized)
            ordered.append(normalized)
    return ordered


def note_title(frontmatter: dict[str, Any], body: str, path: Path) -> str:
    explicit = frontmatter.get("title")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    match = HEADING_RE.search(body)
    if match:
        return match.group(2).strip()
    return path.stem


def chunk_body(body: str, limit: int = 1400) -> list[tuple[int, str, str]]:
    matches = list(HEADING_RE.finditer(body))
    sections: list[tuple[str, str]] = []
    if not matches:
        sections.append(("", body.strip()))
    else:
        prefix = body[: matches[0].start()].strip()
        if prefix:
            sections.append(("", prefix))
        for index, match in enumerate(matches):
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
            sections.append((match.group(2).strip(), body[start:end].strip()))
    chunks: list[tuple[int, str, str]] = []
    for heading, content in sections:
        if not content:
            continue
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", content) if part.strip()]
        current = ""
        for paragraph in paragraphs:
            if current and len(current) + len(paragraph) + 2 > limit:
                chunks.append((len(chunks), heading, current))
                current = paragraph
            else:
                current = f"{current}\n\n{paragraph}".strip()
        if current:
            chunks.append((len(chunks), heading, current))
    if not chunks and body.strip():
        chunks.append((0, "", body.strip()))
    return chunks


class Vault:
    def __init__(
        self,
        root: Path,
        output_folder: str = "10 Projects/Grocery Agent",
        excludes: tuple[str, ...] = DEFAULT_EXCLUDES,
    ) -> None:
        self.root = root.expanduser()
        self.output_folder = output_folder.strip("/")
        self.excludes = excludes

    @property
    def output_root(self) -> Path:
        return assert_within(self.root / self.output_folder, self.root)

    def iter_notes(self) -> list[Path]:
        paths: list[Path] = []
        if not self.root.is_dir():
            return paths
        output = self.output_root
        for path in self.root.rglob("*.md"):
            relative = path.relative_to(self.root).as_posix()
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            if any(relative == prefix or relative.startswith(prefix + "/") for prefix in self.excludes):
                continue
            if path == output or output in path.parents:
                continue
            if path.is_file():
                paths.append(path)
        return sorted(paths)

    def read_note(self, path: Path) -> Note:
        text = path.read_text(encoding="utf-8", errors="replace")
        frontmatter, body = parse_frontmatter(text)
        relative = path.relative_to(self.root).as_posix()
        return Note(
            path=relative,
            title=note_title(frontmatter, body, path),
            folder=str(Path(relative).parent) if "/" in relative else "",
            frontmatter=frontmatter,
            body=body,
            content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            chunks=chunk_body(body),
            tags=extract_tags(frontmatter, body),
        )

    def sync(self, db: Database) -> dict[str, int]:
        paths = self.iter_notes()
        seen: set[str] = set()
        indexed = 0
        unchanged = 0
        for path in paths:
            note = self.read_note(path)
            existing = db.notes.note_by_path(note.path)
            if existing and str(existing["content_hash"]) == note.content_hash:
                unchanged += 1
                seen.add(note.path)
                continue
            db.notes.upsert_note(
                path=note.path,
                title=note.title,
                folder=note.folder,
                frontmatter=note.frontmatter,
                content_hash=note.content_hash,
                body=note.body,
                chunks=note.chunks,
            )
            seen.add(note.path)
            indexed += 1
        removed = db.notes.delete_notes_not_in(seen)
        return {
            "notes": len(paths),
            "indexed": indexed,
            "unchanged": unchanged,
            "removed": removed,
        }

    def ensure_agent_folder(self) -> Path:
        root = self.output_root
        root.mkdir(parents=True, exist_ok=True)
        for name in ("Meal Plans", "Shopping Lists", "Recipes"):
            (root / name).mkdir(parents=True, exist_ok=True)
        dashboard = root / "Grocery Agent.md"
        if not dashboard.exists():
            content = (
                "---\n"
                f"{AGENT_MARKER}\n"
                "type: dashboard\n"
                "---\n\n"
                "# Grocery Agent\n\n"
                "This folder is managed by the local grocery agent. "
                "Generated meal plans and shopping lists appear here.\n"
            )
            atomic_write_text(dashboard, content, mode=0o600)
        return root

    def write_agent_note(self, relative_path: str, content: str) -> Path:
        root = self.output_root
        target = assert_within(root / relative_path, root)
        if target.exists():
            existing = target.read_text(encoding="utf-8", errors="replace")
            if not is_agent_owned(existing):
                raise SafetyError(f"Refusing to overwrite non-agent note: {target}")
        if AGENT_MARKER not in content:
            content = f"---\n{AGENT_MARKER}\n---\n\n{content.lstrip()}"
        atomic_write_text(target, content, mode=0o600)
        return target
