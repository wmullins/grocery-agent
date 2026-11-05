from __future__ import annotations

import json
import subprocess

import pytest
from typer.testing import CliRunner

from grocery_agent.cli import app
from grocery_agent.config import database_file, default_config, load_config, save_config
from grocery_agent.db import Database
from grocery_agent.llm import OllamaClient
from grocery_agent.matching import packs_needed, score_match
from grocery_agent.models import (
    Basket,
    BasketItem,
    Product,
    Proposal,
    ProposalLine,
)
from grocery_agent.obsidian import Vault
from grocery_agent.proposals import ProposalManager
from grocery_agent.recipes import (
    Ingredient,
    extract_recipe_deterministic,
    ingredient_requirements,
    normalize_ingredient_name,
)
from grocery_agent.retail.adapter import (
    AuthRequired,
    RetailAdapter,
    RetailCommandError,
    parse_basket,
    parse_order,
    parse_product,
    parse_slot,
    price_to_minor,
)
from grocery_agent.safety import SafetyError


@pytest.fixture
def home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("GROCERY_AGENT_HOME", str(home))
    return home


@pytest.fixture
def config(home):
    cfg = default_config()
    cfg.paths.vault = home / "vault"
    save_config(cfg)
    return cfg


@pytest.fixture
def db(home):
    database = Database(database_file(home))
    database.initialize()
    return database


class FakeRunner:
    def __init__(self, responses: dict[str, str]) -> None:
        self.responses = responses
        self.interactive_calls: list[list[str]] = []

    def run(
        self,
        args: list[str],
        *,
        input_text: str | None = None,
        timeout: int = 90,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        joined = " ".join(args)
        for key, value in self.responses.items():
            if key == joined or joined.endswith(key):
                return subprocess.CompletedProcess(args, 0, value, "")
        raise RetailCommandError(f"no fixture for {joined}")

    def run_interactive(self, args: list[str], *, timeout: int = 300) -> int:
        self.interactive_calls.append(args)
        return 0


def test_config_save_load_permissions(home):
    cfg = default_config()
    cfg.paths.vault = home / "vault"
    path = save_config(cfg)
    loaded = load_config()
    assert loaded.agent.budget_gbp == cfg.agent.budget_gbp
    assert oct(path.stat().st_mode & 0o777) == "0o600"
    assert oct(path.parent.stat().st_mode & 0o777) == "0o700"


def test_db_note_sync_and_search(db, tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    note = vault / "recipe.md"
    note.write_text(
        "---\ntitle: Pasta\n---\n\n## Ingredients\n- 200g pasta\n- 1 tbsp olive oil\n\nBoil pasta.\n",
        encoding="utf-8",
    )
    indexer = Vault(vault, "10 Projects/Grocery Agent")
    stats = indexer.sync(db)
    assert stats["indexed"] == 1
    results = db.notes.search_notes("pasta", limit=5)
    assert len(results) == 1
    assert results[0]["title"] == "Pasta"


def test_recipe_extraction_deterministic():
    draft = extract_recipe_deterministic("Pasta", "## Ingredients\n- 200g pasta\n- 1 tbsp olive oil\n- Salt to taste\n")
    assert draft is not None
    assert draft.title == "Pasta"
    names = [ingredient.name for ingredient in draft.ingredients]
    assert "pasta" in names
    assert "olive oil" in names


def test_ingredient_requirements_scale():
    recipe = {
        "servings": 2,
        "ingredients": [
            {
                "name": "pasta",
                "normalized_name": "pasta",
                "quantity": 200,
                "unit": "g",
                "optional": False,
            },
            {
                "name": "olive oil",
                "normalized_name": "olive oil",
                "quantity": 1,
                "unit": "tbsp",
                "optional": False,
            },
        ],
    }
    requirements = ingredient_requirements(recipe, servings=4)
    assert len(requirements) == 2
    assert requirements[0].quantity == 400
    assert requirements[0].unit == "g"


def test_normalize_ingredient_name():
    assert normalize_ingredient_name("Fresh Pasta, chopped") == "pasta"


def test_score_match():
    ingredient = Ingredient(name="pasta", normalized_name="pasta", quantity=200, unit="g")
    product = Product(
        product_uid="p1",
        name="Pasta 500g",
        price_minor=150,
        unit_price_minor=30,
        unit_measure="g",
        in_stock=True,
        provider="sainsburys",
        size="500g",
    )
    score = score_match(ingredient, product)
    assert score >= 0.5


def test_packs_needed():
    ingredient = Ingredient(name="pasta", quantity=600, unit="g")
    product = Product(product_uid="p1", name="Pasta 500g", size="500g", unit_measure="g", provider="s")
    assert packs_needed(ingredient, product) == 2


def test_price_to_minor():
    assert price_to_minor("£1.50") == 150
    assert price_to_minor(1.5) == 150
    assert price_to_minor(None) is None
    assert price_to_minor("unknown") is None


def test_parse_product():
    raw = {
        "product_uid": "p1",
        "name": "Milk",
        "retail_price": {"price": 1.20},
        "unit_price": {"price": 1.06, "measure": "1.136L"},
        "in_stock": True,
        "provider": "sainsburys",
    }
    product = parse_product(raw, "sainsburys")
    assert product.product_uid == "p1"
    assert product.price_minor == 120
    assert product.unit_price_minor == 106
    assert product.in_stock is True


def test_parse_basket():
    raw = {
        "provider": "sainsburys",
        "items": [
            {
                "item_id": "i1",
                "product_uid": "p1",
                "name": "Milk",
                "quantity": 2,
                "unit_price": {"price": 1.20},
                "total_price": 2.40,
            }
        ],
        "total_cost": 2.40,
        "item_count": 1,
    }
    basket = parse_basket(raw, "sainsburys")
    assert basket.total_minor == 240
    assert basket.items[0].line_total_minor == 240


def test_parse_slot():
    slot_payload = {
        "slot_id": "s1",
        "date": "2026-11-06",
        "start_time": "10:00",
        "end_time": "12:00",
        "price": 3.00,
        "available": True,
    }
    slot = parse_slot(slot_payload)
    assert slot.slot_id == "s1"
    assert slot.available is True


def test_parse_order():
    raw = {
        "order_id": "o1",
        "status": "delivered",
        "total": "40.00",
        "items": [
            {
                "name": "Milk",
                "quantity": 2,
                "unit_price": "1.20",
                "line_total": "2.40",
            }
        ],
    }
    order = parse_order(raw)
    assert order.order_id == "o1"
    assert order.total_minor == 4000
    assert order.items[0].name == "Milk"


def test_adapter_search_and_batch(monkeypatch):
    search_payload = {
        "products": [
            {
                "product_uid": "p1",
                "name": "Pasta",
                "retail_price": {"price": 1.50},
                "in_stock": True,
                "provider": "sainsburys",
            }
        ]
    }
    batch_payload = {
        "results": [
            {
                "query": "pasta",
                "products": [{"id": "p1", "name": "Pasta", "price": 1.50, "inStock": True}],
            }
        ]
    }
    basket_payload = {"provider": "sainsburys", "items": [], "total_cost": 0, "item_count": 0}
    responses = {
        "supermarket --provider sainsburys search pasta --limit 5 --json": json.dumps(search_payload),
        "supermarket --provider sainsburys search --batch - --limit 5 --json": json.dumps(batch_payload),
        "supermarket --provider sainsburys basket --json": json.dumps(basket_payload),
    }
    runner = FakeRunner(responses)
    adapter = RetailAdapter(default_config().retail, runner=runner)
    products = adapter.search("sainsburys", "pasta", limit=5)
    assert len(products) == 1
    assert products[0].name == "Pasta"
    batched = adapter.search_batch("sainsburys", ["pasta"], limit=5)
    assert batched["pasta"][0].name == "Pasta"
    basket = adapter.basket("sainsburys")
    assert basket.total_minor == 0


def test_adapter_add_batch_passes_input():
    captured = {}

    class InputRunner(FakeRunner):
        def run(self, args, *, input_text=None, timeout=90, check=True):
            captured["input"] = input_text
            payload = {"provider": "sainsburys", "added": 1, "results": []}
            return subprocess.CompletedProcess(args, 0, json.dumps(payload), "")

    runner = InputRunner({"supermarket --provider sainsburys add --batch -": ""})
    adapter = RetailAdapter(default_config().retail, runner=runner)
    result = adapter.add_batch("sainsburys", [{"id": "p1", "qty": 2}])
    assert result["added"] == 1
    assert json.loads(captured["input"]) == [{"id": "p1", "qty": 2}]


def test_adapter_no_checkout_or_booking(config):
    adapter = RetailAdapter(config.retail)
    assert not hasattr(adapter, "checkout")
    assert not hasattr(adapter, "book_slot")
    assert not hasattr(adapter, "book")


def test_adapter_auth_required():
    responses = {"supermarket --provider sainsburys status --json": ""}

    class ErrorRunner(FakeRunner):
        def run(self, args, *, input_text=None, timeout=90, check=True):
            raise AuthRequired("need login")

    adapter = RetailAdapter(default_config().retail, runner=ErrorRunner(responses))
    status = adapter.status("sainsburys")
    assert status["authenticated"] is False


def test_proposal_approve_and_apply(db):
    proposal_id = db.proposals.create_proposal(
        Proposal(
            retailer="sainsburys",
            subtotal_minor=1000,
            total_minor=1000,
            idempotency_key="test-key",
            lines=[
                ProposalLine(
                    position=1,
                    product_uid="p1",
                    name="Pasta",
                    quantity=1,
                    unit_price_minor=1000,
                    line_total_minor=1000,
                )
            ],
        )
    )
    manager = ProposalManager(db)
    approved = manager.approve(proposal_id, note="ok")
    assert approved.status == "approved"

    class AddRunner:
        def run(self, args, *, input_text=None, timeout=90, check=True):
            payload = {"provider": "sainsburys", "added": 1, "results": []}
            return subprocess.CompletedProcess(args, 0, json.dumps(payload), "")

        def run_interactive(self, args, *, timeout=300):
            return 0

    from grocery_agent.retail.adapter import RetailAdapter as RA

    adapter = RA(default_config().retail, runner=AddRunner())

    def fake_basket(retailer):
        return Basket(
            provider=retailer,
            items=[
                BasketItem(
                    item_id="b1",
                    product_uid="p1",
                    name="Pasta",
                    quantity=1,
                    unit_price_minor=1000,
                    line_total_minor=1000,
                )
            ],
            total_minor=1000,
            item_count=1,
        )

    adapter.basket = fake_basket  # type: ignore[method-assign]
    applied = manager.apply(proposal_id, adapter)
    assert applied.status == "applied"


def test_vault_write_refuses_non_agent(tmp_path, db):
    vault = tmp_path / "vault"
    vault.mkdir()
    output = vault / "10 Projects/Grocery Agent"
    output.mkdir(parents=True)
    (output / "Shopping Lists").mkdir(parents=True, exist_ok=True)
    (output / "Shopping Lists" / "test.md").write_text("not agent\n", encoding="utf-8")
    indexer = Vault(vault, "10 Projects/Grocery Agent")
    with pytest.raises(SafetyError):
        indexer.write_agent_note("Shopping Lists/test.md", "new content\n")


def test_cli_init_and_config_show(tmp_path, monkeypatch):
    runner = CliRunner()
    monkeypatch.setenv("GROCERY_AGENT_HOME", str(tmp_path / "home"))
    init_args = [
        "init",
        "--postcode",
        "E1 1AA",
        "--budget-gbp",
        "50",
        "--retailers",
        "sainsburys",
        "--force",
    ]
    result = runner.invoke(app, init_args)
    assert result.exit_code == 0, result.output
    result = runner.invoke(app, ["config-show"])
    assert result.exit_code == 0, result.output
    assert "[set]" in result.output


def test_ollama_available_flag_is_bool():
    assert isinstance(OllamaClient(default_config().llm).available(), bool)
