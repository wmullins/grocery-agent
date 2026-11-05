from __future__ import annotations

from ..models import Order, utc_now
from .schema import _json


class OrderStore:
    def __init__(self, connect) -> None:
        self._connect = connect

    def save_order(self, retailer: str, order_ref_hash: str, order: Order, source: str) -> int:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO orders(retailer, order_ref_hash, status, total_minor, source, imported_at)"
                " VALUES (?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(retailer, order_ref_hash) DO UPDATE SET"
                " status=excluded.status, total_minor=excluded.total_minor,"
                " imported_at=excluded.imported_at",
                (retailer, order_ref_hash, order.status, order.total_minor, source, utc_now()),
            )
            row = connection.execute(
                "SELECT id FROM orders WHERE retailer = ? AND order_ref_hash = ?",
                (retailer, order_ref_hash),
            ).fetchone()
            if row is None:
                raise RuntimeError("Failed to persist order")
            order_id = int(row["id"])
            connection.execute("DELETE FROM order_lines WHERE order_id = ?", (order_id,))
            for line in order.items:
                connection.execute(
                    "INSERT INTO order_lines(order_id, retailer_product_id, name, quantity,"
                    " unit_price_minor, line_total_minor, promotion_json)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        order_id,
                        line.retailer_product_id,
                        line.name,
                        line.quantity,
                        line.unit_price_minor,
                        line.line_total_minor,
                        _json(line.promotion) if line.promotion else None,
                    ),
                )
            return order_id
