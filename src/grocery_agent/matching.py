from __future__ import annotations

import math
import re

from .models import Candidate, Ingredient, Product
from .recipes import normalize_ingredient_name

SCORE_UNIT_MATCH_BONUS = 0.1
SCORE_STOCK_AVAILABLE_BONUS = 0.1
SCORE_STOCK_UNAVAILABLE_PENALTY = 0.2
SCORE_UNKNOWN_PRICE_PENALTY = 0.05
SCORE_KNOWN_PRICE_BONUS = 0.02
SCORE_PACK_PENALTY_PER_EXTRA = 0.03
SCORE_MIN_THRESHOLD = 0.0


def normalize_product_text(text: str) -> str:
    return normalize_ingredient_name(text)


def _unit_base(unit: str | None) -> tuple[str, float]:
    if not unit:
        return ("count", 1.0)
    unit = unit.lower().strip()
    if unit in {"ml", "millilitre", "millilitres", "milliliter", "milliliters"}:
        return ("ml", 1.0)
    if unit in {"l", "litre", "litres", "liter", "liters"}:
        return ("ml", 1000.0)
    if unit in {"g", "gram", "grams"}:
        return ("g", 1.0)
    if unit in {"kg", "kilogram", "kilograms"}:
        return ("g", 1000.0)
    if unit in {
        "each",
        "piece",
        "pieces",
        "pack",
        "packs",
        "tin",
        "tins",
        "can",
        "cans",
        "bunch",
        "bunches",
        "slice",
        "slices",
    }:
        return ("count", 1.0)
    return ("count", 1.0)


def _first_number(text: str | None) -> float | None:
    if not text:
        return None
    match = re.search(r"\d+(?:[.,]\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", "."))
    except ValueError:
        return None


def pack_quantity(product: Product) -> tuple[str, float]:
    base, multiplier = _unit_base(product.unit_measure)
    number = _first_number(product.size) or 1.0
    return (base, number * multiplier)


def packs_needed(ingredient: Ingredient, product: Product) -> int:
    if not ingredient.quantity:
        return 1
    ingredient_base, ingredient_multiplier = _unit_base(ingredient.unit)
    required = float(ingredient.quantity) * ingredient_multiplier
    product_base, pack_base = pack_quantity(product)
    if product_base == ingredient_base and pack_base > 0:
        packs = math.ceil(required / pack_base)
        return max(1, packs)
    return 1


def score_match(ingredient: Ingredient, product: Product) -> float:
    ingredient_tokens = set(normalize_ingredient_name(ingredient.name).split())
    product_tokens = set(normalize_product_text(product.name).split())
    if not ingredient_tokens or not product_tokens:
        return 0.0
    intersection = ingredient_tokens & product_tokens
    union = ingredient_tokens | product_tokens
    overlap = len(intersection) / len(union)
    if overlap <= 0:
        return 0.0
    score = overlap
    if ingredient.unit and product.unit_measure:
        ingredient_base, _ = _unit_base(ingredient.unit)
        product_base, _ = _unit_base(product.unit_measure)
        if ingredient_base == product_base:
            score += SCORE_UNIT_MATCH_BONUS
    if product.in_stock is True:
        score += SCORE_STOCK_AVAILABLE_BONUS
    elif product.in_stock is False:
        score -= SCORE_STOCK_UNAVAILABLE_PENALTY
    if product.price_minor is None:
        score -= SCORE_UNKNOWN_PRICE_PENALTY
    else:
        score += SCORE_KNOWN_PRICE_BONUS
    packs = packs_needed(ingredient, product)
    score -= SCORE_PACK_PENALTY_PER_EXTRA * max(0, packs - 1)
    return min(max(score, SCORE_MIN_THRESHOLD), 1.0)


def rank_products(ingredient: Ingredient, products: list[Product]) -> list[Candidate]:
    ranked = [Candidate(product=product, score=score_match(ingredient, product)) for product in products]
    ranked.sort(key=lambda item: item.score, reverse=True)
    return ranked


def best_match(ingredient: Ingredient, products: list[Product]) -> Candidate | None:
    ranked = rank_products(ingredient, products)
    if not ranked or ranked[0].score <= 0.0:
        return None
    return ranked[0]
