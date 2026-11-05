from __future__ import annotations

from .db import Database
from .models import Basket, Proposal
from .retail.adapter import RetailAdapter


class ProposalManager:
    def __init__(self, db: Database) -> None:
        self.db = db

    def show(self, proposal_id: int) -> Proposal | None:
        return self.db.proposals.get_proposal(proposal_id)

    def approve(self, proposal_id: int, note: str = "") -> Proposal | None:
        proposal = self.db.proposals.get_proposal(proposal_id)
        if proposal is None:
            return None
        if proposal.status not in {"draft", "rejected", "failed"}:
            return proposal
        self.db.proposals.set_proposal_status(proposal_id, "approved", note=note)
        self.db.audit.audit("proposal_approved", "proposal", str(proposal_id), {"note": note})
        return self.db.proposals.get_proposal(proposal_id)

    def apply(self, proposal_id: int, adapter: RetailAdapter) -> Proposal | None:
        proposal = self.db.proposals.get_proposal(proposal_id)
        if proposal is None:
            return None
        if proposal.status != "approved":
            return proposal
        items = []
        for line in proposal.lines:
            quantity = line.quantity
            if isinstance(quantity, float) and quantity.is_integer():
                quantity = int(quantity)
            items.append({"id": line.product_uid, "qty": quantity})
        try:
            result = adapter.add_batch(proposal.retailer, items)
            basket = adapter.basket(proposal.retailer)
        except Exception as exc:
            self.db.proposals.set_proposal_status(proposal_id, "failed", note=str(exc))
            self.db.audit.audit("proposal_apply_failed", "proposal", str(proposal_id), {"error": str(exc)})
            return self.db.proposals.get_proposal(proposal_id)
        missing = self._missing_items(proposal, basket)
        if missing:
            self.db.proposals.set_proposal_status(proposal_id, "failed", note="missing items: " + ", ".join(missing))
            self.db.audit.audit("proposal_apply_incomplete", "proposal", str(proposal_id), {"missing": missing})
            return self.db.proposals.get_proposal(proposal_id)
        self.db.proposals.set_proposal_status(proposal_id, "applied", note="basket updated via open-supermarkets")
        self.db.audit.audit("proposal_applied", "proposal", str(proposal_id), {"adapter_result": result})
        return self.db.proposals.get_proposal(proposal_id)

    def _missing_items(self, proposal: Proposal, basket: Basket) -> list[str]:
        missing: list[str] = []
        for line in proposal.lines:
            found = any(
                str(item.product_uid) == line.product_uid or item.name.lower() == line.name.lower()
                for item in basket.items
            )
            if not found:
                missing.append(line.name)
        return missing
