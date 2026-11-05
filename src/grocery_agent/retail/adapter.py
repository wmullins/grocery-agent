from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Protocol

from ..config import RetailSettings
from ..models import (
    Basket,
    BasketItem,
    DeliverySlot,
    Order,
    OrderLine,
    Product,
    Promotion,
)
from ..safety import ensure_private_dir, redact
from .errors import (
    AuthRequired,
    RetailCommandError,
    RetailError,
    RetailUnavailable,
    UnsupportedRetailer,
)

AUTH_PATTERN = re.compile(
    r"auth|login|session|unauthori[sz]ed|forbidden|401|403|expired|cookie",
    re.IGNORECASE,
)
BLOCK_PATTERN = re.compile(
    r"waf|bot|captcha|access denied|blocked|challenge|akamai",
    re.IGNORECASE,
)
CREDENTIAL_ENV = {
    "SAINSBURYS_EMAIL",
    "SAINSBURYS_PASSWORD",
    "SUPERMARKET_EMAIL",
    "SUPERMARKET_PASSWORD",
    "GROC_EMAIL",
    "GROC_PASSWORD",
}


class Runner(Protocol):
    def run(
        self,
        args: list[str],
        *,
        input_text: str | None = None,
        timeout: int = 90,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]: ...

    def run_interactive(self, args: list[str], *, timeout: int = 300) -> int: ...


class SubprocessRunner:
    def _env(self) -> dict[str, str]:
        env = os.environ.copy()
        for key in CREDENTIAL_ENV:
            env.pop(key, None)
        env["NO_COLOR"] = "1"
        env["FORCE_COLOR"] = "0"
        return env

    def run(
        self,
        args: list[str],
        *,
        input_text: str | None = None,
        timeout: int = 90,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            args,
            input=input_text,
            text=True,
            capture_output=True,
            timeout=timeout,
            env=self._env(),
            check=False,
        )
        if check and result.returncode != 0:
            raise RetailCommandError(
                redact(result.stderr.strip() or result.stdout.strip() or "retail command failed"),
                stderr=result.stderr,
                returncode=result.returncode,
            )
        return result

    def run_interactive(self, args: list[str], *, timeout: int = 300) -> int:
        result = subprocess.run(args, timeout=timeout, env=self._env(), check=False)
        return result.returncode


def _coerce_dict(data: Any) -> dict[str, Any]:
    return data if isinstance(data, dict) else {}


def price_to_minor(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return round(float(value) * 100)
    if isinstance(value, str):
        cleaned = value.strip().replace("£", "").replace(",", "")
        if not cleaned or cleaned.lower() in {"unknown", "n/a", "none", "null"}:
            return None
        try:
            return round(float(cleaned) * 100)
        except ValueError:
            return None
    return None


def _parse_unit_price(value: Any) -> tuple[int | None, str | None]:
    if isinstance(value, dict):
        return price_to_minor(value.get("price")), value.get("measure")
    if isinstance(value, str):
        match = re.search(r"([\d.]+)\s*/\s*(.+)", value.replace("£", ""))
        if match:
            return price_to_minor(match.group(1)), match.group(2).strip()
    return None, None


def _loyalty(description: str) -> tuple[bool, str | None]:
    lowered = description.lower()
    for name in ("clubcard", "nectar", "more card", "membership"):
        if name in lowered:
            return True, name
    if "member" in lowered:
        return True, "member"
    return False, None


def parse_promotion(raw: dict[str, Any]) -> Promotion:
    description = str(raw.get("description") or raw.get("name") or "")
    before = price_to_minor(raw.get("before") or raw.get("beforeDiscount"))
    after = price_to_minor(raw.get("after") or raw.get("afterDiscount"))
    if isinstance(raw.get("price"), dict):
        before = price_to_minor(raw["price"].get("beforeDiscount") or raw["price"].get("before") or before)
        after = price_to_minor(raw["price"].get("afterDiscount") or raw["price"].get("after") or after)
    requires_loyalty, programme = _loyalty(description)
    return Promotion(
        kind=str(raw.get("kind") or "offer"),
        description=description,
        before_minor=before,
        after_minor=after,
        requires_loyalty=requires_loyalty,
        loyalty_programme=programme,
        raw=raw,
    )


def parse_product(raw: dict[str, Any], retailer: str) -> Product:
    uid = raw.get("product_uid") or raw.get("id") or raw.get("productId")
    if uid is None:
        raise RetailError("Product payload is missing a product id")
    retail_price = raw.get("retail_price")
    if isinstance(retail_price, dict):
        price = price_to_minor(retail_price.get("price"))
    else:
        price = price_to_minor(raw.get("price"))
    unit_price, unit_measure = _parse_unit_price(raw.get("unit_price") or raw.get("unitPrice") or raw.get("unit"))
    stock = raw.get("in_stock")
    if stock is None:
        stock = raw.get("inStock")
    promotions = [parse_promotion(item) for item in raw.get("promotions", []) if isinstance(item, dict)]
    size = raw.get("size")
    if isinstance(size, dict):
        size = size.get("value")
    return Product(
        product_uid=str(uid),
        name=str(raw.get("name") or "Unknown product"),
        price_minor=price,
        currency=str(raw.get("currency") or "GBP"),
        unit_price_minor=unit_price,
        unit_measure=str(unit_measure) if unit_measure else None,
        in_stock=stock if isinstance(stock, bool) else None,
        image_url=raw.get("image_url") or raw.get("imageUrl"),
        size=str(size) if size else None,
        gtin=raw.get("gtin"),
        provider=str(raw.get("provider") or retailer),
        rating=raw.get("rating"),
        review_count=raw.get("review_count") or raw.get("reviewCount"),
        promotions=promotions,
    )


def parse_basket(raw: dict[str, Any], retailer: str) -> Basket:
    items: list[BasketItem] = []
    raw_items = raw.get("items", [])
    if not isinstance(raw_items, list):
        raw_items = []
    for line in raw_items:
        if not isinstance(line, dict):
            continue
        product = line.get("product") if isinstance(line.get("product"), dict) else {}
        item_id = line.get("item_id") or line.get("itemId") or line.get("id")
        product_uid = line.get("product_uid") or product.get("product_uid") or item_id
        if item_id is None or product_uid is None:
            continue
        promotion = None
        if isinstance(line.get("promotion"), dict):
            promotion = parse_promotion(line["promotion"])
        items.append(
            BasketItem(
                item_id=str(item_id),
                product_uid=str(product_uid),
                name=str(line.get("name") or product.get("name") or "Unknown product"),
                quantity=float(line.get("quantity") or 0),
                unit_price_minor=price_to_minor(line.get("unit_price") or line.get("unitPrice")),
                line_total_minor=price_to_minor(
                    line.get("total_price") or line.get("line_total") or line.get("lineTotal")
                ),
                promotion=promotion,
            )
        )
    total = raw.get("total_cost")
    if total is None:
        total = raw.get("total_price") or raw.get("total")
    return Basket(
        provider=str(raw.get("provider") or retailer),
        items=items,
        total_minor=price_to_minor(total),
        item_count=raw.get("item_count") or raw.get("itemCount") or len(items),
        currency=str(raw.get("currency") or "GBP"),
    )


def parse_slot(raw: dict[str, Any]) -> DeliverySlot:
    slot_id = raw.get("slot_id") or raw.get("id")
    if slot_id is None:
        raise RetailError("Delivery slot is missing an id")
    return DeliverySlot(
        slot_id=str(slot_id),
        date=str(raw.get("date") or ""),
        start_time=str(raw.get("start_time") or raw.get("start") or ""),
        end_time=str(raw.get("end_time") or raw.get("end") or ""),
        price_minor=price_to_minor(raw.get("price")),
        available=bool(raw.get("available", True)),
    )


def parse_order(raw: dict[str, Any]) -> Order:
    order_id = raw.get("order_id") or raw.get("orderId")
    if order_id is None:
        raise RetailError("Order payload is missing an id")
    lines: list[OrderLine] = []
    raw_items = raw.get("items", [])
    if not isinstance(raw_items, list):
        raw_items = []
    for line in raw_items:
        if not isinstance(line, dict):
            continue
        product = line.get("product") if isinstance(line.get("product"), dict) else {}
        lines.append(
            OrderLine(
                retailer_product_id=str(line.get("product_uid") or product.get("product_uid") or "") or None,
                name=str(line.get("name") or product.get("name") or "Unknown product"),
                quantity=float(line.get("quantity") or 1),
                unit_price_minor=price_to_minor(line.get("unit_price") or line.get("unitPrice")),
                line_total_minor=price_to_minor(line.get("total_price") or line.get("line_total")),
                promotion=line.get("promotion") if isinstance(line.get("promotion"), dict) else None,
            )
        )
    return Order(
        order_id=str(order_id),
        status=str(raw.get("status") or ""),
        total_minor=price_to_minor(raw.get("total")),
        delivery_slot=raw.get("delivery_slot") if isinstance(raw.get("delivery_slot"), dict) else None,
        items=lines,
    )


class RetailAdapter:
    def __init__(
        self,
        settings: RetailSettings,
        *,
        runner: Runner | None = None,
        available_retailers: tuple[str, ...] = ("sainsburys", "tesco", "ocado"),
    ) -> None:
        self.settings = settings
        self.runner = runner or SubprocessRunner()
        self.available_retailers = available_retailers

    def _validate(self, retailer: str) -> None:
        if retailer not in self.available_retailers:
            raise UnsupportedRetailer(
                f"Retailer '{retailer}' is not supported. Choose from: " + ", ".join(self.available_retailers)
            )

    def binary(self) -> list[str] | None:
        candidate = self.settings.node_prefix / "node_modules" / ".bin" / "supermarket"
        if candidate.exists():
            return [str(candidate)]
        npm = shutil.which("npm")
        if npm:
            return [
                npm,
                "exec",
                "--yes",
                f"--package={self.settings.package}",
                "--",
                "supermarket",
            ]
        return None

    def require_binary(self) -> list[str]:
        binary = self.binary()
        if binary is None:
            raise RetailUnavailable("open-supermarkets is not installed and npm was not found. Run `grocery doctor`.")
        return binary

    def install(self) -> str:
        npm = shutil.which("npm")
        if npm is None:
            raise RetailUnavailable("npm is required to install open-supermarkets.")
        ensure_private_dir(self.settings.node_prefix)
        result = self.runner.run(
            [
                npm,
                "install",
                "--prefix",
                str(self.settings.node_prefix),
                "--no-fund",
                "--no-audit",
                self.settings.package,
            ],
            timeout=300,
        )
        return result.stdout.strip()

    def _base(self, retailer: str) -> list[str]:
        self._validate(retailer)
        return [*self.require_binary(), "--provider", retailer]

    def _json(self, args: list[str], *, input_text: str | None = None) -> dict[str, Any]:
        result = self.runner.run(
            args,
            input_text=input_text,
            timeout=self.settings.timeout_seconds,
            check=False,
        )
        if result.returncode != 0:
            message = (result.stderr or result.stdout or "retail command failed").strip()
            if AUTH_PATTERN.search(message):
                raise AuthRequired(
                    f"Authentication required. Run `grocery auth` for this retailer. ({redact(message)})"
                )
            if BLOCK_PATTERN.search(message):
                raise RetailUnavailable(f"Retailer blocked automated access; no bypass attempted. ({redact(message)})")
            raise RetailCommandError(redact(message), stderr=result.stderr, returncode=result.returncode)
        text = result.stdout.strip()
        if not text:
            return {}
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise RetailCommandError(f"Retail command returned non-JSON output: {redact(text[:300])}") from exc

    def status(self, retailer: str) -> dict[str, Any]:
        try:
            data = self._json([*self._base(retailer), "status", "--json"])
        except AuthRequired:
            return {"provider": retailer, "authenticated": False}
        return data if isinstance(data, dict) else {"provider": retailer}

    def search(self, retailer: str, query: str, *, limit: int = 10) -> list[Product]:
        data = _coerce_dict(self._json([*self._base(retailer), "search", query, "--limit", str(limit), "--json"]))
        products = data.get("products", [])
        return [parse_product(item, retailer) for item in products if isinstance(item, dict)]

    def search_batch(self, retailer: str, queries: list[str], *, limit: int = 5) -> dict[str, list[Product]]:
        payload = json.dumps(queries)
        data = self._json(
            [
                *self._base(retailer),
                "search",
                "--batch",
                "-",
                "--limit",
                str(limit),
                "--json",
            ],
            input_text=payload,
        )
        data = _coerce_dict(data)
        results: dict[str, list[Product]] = {}
        for item in data.get("results", []):
            if not isinstance(item, dict):
                continue
            query = str(item.get("query") or "")
            products = item.get("products", [])
            results[query] = [parse_product(product, retailer) for product in products if isinstance(product, dict)]
        return results

    def basket(self, retailer: str) -> Basket:
        data = _coerce_dict(self._json([*self._base(retailer), "basket", "--json"]))
        return parse_basket(data, retailer)

    def add_batch(self, retailer: str, items: list[dict[str, Any]]) -> dict[str, Any]:
        if not items:
            return {"provider": retailer, "added": 0, "results": []}
        data = self._json(
            [*self._base(retailer), "add", "--batch", "-"],
            input_text=json.dumps(items),
        )
        return data if isinstance(data, dict) else {"provider": retailer, "results": []}

    def remove(self, retailer: str, item_id: str) -> None:
        self._json([*self._base(retailer), "remove", item_id])

    def update(self, retailer: str, item_id: str, quantity: int) -> None:
        self._json([*self._base(retailer), "update", item_id, str(quantity)])

    def clear(self, retailer: str) -> None:
        self._json([*self._base(retailer), "clear"])

    def slots(self, retailer: str) -> list[DeliverySlot]:
        data = _coerce_dict(self._json([*self._base(retailer), "slots", "--json"]))
        slots = data.get("slots", [])
        return [parse_slot(item) for item in slots if isinstance(item, dict)]

    def orders(self, retailer: str, *, limit: int = 20) -> list[Order]:
        data = _coerce_dict(self._json([*self._base(retailer), "orders", "--json", "--limit", str(limit)]))
        orders = data.get("orders", [])
        return [parse_order(item) for item in orders if isinstance(item, dict)]

    def login(self, retailer: str) -> int:
        self._validate(retailer)
        args = [*self.require_binary(), "--provider", retailer, "login"]
        return self.runner.run_interactive(args, timeout=300)

    def import_session(self, retailer: str, cookie_file: Path) -> int:
        self._validate(retailer)
        args = [
            *self.require_binary(),
            "--provider",
            retailer,
            "import-session",
            "--file",
            str(cookie_file),
        ]
        return self.runner.run_interactive(args, timeout=120)

    def doctor(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "python": sys.version.split()[0],
            "node": shutil.which("node"),
            "npm": shutil.which("npm"),
            "binary": None,
            "package": self.settings.package,
            "retailers": {},
        }
        binary = self.binary()
        result["binary"] = binary[0] if binary else None
        for retailer in self.available_retailers:
            try:
                result["retailers"][retailer] = self.status(retailer)
            except (RetailError, RetailCommandError) as exc:
                result["retailers"][retailer] = {"error": redact(str(exc))}
        return result
