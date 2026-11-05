from __future__ import annotations

import csv
import hashlib
from pathlib import Path

from .db import Database
from .models import Order, OrderLine
from .retail.adapter import RetailAdapter


class OrderImporter:
    def __init__(self, db: Database, adapter: RetailAdapter) -> None:
        self.db = db
        self.adapter = adapter

    def import_orders(self, retailer: str, *, limit: int = 20) -> int:
        orders = self.adapter.orders(retailer, limit=limit)
        count = 0
        for order in orders:
            order_ref_hash = hashlib.sha256(f"{retailer}:{order.order_id}".encode()).hexdigest()
            self.db.orders.save_order(retailer, order_ref_hash, order, source="open-supermarkets")
            count += 1
        return count

    def import_csv(self, path: Path, retailer: str) -> int:
        count = 0
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                order_id = row.get("order_id") or row.get("order ref") or ""
                order_ref_hash = hashlib.sha256(
                    f"{retailer}:{order_id or row.get('date', '')}:{count}".encode()
                ).hexdigest()
                order = Order(
                    order_id=order_id or order_ref_hash[:12],
                    status=str(row.get("status") or "imported"),
                    total_minor=self._minor(row.get("total")),
                    items=[
                        OrderLine(
                            retailer_product_id=row.get("product_id") or "",
                            name=str(row.get("product") or ""),
                            quantity=float(row.get("quantity") or 1),
                            unit_price_minor=self._minor(row.get("unit_price")),
                            line_total_minor=self._minor(row.get("line_total") or row.get("total")),
                        )
                    ],
                )
                self.db.orders.save_order(retailer, order_ref_hash, order, source="csv")
                count += 1
        return count

    @staticmethod
    def _minor(value: str | None) -> int | None:
        if value is None:
            return None
        cleaned = str(value).replace("£", "").replace(",", "").strip()
        if not cleaned:
            return None
        try:
            return round(float(cleaned) * 100)
        except ValueError:
            return None
