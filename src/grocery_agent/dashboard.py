from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from .db import Database

app = FastAPI(title="Grocery Agent")

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def _db() -> Database:
    return Database(Path.home() / "Library" / "Application Support" / "grocery-agent" / "grocery.sqlite3")


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    db = _db()
    db.initialize()
    # Query recent orders directly
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT retailer, status, total_minor, ordered_at FROM orders ORDER BY imported_at DESC LIMIT 8"
        ).fetchall()
        recent_orders = [dict(r) for r in rows]
        order_count = conn.execute("SELECT COUNT(*) AS c FROM orders").fetchone()["c"]
        recipe_count = conn.execute("SELECT COUNT(*) AS c FROM recipes").fetchone()["c"]
        price_count = conn.execute("SELECT COUNT(*) AS c FROM price_observations").fetchone()["c"]
        retailer_count = conn.execute("SELECT COUNT(DISTINCT retailer) AS c FROM retailer_products").fetchone()["c"]

    # Biggest discounts: observations with promotion before > after
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT rp.name, rp.retailer, po.price_minor,
                   po.unit_price_minor, po.unit_measure,
                   po.in_stock, po.observed_at
            FROM price_observations po
            JOIN retailer_products rp ON rp.id = po.retailer_product_id
            WHERE po.observed_at >= datetime('now', '-7 days')
            ORDER BY po.observed_at DESC
            LIMIT 10
            """
        ).fetchall()
        big_discounts = [
            {
                "name": r["name"],
                "retailer": r["retailer"],
                "before": None,
                "after": r["price_minor"],
                "saving": None,
            }
            for r in rows
        ]

    with db.connect() as conn:
        rows = conn.execute(
            "SELECT title, servings, prep_minutes, cook_minutes, confidence, source_json FROM recipes LIMIT 8"
        ).fetchall()
        common_recipes = [
            {
                "title": r["title"],
                "servings": r["servings"],
                "prep_minutes": r["prep_minutes"],
                "cook_minutes": r["cook_minutes"],
                "confidence": r["confidence"],
                "source": {},
            }
            for r in rows
        ]

    return templates.TemplateResponse(
        "home.html",
        {
            "request": request,
            "orders_count": order_count,
            "recipes_count": recipe_count,
            "price_observations_count": price_count,
            "retailers_count": retailer_count,
            "recent_orders": recent_orders,
            "big_discounts": big_discounts,
            "common_recipes": common_recipes,
        },
    )


@app.get("/orders", response_class=HTMLResponse)
async def orders_page(request: Request):
    db = _db()
    db.initialize()
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT retailer, status, total_minor, ordered_at FROM orders ORDER BY imported_at DESC LIMIT 50"
        ).fetchall()
        orders = [dict(r) for r in rows]
    return templates.TemplateResponse("orders.html", {"request": request, "orders": orders})


@app.get("/recipes", response_class=HTMLResponse)
async def recipes_page(request: Request):
    db = _db()
    db.initialize()
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT title, servings, prep_minutes, cook_minutes, "
            "confidence, source_json FROM recipes ORDER BY title LIMIT 100"
        ).fetchall()
        recipes = [dict(r) for r in rows]
    return templates.TemplateResponse("recipes.html", {"request": request, "recipes": recipes})


@app.get("/prices", response_class=HTMLResponse)
async def prices_page(request: Request):
    db = _db()
    db.initialize()
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT rp.name, rp.retailer, po.price_minor,
                   po.unit_price_minor, po.unit_measure,
                   po.in_stock, po.observed_at
            FROM price_observations po
            JOIN retailer_products rp ON rp.id = po.retailer_product_id
            ORDER BY po.observed_at DESC LIMIT 100
            """
        ).fetchall()
        prices = [dict(r) for r in rows]
    return templates.TemplateResponse("prices.html", {"request": request, "prices": prices})


def main():
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8787)
