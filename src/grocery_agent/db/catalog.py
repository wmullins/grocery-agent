from __future__ import annotations

from typing import Any

from ..models import utc_now
from .schema import _json, _loads


class CatalogStore:
    def __init__(self, connect) -> None:
        self._connect = connect

    def replace_recipe(
        self,
        *,
        note_id: int | None,
        title: str,
        servings: int | None,
        prep_minutes: int | None,
        cook_minutes: int | None,
        confidence: float,
        tags: list[str],
        source: dict[str, Any],
        ingredients: list[dict[str, Any]],
    ) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id FROM recipes WHERE note_id IS ? AND title = ?",
                (note_id, title),
            ).fetchone()
            if row is None:
                cursor = connection.execute(
                    "INSERT INTO recipes(note_id, title, servings, prep_minutes, cook_minutes,"
                    " confidence, tags_json, source_json, created_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        note_id,
                        title,
                        servings,
                        prep_minutes,
                        cook_minutes,
                        confidence,
                        _json(tags),
                        _json(source),
                        utc_now(),
                    ),
                )
                recipe_id = int(cursor.lastrowid or 0)
            else:
                recipe_id = int(row["id"])
                connection.execute(
                    "UPDATE recipes SET servings = ?, prep_minutes = ?, cook_minutes = ?,"
                    " confidence = ?, tags_json = ?, source_json = ? WHERE id = ?",
                    (
                        servings,
                        prep_minutes,
                        cook_minutes,
                        confidence,
                        _json(tags),
                        _json(source),
                        recipe_id,
                    ),
                )
                connection.execute("DELETE FROM recipe_ingredients WHERE recipe_id = ?", (recipe_id,))
            for position, ingredient in enumerate(ingredients):
                connection.execute(
                    "INSERT INTO recipe_ingredients(recipe_id, position, name, normalized_name,"
                    " quantity, unit, optional, note) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        recipe_id,
                        position,
                        ingredient["name"],
                        ingredient["normalized_name"],
                        ingredient.get("quantity"),
                        ingredient.get("unit"),
                        1 if ingredient.get("optional") else 0,
                        ingredient.get("note"),
                    ),
                )
            return recipe_id

    def clear_recipes(self) -> int:
        """Remove all recipes and ingredients from the DB (for fresh extraction)."""
        with self._connect() as connection:
            connection.execute("DELETE FROM recipe_ingredients")
            connection.execute("DELETE FROM recipes")
            return 0

    def get_recipe(self, recipe_id: int) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,)).fetchone()
        if row is None:
            return None
        item = dict(row)
        item["tags"] = _loads(item.pop("tags_json"), [])
        item["source"] = _loads(item.pop("source_json"), {})
        with self._connect() as connection:
            ingredients = connection.execute(
                "SELECT * FROM recipe_ingredients WHERE recipe_id = ? ORDER BY position",
                (recipe_id,),
            ).fetchall()
        item["ingredients"] = [dict(ingredient) for ingredient in ingredients]
        return item

    def list_recipes(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT r.*, n.path AS note_path FROM recipes r"
                " LEFT JOIN notes n ON n.id = r.note_id"
                " ORDER BY r.title LIMIT ?",
                (limit,),
            ).fetchall()
        results: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["tags"] = _loads(item.pop("tags_json"), [])
            item["source"] = _loads(item.pop("source_json"), {})
            with self._connect() as connection:
                ingredients = connection.execute(
                    "SELECT * FROM recipe_ingredients WHERE recipe_id = ? ORDER BY position",
                    (item["id"],),
                ).fetchall()
            item["ingredients"] = [dict(ingredient) for ingredient in ingredients]
            results.append(item)
        return results

    def record_product(self, product, *, observed_at: str | None = None) -> int:
        now = observed_at or utc_now()
        with self._connect() as connection:
            product_id: int | None = None
            if product.gtin:
                row = connection.execute("SELECT id FROM products WHERE gtin = ?", (product.gtin,)).fetchone()
                if row:
                    product_id = int(row["id"])
            if product_id is None:
                row = connection.execute(
                    "SELECT id FROM products WHERE canonical_name = ?"
                    " AND COALESCE(size, '') = COALESCE(?, '')"
                    " AND gtin IS NULL LIMIT 1",
                    (product.name, product.size),
                ).fetchone()
                if row:
                    product_id = int(row["id"])
            if product_id is None:
                cursor = connection.execute(
                    "INSERT INTO products(gtin, canonical_name, size, unit, created_at) VALUES (?, ?, ?, ?, ?)",
                    (product.gtin, product.name, product.size, product.unit_measure, now),
                )
                product_id = int(cursor.lastrowid or 0)
            connection.execute(
                "INSERT INTO retailer_products(product_id, retailer, retailer_product_id,"
                " name, size, unit, gtin, last_seen_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(retailer, retailer_product_id) DO UPDATE SET"
                " product_id=excluded.product_id, name=excluded.name, size=excluded.size,"
                " unit=excluded.unit, gtin=excluded.gtin, last_seen_at=excluded.last_seen_at",
                (
                    product_id,
                    product.provider,
                    product.product_uid,
                    product.name,
                    product.size,
                    product.unit_measure,
                    product.gtin,
                    now,
                ),
            )
            retailer_row = connection.execute(
                "SELECT id FROM retailer_products WHERE retailer = ? AND retailer_product_id = ?",
                (product.provider, product.product_uid),
            ).fetchone()
            if retailer_row is None:
                raise RuntimeError("Failed to persist retailer product")
            retailer_product_id = int(retailer_row["id"])
            connection.execute(
                "INSERT INTO price_observations(retailer_product_id, price_minor,"
                " unit_price_minor, unit_measure, in_stock, promotion_json, observed_at, source)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    retailer_product_id,
                    product.price_minor,
                    product.unit_price_minor,
                    product.unit_measure,
                    None if product.in_stock is None else int(product.in_stock),
                    _json([promotion.model_dump() for promotion in product.promotions]),
                    now,
                    "open-supermarkets",
                ),
            )
            return retailer_product_id
