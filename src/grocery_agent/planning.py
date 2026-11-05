from __future__ import annotations

import hashlib
from datetime import date
from typing import Any

from .db import Database
from .matching import best_match, packs_needed, rank_products
from .models import Ingredient, MealPlan, MealPlanItem, Proposal, ProposalLine
from .retail.adapter import RetailAdapter


class PlanningError(RuntimeError):
    pass


class MealPlanner:
    def __init__(self, db: Database, retailer: str = "sainsburys") -> None:
        self.db = db
        self.retailer = retailer

    def plan_meals(self, days: int, servings: int, meals: list[str] | None = None) -> MealPlan:
        recipes = self.db.catalog.list_recipes()
        if not recipes and not meals:
            raise PlanningError("No recipes found. Add recipe notes to the vault and run `grocery recipes extract`.")
        start = date.today()
        items: list[MealPlanItem] = []
        for day in range(days):
            title = meals[day] if meals and day < len(meals) else recipes[day % len(recipes)]["title"]
            recipe_id = None if meals else int(recipes[day % len(recipes)]["id"])
            items.append(
                MealPlanItem(
                    day_index=day,
                    meal_type="dinner",
                    title=title,
                    recipe_id=recipe_id,
                    servings=servings,
                )
            )
        plan = MealPlan(start_date=start.isoformat(), days=days, servings=servings, items=items)
        plan.id = self.db.plans.create_meal_plan(plan)
        return plan

    def _ingredient_recipes(self, plan: MealPlan) -> dict[int, dict[str, Any]]:
        recipes: dict[int, dict[str, Any]] = {}
        for item in plan.items:
            if item.recipe_id and item.recipe_id not in recipes:
                recipe = self.db.catalog.get_recipe(item.recipe_id)
                if recipe:
                    recipes[item.recipe_id] = recipe
        return recipes

    def aggregate_ingredients(self, plan: MealPlan) -> list[Ingredient]:
        recipes = self._ingredient_recipes(plan)
        combined: dict[str, dict[str, Any]] = {}
        for item in plan.items:
            if item.recipe_id:
                recipe = recipes.get(item.recipe_id)
                if not recipe:
                    continue
                scale = float(item.servings) / float(recipe.get("servings") or 1)
                ingredient_items = recipe.get("ingredients", [])
            else:
                scale = 1.0
                ingredient_items = [
                    {
                        "name": item.title,
                        "normalized_name": item.title,
                        "quantity": 1,
                        "unit": None,
                        "optional": False,
                    }
                ]
            for raw in ingredient_items:
                name = str(raw["name"])
                normalized = str(raw["normalized_name"])
                quantity = raw.get("quantity")
                if isinstance(quantity, int | float):
                    quantity = float(quantity) * scale
                unit = raw.get("unit")
                existing = combined.get(normalized)
                if not existing:
                    combined[normalized] = {
                        "name": name,
                        "normalized_name": normalized,
                        "quantity": quantity,
                        "unit": unit,
                        "optional": bool(raw.get("optional")),
                    }
                    continue
                if (
                    existing.get("unit") == unit
                    and isinstance(quantity, int | float)
                    and isinstance(existing.get("quantity"), int | float)
                ):
                    existing["quantity"] = float(existing["quantity"]) + float(quantity)
                existing["optional"] = existing.get("optional", False) or bool(raw.get("optional"))
        return [
            Ingredient(
                name=item["name"],
                normalized_name=item["normalized_name"],
                quantity=item.get("quantity"),
                unit=item.get("unit"),
                optional=bool(item.get("optional")),
            )
            for item in combined.values()
        ]

    def propose(
        self,
        plan: MealPlan,
        retailer: str | None,
        adapter: RetailAdapter,
        budget_gbp: float | None = None,
    ) -> Proposal:
        retailer = retailer or self.retailer
        requirements = self.aggregate_ingredients(plan)
        if not requirements:
            raise PlanningError("No purchasable ingredients found for this plan.")
        queries = [req.name for req in requirements]
        results = adapter.search_batch(retailer, queries, limit=5)
        lines: list[ProposalLine] = []
        subtotal_minor = 0
        unknown_count = 0
        for position, req in enumerate(requirements, start=1):
            products = results.get(req.name, [])
            match = best_match(req, products)
            if not match:
                unknown_count += 1
                lines.append(
                    ProposalLine(
                        position=position,
                        product_uid=req.normalized_name or req.name,
                        name=req.name,
                        quantity=float(req.quantity or 1),
                        unit_price_minor=None,
                        line_total_minor=None,
                        promotion=None,
                        alternatives=[],
                        ingredient_names=[req.name],
                    )
                )
                continue
            product = match.product
            packs = packs_needed(req, product)
            line_total = None
            if product.price_minor is not None:
                line_total = int(product.price_minor) * packs
                subtotal_minor += line_total
            else:
                unknown_count += 1
            alternatives = [candidate.product for candidate in rank_products(req, products)[1:4]]
            lines.append(
                ProposalLine(
                    position=position,
                    product_uid=product.product_uid,
                    name=product.name,
                    quantity=float(packs),
                    unit_price_minor=product.price_minor,
                    line_total_minor=line_total,
                    promotion=product.promotions[0] if product.promotions else None,
                    alternatives=alternatives,
                    ingredient_names=[req.name],
                )
            )
        key_input = f"{retailer}:{plan.id}:{','.join(req.normalized_name or req.name for req in requirements)}"
        proposal = Proposal(
            retailer=retailer,
            budget_minor=None if budget_gbp is None else round(budget_gbp * 100),
            subtotal_minor=subtotal_minor if subtotal_minor else None,
            total_minor=subtotal_minor if subtotal_minor else None,
            unknown_count=unknown_count,
            idempotency_key=hashlib.sha256(key_input.encode("utf-8")).hexdigest(),
            lines=lines,
        )
        proposal.id = self.db.proposals.create_proposal(proposal)
        return proposal
