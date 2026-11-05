from __future__ import annotations

from typing import Literal

from ..models import Product, Promotion, Proposal, ProposalLine, utc_now
from .schema import _json, _loads


class ProposalStore:
    def __init__(self, connect) -> None:
        self._connect = connect

    def create_proposal(self, proposal: Proposal) -> int:
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT id FROM proposals WHERE idempotency_key = ?",
                (proposal.idempotency_key,),
            ).fetchone()
            if existing:
                return int(existing["id"])
            cursor = connection.execute(
                "INSERT INTO proposals(retailer, status, budget_minor, subtotal_minor,"
                " delivery_minor, total_minor, created_at, idempotency_key)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    proposal.retailer,
                    proposal.status,
                    proposal.budget_minor,
                    proposal.subtotal_minor,
                    proposal.delivery_minor,
                    proposal.total_minor,
                    proposal.created_at,
                    proposal.idempotency_key,
                ),
            )
            proposal_id = int(cursor.lastrowid or 0)
            for line in proposal.lines:
                connection.execute(
                    "INSERT INTO proposal_lines(proposal_id, position, product_uid, name,"
                    " quantity, unit_price_minor, line_total_minor, promotion_json,"
                    " alternatives_json, ingredient_names_json)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        proposal_id,
                        line.position,
                        line.product_uid,
                        line.name,
                        line.quantity,
                        line.unit_price_minor,
                        line.line_total_minor,
                        _json(line.promotion.model_dump()) if line.promotion else None,
                        _json([item.model_dump() for item in line.alternatives]),
                        _json(line.ingredient_names),
                    ),
                )
            return proposal_id

    def get_proposal(self, proposal_id: int) -> Proposal | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,)).fetchone()
            if row is None:
                return None
            lines = connection.execute(
                "SELECT * FROM proposal_lines WHERE proposal_id = ? ORDER BY position",
                (proposal_id,),
            ).fetchall()
        return Proposal(
            id=int(row["id"]),
            retailer=str(row["retailer"]),
            status=str(row["status"]),
            budget_minor=row["budget_minor"],
            subtotal_minor=row["subtotal_minor"],
            delivery_minor=row["delivery_minor"],
            total_minor=row["total_minor"],
            created_at=str(row["created_at"]),
            approved_at=row["approved_at"],
            applied_at=row["applied_at"],
            idempotency_key=str(row["idempotency_key"]),
            lines=[
                ProposalLine(
                    position=int(line["position"]),
                    product_uid=str(line["product_uid"]),
                    name=str(line["name"]),
                    quantity=float(line["quantity"]),
                    unit_price_minor=line["unit_price_minor"],
                    line_total_minor=line["line_total_minor"],
                    promotion=(
                        Promotion.model_validate(_loads(line["promotion_json"], {})) if line["promotion_json"] else None
                    ),
                    alternatives=[Product.model_validate(item) for item in _loads(line["alternatives_json"], [])],
                    ingredient_names=_loads(line["ingredient_names_json"], []),
                )
                for line in lines
            ],
        )

    def set_proposal_status(
        self,
        proposal_id: int,
        status: Literal["draft", "approved", "applied", "failed", "rejected"],
        *,
        note: str = "",
    ) -> None:
        now = utc_now()
        with self._connect() as connection:
            if status == "approved":
                connection.execute(
                    "UPDATE proposals SET status = ?, approved_at = ? WHERE id = ?",
                    (status, now, proposal_id),
                )
            elif status == "applied":
                connection.execute(
                    "UPDATE proposals SET status = ?, applied_at = ? WHERE id = ?",
                    (status, now, proposal_id),
                )
            else:
                connection.execute("UPDATE proposals SET status = ? WHERE id = ?", (status, proposal_id))
            connection.execute(
                "INSERT INTO approvals(proposal_id, decision, note, decided_at) VALUES (?, ?, ?, ?)",
                (proposal_id, status, note, now),
            )
