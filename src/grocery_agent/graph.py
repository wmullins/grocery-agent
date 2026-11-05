from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from .config import Config
from .db import Database
from .models import MealPlan
from .planning import MealPlanner
from .retail.adapter import RetailAdapter


class ShopState(TypedDict, total=False):
    plan_id: int
    plan: dict[str, Any] | None
    requirements: list[dict[str, Any]]
    search_results: dict[str, Any]
    proposals: list[dict[str, Any]]
    selected: dict[str, Any] | None
    errors: list[str]


def build_shopping_graph(db: Database, adapter: RetailAdapter, config: Config):
    retailers = config.agent.retailers or ["sainsburys"]
    default_retailer = retailers[0]

    def load_plan(state: ShopState) -> ShopState:
        plan_id = state.get("plan_id")
        if plan_id is None:
            state["errors"] = [*state.get("errors", []), "plan_id is required"]
            return state
        plan = db.plans.get_meal_plan(int(plan_id))
        state["plan"] = plan.model_dump() if plan else None
        if plan is None:
            state["errors"] = [*state.get("errors", []), f"Plan {plan_id} not found"]
        return state

    def aggregate(state: ShopState) -> ShopState:
        plan_data = state.get("plan")
        if not plan_data:
            return state
        plan = MealPlan.model_validate(plan_data)
        planner = MealPlanner(db, retailer=default_retailer)
        requirements = planner.aggregate_ingredients(plan)
        state["requirements"] = [
            {
                "name": item.name,
                "normalized_name": item.normalized_name,
                "quantity": item.quantity,
                "unit": item.unit,
                "optional": item.optional,
            }
            for item in requirements
        ]
        return state

    def search_retailers(state: ShopState) -> ShopState:
        requirements = state.get("requirements", [])
        if not requirements:
            return state
        queries = [item["name"] for item in requirements]
        found: dict[str, Any] = {}
        for retailer in retailers:
            try:
                products = adapter.search_batch(retailer, queries, limit=5)
                found[retailer] = {
                    query: [product.model_dump() for product in product_list]
                    for query, product_list in products.items()
                }
            except Exception as exc:
                state.setdefault("errors", []).append(f"{retailer}: {exc}")
        state["search_results"] = found
        return state

    def propose(state: ShopState) -> ShopState:
        plan_data = state.get("plan")
        if not plan_data:
            return state
        plan = MealPlan.model_validate(plan_data)
        planner = MealPlanner(db, retailer=default_retailer)
        proposals: list[dict[str, Any]] = []
        for retailer in retailers:
            try:
                proposal = planner.propose(plan, retailer, adapter, budget_gbp=config.agent.budget_gbp)
                proposals.append(proposal.model_dump())
            except Exception as exc:
                state.setdefault("errors", []).append(f"propose {retailer}: {exc}")
        state["proposals"] = proposals
        return state

    def select(state: ShopState) -> ShopState:
        proposals = state.get("proposals", [])
        if not proposals:
            return state

        def sort_key(item: dict[str, Any]) -> tuple[int, int, int]:
            total = item.get("total_minor") or 0
            unknown = item.get("unknown_count") or 0
            return (0 if total else 1, unknown, -total)

        state["selected"] = min(proposals, key=sort_key)
        return state

    graph = StateGraph(ShopState)
    graph.add_node("load_plan", load_plan)
    graph.add_node("aggregate", aggregate)
    graph.add_node("search_retailers", search_retailers)
    graph.add_node("propose", propose)
    graph.add_node("select", select)
    graph.add_edge(START, "load_plan")
    graph.add_edge("load_plan", "aggregate")
    graph.add_edge("aggregate", "search_retailers")
    graph.add_edge("search_retailers", "propose")
    graph.add_edge("propose", "select")
    graph.add_edge("select", END)
    return graph.compile()
