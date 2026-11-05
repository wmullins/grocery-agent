from __future__ import annotations

from typing import Any

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    folder TEXT NOT NULL,
    frontmatter_json TEXT NOT NULL DEFAULT '{}',
    content_hash TEXT NOT NULL,
    body TEXT NOT NULL,
    indexed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS note_chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    note_id INTEGER NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    heading TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL,
    UNIQUE(note_id, chunk_index)
);

CREATE VIRTUAL TABLE IF NOT EXISTS note_chunks_fts USING fts5(
    content,
    heading,
    note_id UNINDEXED,
    chunk_index UNINDEXED,
    tokenize = 'porter unicode61'
);

CREATE TABLE IF NOT EXISTS recipes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    note_id INTEGER REFERENCES notes(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    servings INTEGER,
    prep_minutes INTEGER,
    cook_minutes INTEGER,
    confidence REAL NOT NULL DEFAULT 0.5,
    tags_json TEXT NOT NULL DEFAULT '[]',
    source_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    UNIQUE(note_id, title)
);

CREATE TABLE IF NOT EXISTS recipe_ingredients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recipe_id INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    quantity REAL,
    unit TEXT,
    optional INTEGER NOT NULL DEFAULT 0,
    note TEXT
);

CREATE TABLE IF NOT EXISTS meal_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    start_date TEXT NOT NULL,
    days INTEGER NOT NULL,
    servings INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS meal_plan_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    meal_plan_id INTEGER NOT NULL REFERENCES meal_plans(id) ON DELETE CASCADE,
    day_index INTEGER NOT NULL,
    meal_type TEXT NOT NULL,
    title TEXT NOT NULL,
    recipe_id INTEGER REFERENCES recipes(id) ON DELETE SET NULL,
    servings INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    gtin TEXT UNIQUE,
    canonical_name TEXT NOT NULL,
    brand TEXT,
    size TEXT,
    unit TEXT,
    category TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS retailer_products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER REFERENCES products(id) ON DELETE SET NULL,
    retailer TEXT NOT NULL,
    retailer_product_id TEXT NOT NULL,
    name TEXT NOT NULL,
    size TEXT,
    unit TEXT,
    gtin TEXT,
    last_seen_at TEXT NOT NULL,
    UNIQUE(retailer, retailer_product_id)
);

CREATE TABLE IF NOT EXISTS price_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    retailer_product_id INTEGER NOT NULL REFERENCES retailer_products(id) ON DELETE CASCADE,
    price_minor INTEGER,
    unit_price_minor INTEGER,
    unit_measure TEXT,
    in_stock INTEGER,
    promotion_json TEXT NOT NULL DEFAULT '[]',
    observed_at TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'open-supermarkets'
);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    retailer TEXT NOT NULL,
    order_ref_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT '',
    ordered_at TEXT,
    total_minor INTEGER,
    source TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    UNIQUE(retailer, order_ref_hash)
);

CREATE TABLE IF NOT EXISTS order_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    retailer_product_id TEXT,
    name TEXT NOT NULL,
    quantity REAL NOT NULL DEFAULT 1,
    unit_price_minor INTEGER,
    line_total_minor INTEGER,
    promotion_json TEXT
);

CREATE TABLE IF NOT EXISTS preferences (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0.5,
    source TEXT NOT NULL DEFAULT 'explicit',
    evidence TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS proposals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    retailer TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    budget_minor INTEGER,
    subtotal_minor INTEGER,
    delivery_minor INTEGER,
    total_minor INTEGER,
    created_at TEXT NOT NULL,
    approved_at TEXT,
    applied_at TEXT,
    idempotency_key TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS proposal_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proposal_id INTEGER NOT NULL REFERENCES proposals(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    product_uid TEXT NOT NULL,
    name TEXT NOT NULL,
    quantity REAL NOT NULL,
    unit_price_minor INTEGER,
    line_total_minor INTEGER,
    promotion_json TEXT,
    alternatives_json TEXT NOT NULL DEFAULT '[]',
    ingredient_names_json TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS approvals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proposal_id INTEGER NOT NULL REFERENCES proposals(id) ON DELETE CASCADE,
    decision TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    decided_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL,
    entity TEXT NOT NULL,
    entity_id TEXT,
    detail_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_note_chunks_note ON note_chunks(note_id);
CREATE INDEX IF NOT EXISTS idx_recipe_ingredients_recipe ON recipe_ingredients(recipe_id);
CREATE INDEX IF NOT EXISTS idx_price_product_time ON price_observations(retailer_product_id, observed_at);
CREATE INDEX IF NOT EXISTS idx_retailer_products_lookup ON retailer_products(retailer, retailer_product_id);
CREATE INDEX IF NOT EXISTS idx_proposals_status ON proposals(status);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at);
"""


def _json(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _loads(value: str | None, default: Any) -> Any:
    import json

    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default
