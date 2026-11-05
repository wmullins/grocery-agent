from __future__ import annotations

import json
from pathlib import Path

import typer

from .config import (
    Config,
    ConfigError,
    app_home,
    config_file,
    database_file,
    default_config,
    ensure_runtime_dirs,
    load_config,
    save_config,
)
from .db import Database
from .history import OrderImporter
from .llm import OllamaClient
from .obsidian import Vault
from .output import (
    console,
    error,
    header,
    money,
    ok,
    price_table,
    proposal_table,
    section,
    spinner,
    status_panel,
)
from .planning import MealPlanner
from .proposals import ProposalManager
from .recipes import extract_recipes
from .retail.adapter import RetailAdapter
from .safety import AGENT_MARKER

app = typer.Typer(help="Grocery agent", no_args_is_help=True)


@app.callback()
def main() -> None:
    pass


def _load_config() -> Config:
    try:
        return load_config()
    except ConfigError as exc:
        error(str(exc))
        raise typer.Exit(code=1) from None


def _db() -> Database:
    return Database(database_file())


def _adapter(config: Config) -> RetailAdapter:
    return RetailAdapter(config.retail)


@app.command()
def init(
    postcode: str = typer.Option("", "--postcode", help="Delivery postcode"),
    budget_gbp: float = typer.Option(70.0, "--budget-gbp", help="Weekly budget in GBP"),
    household_size: int = typer.Option(2, "--household-size", help="People to cook for"),
    retailers: str = typer.Option("sainsburys,ocado", "--retailers", help="Comma separated retailer ids"),
    fulfilment: str = typer.Option("delivery", "--fulfilment", help="delivery or pickup"),
    vault: str = typer.Option("", "--vault", help="Obsidian vault path"),
    output_folder: str = typer.Option("10 Projects/Grocery Agent", "--output-folder"),
    force: bool = typer.Option(False, "--force", help="Overwrite existing config"),
    allergies: str = typer.Option("", "--allergies", help="Comma separated allergies"),
    dietary: str = typer.Option("", "--dietary", help="Comma separated dietary restrictions"),
) -> None:
    home = app_home()
    path = config_file(home)
    if path.exists() and not force:
        error(f"Config already exists at {path}. Use --force to overwrite.")
        raise typer.Exit(code=1)
    config = default_config()
    config.agent.postcode = postcode
    config.agent.budget_gbp = budget_gbp
    config.agent.household_size = household_size
    config.agent.fulfilment = fulfilment
    config.agent.allergies = [item.strip() for item in allergies.split(",") if item.strip()]
    config.agent.dietary_restrictions = [item.strip() for item in dietary.split(",") if item.strip()]
    config.agent.retailers = [item.strip() for item in retailers.split(",") if item.strip()]
    if vault:
        config.paths.vault = Path(vault)
    config.paths.output_folder = output_folder
    save_config(config)
    ensure_runtime_dirs(home)
    db = _db()
    db.initialize()
    vault_indexer = Vault(config.paths.vault, config.paths.output_folder)
    vault_indexer.ensure_agent_folder()
    with spinner("Indexing vault and extracting recipes"):
        sync_stats = vault_indexer.sync(db)
        recipe_stats = extract_recipes(
            vault_root=config.paths.vault,
            db=db,
            llm=OllamaClient(config.llm),
        )
    header("Initialized", str(home))
    ok(f"Vault notes indexed: {sync_stats['indexed']} new, {sync_stats['unchanged']} unchanged")
    ok(f"Recipes extracted: {recipe_stats['recipes']}")


@app.command()
def doctor() -> None:
    config = _load_config()
    adapter = _adapter(config)
    report = adapter.doctor()
    db = _db()
    try:
        db.initialize()
        note_count = db.notes.note_count()
    except Exception as exc:
        note_count = f"error: {exc}"
    items = [
        ("Python", "ok", report["python"]),
        ("Node", "ok", report["node"] or "missing"),
        ("npm", "ok", report["npm"] or "missing"),
        ("open-supermarkets", "ok" if report["binary"] else "warn", report["binary"] or "not installed"),
        ("Ollama", "ok" if OllamaClient(config.llm).available() else "warn", "local LLM"),
        ("Vault notes", "ok", str(note_count)),
    ]
    for retailer, status in report["retailers"].items():
        auth = status.get("authenticated", False)
        items.append((retailer, "ok" if auth else "warn", "authenticated" if auth else "session required"))
    status_panel(items)
    section("Config")
    data = config.model_dump(mode="json")
    agent = data["agent"]
    if agent.get("postcode"):
        agent["postcode"] = "[set]"
    console.print(json.dumps(data, indent=2))
    console.print()


@app.command()
def setup_node() -> None:
    config = _load_config()
    adapter = _adapter(config)
    output = adapter.install()
    ok(output or "open-supermarkets installed")


@app.command()
def vault_sync() -> None:
    config = _load_config()
    db = _db()
    db.initialize()
    with spinner("Syncing vault"):
        stats = Vault(config.paths.vault, config.paths.output_folder).sync(db)
    header("Vault Sync")
    ok(f"{stats['indexed']} notes indexed, {stats['unchanged']} unchanged, {stats['removed']} removed")


@app.command()
def notes_search(
    query: str,
    limit: int = typer.Option(10, "--limit"),
) -> None:
    _load_config()
    db = _db()
    db.initialize()
    results = db.notes.search_notes(query, limit=limit)
    section(f"Notes matching: {query}")
    for result in results:
        console.print(f"  {result['path']} | {result['title']} | {result.get('snippet', '')}")
    console.print()


@app.command()
def recipes_extract() -> None:
    config = _load_config()
    db = _db()
    db.initialize()
    with spinner("Clearing old recipes and extracting from vault"):
        db.catalog.clear_recipes()
        stats = extract_recipes(
            vault_root=config.paths.vault,
            db=db,
            llm=OllamaClient(config.llm),
        )
    header("Recipe Extraction")
    ok(f"{stats['recipes']} recipes from {stats['notes']} notes")


@app.command()
def plan(
    days: int = typer.Argument(7, min=1, max=28),
    servings: int = typer.Option(2, "--servings"),
    retailer: str | None = typer.Option(None, "--retailer"),
    budget_gbp: float | None = typer.Option(None, "--budget-gbp"),
    meal: list[str] = typer.Option(None, "--meal"),
) -> None:
    config = _load_config()
    db = _db()
    db.initialize()
    planner = MealPlanner(db, retailer=retailer or config.agent.retailers[0])
    plan_obj = planner.plan_meals(days, servings, meal)
    vault_indexer = Vault(config.paths.vault, config.paths.output_folder)
    vault_indexer.ensure_agent_folder()
    content = (
        f"---\n{AGENT_MARKER}\ntype: meal_plan\ndate: {plan_obj.start_date}\n---\n\n"
        f"# Meal plan {plan_obj.start_date}\n\n"
    )
    for item in plan_obj.items:
        content += f"- Day {item.day_index + 1}: {item.title} (servings {item.servings})\n"
    vault_indexer.write_agent_note(f"Meal Plans/{plan_obj.start_date}.md", content)
    header(f"Meal Plan — {plan_obj.start_date}")
    for item in plan_obj.items:
        console.print(f"  Day {item.day_index + 1}: {item.title} (servings {item.servings})")
    console.print()


@app.command()
def compare(
    retailer: str,
    query: str,
    limit: int = typer.Option(10, "--limit"),
) -> None:
    config = _load_config()
    adapter = _adapter(config)
    with spinner(f"Searching {retailer}"):
        products = adapter.search(retailer, query, limit=limit)
    section(f"{retailer.title()} — {query}")
    rows = []
    for product in products:
        price = money(product.price_minor)
        unit = ""
        if product.unit_price_minor is not None and product.unit_measure:
            unit = f"{money(product.unit_price_minor)}/{product.unit_measure}"
        stock = "ok" if product.in_stock is True else ("out" if product.in_stock is False else "unknown")
        rows.append((product.name, price, unit, stock))
    price_table(f"{retailer.title()} — {query}", rows)


@app.command()
def propose(
    days: int = typer.Argument(7, min=1, max=28),
    servings: int = typer.Option(2, "--servings"),
    retailer: str | None = typer.Option(None, "--retailer"),
    budget_gbp: float | None = typer.Option(None, "--budget-gbp"),
    meal: list[str] = typer.Option(None, "--meal"),
) -> None:
    config = _load_config()
    db = _db()
    db.initialize()
    adapter = _adapter(config)
    planner = MealPlanner(db, retailer=retailer or config.agent.retailers[0])
    plan_obj = planner.plan_meals(days, servings, meal)
    retailers = [retailer] if retailer else config.agent.retailers
    for target in retailers:
        try:
            with spinner(f"Building {target} proposal"):
                proposal = planner.propose(plan_obj, target, adapter, budget_gbp=budget_gbp or config.agent.budget_gbp)
            header(f"Proposal — {target}")
            lines = [
                {
                    "position": line.position,
                    "name": line.name,
                    "quantity": line.quantity,
                    "unit_price_minor": line.unit_price_minor,
                    "line_total_minor": line.line_total_minor,
                }
                for line in proposal.lines
            ]
            proposal_table(
                f"{target.title()} Basket",
                lines,
                budget_minor=proposal.budget_minor,
            )
        except Exception as exc:
            error(f"{target}: {exc}")


@app.command()
def proposal_show(
    proposal_id: int,
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    _load_config()
    db = _db()
    db.initialize()
    manager = ProposalManager(db)
    proposal = manager.show(proposal_id)
    if proposal is None:
        error("Proposal not found")
        raise typer.Exit(code=1)
    if json_output:
        console.print_json(json.dumps(proposal.model_dump(mode="json"), indent=2))
        return
    header(f"Proposal {proposal.id} — {proposal.retailer}")
    lines = [
        {
            "position": line.position,
            "name": line.name,
            "quantity": line.quantity,
            "unit_price_minor": line.unit_price_minor,
            "line_total_minor": line.line_total_minor,
        }
        for line in proposal.lines
    ]
    proposal_table(
        f"{proposal.retailer.title()} Basket",
        lines,
        budget_minor=proposal.budget_minor,
    )


@app.command()
def proposal_approve(
    proposal_id: int,
    note: str = typer.Option("", "--note"),
) -> None:
    _load_config()
    db = _db()
    db.initialize()
    manager = ProposalManager(db)
    proposal = manager.approve(proposal_id, note)
    if proposal is None:
        error("Proposal not found or not approvable")
        raise typer.Exit(code=1)
    ok(f"Proposal {proposal.id} approved")


@app.command()
def proposal_apply(proposal_id: int) -> None:
    config = _load_config()
    db = _db()
    db.initialize()
    adapter = _adapter(config)
    manager = ProposalManager(db)
    proposal = manager.apply(proposal_id, adapter)
    if proposal is None:
        error("Proposal not found")
        raise typer.Exit(code=1)
    header("Apply Result")
    ok(f"Proposal {proposal.id} status: {proposal.status}")


@app.command()
def basket_show(retailer: str | None = typer.Option(None, "--retailer")) -> None:
    config = _load_config()
    adapter = _adapter(config)
    target = retailer or config.agent.retailers[0]
    basket = adapter.basket(target)
    section(f"{basket.provider.title()} Basket")
    rows = []
    for item in basket.items:
        rows.append((item.name, money(item.line_total_minor), money(item.unit_price_minor), "ok"))
    price_table(f"{basket.provider.title()} Basket", rows, show_total=True, total_minor=basket.total_minor)


@app.command()
def auth(
    retailer: str,
    cookie_file: str | None = typer.Option(None, "--cookie-file", help="Cookies JSON for Tesco import"),
) -> None:
    config = _load_config()
    adapter = _adapter(config)
    code = adapter.import_session(retailer, Path(cookie_file)) if cookie_file else adapter.login(retailer)
    header("Auth")
    ok(f"Auth exit code: {code}")


@app.command()
def history_import(
    retailer: str = typer.Option("all", "--retailer"),
    limit: int = typer.Option(20, "--limit"),
) -> None:
    config = _load_config()
    db = _db()
    db.initialize()
    adapter = _adapter(config)
    importer = OrderImporter(db, adapter)
    targets = config.agent.retailers if retailer == "all" else [retailer]
    total = 0
    for target in targets:
        total += importer.import_orders(target, limit=limit)
    header("History Import")
    ok(f"{total} orders imported")


@app.command()
def history_import_csv(
    path: Path,
    retailer: str = typer.Option(..., "--retailer"),
) -> None:
    config = _load_config()
    db = _db()
    db.initialize()
    adapter = _adapter(config)
    importer = OrderImporter(db, adapter)
    count = importer.import_csv(path, retailer)
    header("CSV Import")
    ok(f"{count} order rows imported")


@app.command()
def config_show() -> None:
    config = _load_config()
    header("Config")
    data = config.model_dump(mode="json")
    agent = data["agent"]
    if agent.get("postcode"):
        agent["postcode"] = "[set]"
    console.print_json(json.dumps(data, indent=2))


@app.command()
def serve(
    port: int = typer.Option(8789, "--port", help="Dashboard port"),
) -> None:
    """Start the local dashboard for browsing orders, recipes, and prices."""
    import uvicorn

    header("Dashboard")
    ok(f"Local dashboard: http://127.0.0.1:{port}")
    uvicorn.run("grocery_agent.dashboard:app", host="127.0.0.1", port=port)


if __name__ == "__main__":
    app()
