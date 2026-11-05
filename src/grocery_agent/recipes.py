from __future__ import annotations

import json
import re
from typing import Any

from .db import Database
from .llm import OllamaClient
from .models import Ingredient, RecipeDraft
from .obsidian import HEADING_RE, extract_tags

INGREDIENT_HEADING_RE = re.compile(r"\bingredients?\b", re.IGNORECASE)
SERVINGS_RE = re.compile(r"\b(?:serves?|servings?)\s*[:\-]?\s*(\d+)", re.IGNORECASE)
PREP_RE = re.compile(r"\bprep(?:aration)?\s*time\s*[:\-]?\s*(\d+)", re.IGNORECASE)
COOK_RE = re.compile(r"\bcook(?:ing)?\s*time\s*[:\-]?\s*(\d+)", re.IGNORECASE)
QUANTITY_RE = re.compile(
    r"^\s*(?:[-*+]\s*)?(?P<quantity>\d+(?:[.,]\d+)?|\d+\s*/\s*\d+)"
    r"\s*(?P<unit>kg|g|mg|ml|l|litres?|liters?|tsp|tbsp|teaspoons?|tablespoons?|"
    r"cups?|oz|lb|lbs|cloves?|cans?|tins?|packs?|bunch(?:es)?|slices?|pieces?|"
    r"each|whole)?\b\s*(?P<name>.+)$",
    re.IGNORECASE,
)
UNIT_MAP = {
    "teaspoon": "tsp",
    "teaspoons": "tsp",
    "tablespoon": "tbsp",
    "tablespoons": "tbsp",
    "litre": "l",
    "litres": "l",
    "liter": "l",
    "liters": "l",
    "clove": "clove",
    "cloves": "clove",
    "can": "tin",
    "cans": "tin",
    "tins": "tin",
    "pack": "pack",
    "packs": "pack",
    "bunch": "bunch",
    "bunches": "bunch",
    "slice": "slice",
    "slices": "slice",
    "piece": "piece",
    "pieces": "piece",
    "cup": "cup",
    "cups": "cup",
    "lbs": "lb",
}
DESCRIPTORS = {
    "fresh",
    "large",
    "small",
    "medium",
    "finely",
    "roughly",
    "chopped",
    "diced",
    "minced",
    "sliced",
    "grated",
    "peeled",
    "drained",
    "rinsed",
    "optional",
    "to",
    "taste",
    "plus",
    "extra",
}


def normalize_ingredient_name(name: str) -> str:
    text = re.sub(r"\([^)]*\)", " ", name.lower())
    text = re.sub(r"[^a-z0-9\s-]", " ", text)
    words = [word for word in text.split() if word not in DESCRIPTORS]
    if len(words) > 1 and words[-1].endswith("s") and not words[-1].endswith("ss"):
        words[-1] = words[-1][:-1]
    return " ".join(words).strip()


def _parse_quantity(value: str) -> float | None:
    value = value.replace(",", ".").strip()
    if "/" in value:
        parts = value.split("/")
        try:
            return float(parts[0]) / float(parts[1])
        except (ValueError, ZeroDivisionError):
            return None
    try:
        return float(value)
    except ValueError:
        return None


def parse_ingredient_line(line: str) -> Ingredient | None:
    cleaned = line.strip().lstrip("-*+ ").strip()
    if not cleaned:
        return None
    optional = "optional" in cleaned.lower()
    cleaned = re.sub(r"\s*\(optional\)\s*", " ", cleaned, flags=re.IGNORECASE).strip()
    match = QUANTITY_RE.match(cleaned)
    if not match:
        name = cleaned.strip(" .,")
        if not name or len(name) > 120:
            return None
        return Ingredient(name=name, optional=optional)
    quantity = _parse_quantity(match.group("quantity"))
    unit = (match.group("unit") or "").lower().strip()
    unit = UNIT_MAP.get(unit, unit or None)
    name = match.group("name").strip(" .,")
    name = re.sub(r"^(?:of|x)\s+", "", name, flags=re.IGNORECASE).strip()
    if not name:
        return None
    return Ingredient(name=name, quantity=quantity, unit=unit, optional=optional)


def _ingredient_section(body: str) -> str:
    matches = list(HEADING_RE.finditer(body))
    for index, match in enumerate(matches):
        if INGREDIENT_HEADING_RE.search(match.group(2)):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
            return body[match.end() : end]
    return ""


def _first_int(pattern: re.Pattern[str], text: str) -> int | None:
    match = pattern.search(text)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def extract_recipe_deterministic(title: str, body: str) -> RecipeDraft | None:
    section = _ingredient_section(body)
    if not section:
        return None
    ingredients: list[Ingredient] = []
    for line in section.splitlines():
        parsed = parse_ingredient_line(line)
        if parsed is not None:
            ingredients.append(parsed)
    if not ingredients:
        return None
    return RecipeDraft(
        title=title,
        servings=_first_int(SERVINGS_RE, body),
        prep_minutes=_first_int(PREP_RE, body),
        cook_minutes=_first_int(COOK_RE, body),
        ingredients=ingredients,
        tags=extract_tags({}, body),
        confidence=0.75,
        source={"extractor": "deterministic"},
    )


def is_recipe_like(title: str, body: str, tags: list[str]) -> bool:
    tag_text = " ".join(tags).lower()
    if any(word in tag_text for word in ("recipe", "food", "meal", "cook")):
        return True
    if _ingredient_section(body):
        return True
    return bool(re.search(r"\b(recipe|dinner|lunch|breakfast|meal)\b", title, re.IGNORECASE))


def _note_tags(frontmatter_json: str, body: str) -> list[str]:
    try:
        frontmatter = json.loads(frontmatter_json)
    except json.JSONDecodeError:
        frontmatter = {}
    if not isinstance(frontmatter, dict):
        frontmatter = {}
    return extract_tags(frontmatter, body)


def extract_recipes(
    db: Database,
    *,
    llm: OllamaClient | None = None,
    limit: int = 500,
) -> dict[str, int]:
    stats = {"notes": 0, "recipes": 0, "skipped": 0, "llm": 0}
    for row in db.notes.list_notes(limit=limit):
        stats["notes"] += 1
        body = str(row["body"])
        title = str(row["title"])
        tags = _note_tags(str(row["frontmatter_json"]), body)
        if not is_recipe_like(title, body, tags):
            stats["skipped"] += 1
            continue
        draft = extract_recipe_deterministic(title, body)
        if draft is None and llm is not None:
            draft = llm.extract_recipe(title, body)
            if draft is not None:
                stats["llm"] += 1
        if draft is None or not draft.ingredients:
            stats["skipped"] += 1
            continue
        draft.source["note_path"] = str(row["path"])
        ingredients = []
        for ingredient in draft.ingredients:
            ingredients.append(
                {
                    "name": ingredient.name,
                    "normalized_name": normalize_ingredient_name(ingredient.name),
                    "quantity": ingredient.quantity,
                    "unit": ingredient.unit,
                    "optional": ingredient.optional,
                    "note": ingredient.note,
                }
            )
        db.catalog.replace_recipe(
            note_id=int(row["id"]),
            title=draft.title,
            servings=draft.servings,
            prep_minutes=draft.prep_minutes,
            cook_minutes=draft.cook_minutes,
            confidence=draft.confidence,
            tags=draft.tags,
            source=draft.source,
            ingredients=ingredients,
        )
        stats["recipes"] += 1
    return stats


def ingredient_requirements(recipe: dict[str, Any], servings: int | None = None) -> list[Ingredient]:
    recipe_servings = recipe.get("servings") or 1
    target = servings or recipe_servings
    try:
        scale = float(target) / float(recipe_servings)
    except (TypeError, ValueError, ZeroDivisionError):
        scale = 1.0
    ingredients: list[Ingredient] = []
    for item in recipe.get("ingredients", []):
        quantity = item.get("quantity")
        if isinstance(quantity, int | float):
            quantity = float(quantity) * scale
        ingredients.append(
            Ingredient(
                name=str(item["name"]),
                quantity=quantity if isinstance(quantity, int | float) else None,
                unit=item.get("unit"),
                optional=bool(item.get("optional")),
                note=item.get("note"),
            )
        )
    return ingredients
