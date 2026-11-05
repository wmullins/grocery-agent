from __future__ import annotations

from ..models import MealPlan, MealPlanItem


class PlanStore:
    def __init__(self, connect) -> None:
        self._connect = connect

    def create_meal_plan(self, plan: MealPlan) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO meal_plans(start_date, days, servings, status, created_at) VALUES (?, ?, ?, ?, ?)",
                (plan.start_date, plan.days, plan.servings, plan.status, plan.created_at),
            )
            plan_id = int(cursor.lastrowid or 0)
            for item in plan.items:
                connection.execute(
                    "INSERT INTO meal_plan_items(meal_plan_id, day_index, meal_type, title,"
                    " recipe_id, servings) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        plan_id,
                        item.day_index,
                        item.meal_type,
                        item.title,
                        item.recipe_id,
                        item.servings,
                    ),
                )
            return plan_id

    def get_meal_plan(self, plan_id: int) -> MealPlan | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM meal_plans WHERE id = ?", (plan_id,)).fetchone()
            if row is None:
                return None
            items = connection.execute(
                "SELECT * FROM meal_plan_items WHERE meal_plan_id = ? ORDER BY day_index",
                (plan_id,),
            ).fetchall()
        return MealPlan(
            id=int(row["id"]),
            start_date=str(row["start_date"]),
            days=int(row["days"]),
            servings=int(row["servings"]),
            status=str(row["status"]),
            created_at=str(row["created_at"]),
            items=[
                MealPlanItem(
                    day_index=int(item["day_index"]),
                    meal_type=str(item["meal_type"]),
                    title=str(item["title"]),
                    recipe_id=item["recipe_id"],
                    servings=int(item["servings"]),
                )
                for item in items
            ],
        )
