from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


class Promotion(BaseModel):
    kind: str = "offer"
    description: str = ""
    before_minor: int | None = None
    after_minor: int | None = None
    requires_loyalty: bool = False
    loyalty_programme: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class Product(BaseModel):
    product_uid: str
    name: str
    price_minor: int | None = None
    currency: str = "GBP"
    unit_price_minor: int | None = None
    unit_measure: str | None = None
    in_stock: bool | None = None
    image_url: str | None = None
    size: str | None = None
    gtin: str | None = None
    provider: str = ""
    rating: float | None = None
    review_count: int | None = None
    promotions: list[Promotion] = Field(default_factory=list)


class Ingredient(BaseModel):
    name: str
    normalized_name: str = ""
    quantity: float | None = None
    unit: str | None = None
    optional: bool = False
    note: str | None = None


class RecipeDraft(BaseModel):
    title: str
    servings: int | None = None
    prep_minutes: int | None = None
    cook_minutes: int | None = None
    ingredients: list[Ingredient] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    confidence: float = 0.5
    source: dict[str, Any] = Field(default_factory=dict)


class Candidate(BaseModel):
    product: Product
    score: float
    reason: str = ""


class BasketItem(BaseModel):
    item_id: str
    product_uid: str
    name: str
    quantity: float
    unit_price_minor: int | None = None
    line_total_minor: int | None = None
    promotion: Promotion | None = None


class Basket(BaseModel):
    provider: str = ""
    items: list[BasketItem] = Field(default_factory=list)
    total_minor: int | None = None
    item_count: int | None = None
    currency: str = "GBP"


class DeliverySlot(BaseModel):
    slot_id: str
    date: str
    start_time: str
    end_time: str
    price_minor: int | None = None
    available: bool = True


class OrderLine(BaseModel):
    retailer_product_id: str | None = None
    name: str
    quantity: float = 1
    unit_price_minor: int | None = None
    line_total_minor: int | None = None
    promotion: dict[str, Any] | None = None


class Order(BaseModel):
    order_id: str
    status: str = ""
    total_minor: int | None = None
    delivery_slot: dict[str, Any] | None = None
    items: list[OrderLine] = Field(default_factory=list)


class ProposalLine(BaseModel):
    position: int
    product_uid: str
    name: str
    quantity: float
    unit_price_minor: int | None = None
    line_total_minor: int | None = None
    promotion: Promotion | None = None
    alternatives: list[Product] = Field(default_factory=list)
    ingredient_names: list[str] = Field(default_factory=list)


class Proposal(BaseModel):
    id: int | None = None
    retailer: str
    status: str = "draft"
    budget_minor: int | None = None
    subtotal_minor: int | None = None
    delivery_minor: int | None = None
    total_minor: int | None = None
    unknown_count: int = 0
    created_at: str = Field(default_factory=utc_now)
    approved_at: str | None = None
    applied_at: str | None = None
    idempotency_key: str = ""
    lines: list[ProposalLine] = Field(default_factory=list)


class MealPlanItem(BaseModel):
    day_index: int
    meal_type: str = "dinner"
    title: str
    recipe_id: int | None = None
    servings: int = 2


class MealPlan(BaseModel):
    id: int | None = None
    start_date: str
    days: int
    servings: int
    status: str = "draft"
    items: list[MealPlanItem] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now)


class Preference(BaseModel):
    key: str
    value: Any
    confidence: float = 0.5
    source: str = "explicit"
    evidence: str = ""
