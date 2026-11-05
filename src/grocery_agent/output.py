from __future__ import annotations

from contextlib import contextmanager

from rich.box import SIMPLE_HEAVY
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console(width=100)

INK = "#1a1a1a"
PAPER = "#f5f5f0"
ACCENT = "#0036ff"  # deep blue — single accent
INK_MUTED = "#666666"
LINE = "#d9d9d9"
OK = "#0a7a0a"
WARN = "#b5651d"
ERROR = "#b00020"


def header(title: str, subtitle: str | None = None) -> None:
    text = Text(title, style=f"bold {INK}")
    if subtitle:
        text.append(f"  ·  {subtitle}", style=INK_MUTED)
    console.print()
    console.print(Panel(text, box=SIMPLE_HEAVY, border_style=LINE, padding=(0, 1)))
    console.print()


def section(title: str) -> None:
    console.print(Text(f"{title.upper()}", style=f"bold {INK_MUTED}"))


def money(minor: int | None) -> str:
    if minor is None:
        return "—"
    return f"£{minor / 100:.2f}"


def price_table(
    title: str,
    rows: list[tuple[str, str, str, str]],
    *,
    show_total: bool = False,
    total_minor: int | None = None,
) -> None:
    table = Table(title=title, box=SIMPLE_HEAVY, border_style=LINE, header_style=f"bold {INK}")
    table.add_column("Product", style=f"bold {INK}")
    table.add_column("Price", justify="right", style=INK)
    table.add_column("Unit", justify="right", style=INK_MUTED)
    table.add_column("Stock", justify="center", style=INK_MUTED)
    for name, price, unit, stock in rows:
        stock_style = OK if stock == "ok" else (WARN if stock == "unknown" else ERROR)
        table.add_row(name, price, unit, Text(stock, style=stock_style))
    if show_total and total_minor is not None:
        table.add_row(Text("Total", style=f"bold {INK}"), Text(money(total_minor), style=f"bold {INK}"), "", "")
    console.print(table)
    console.print()


def proposal_table(title: str, lines: list[dict], budget_minor: int | None = None) -> None:
    table = Table(title=title, box=SIMPLE_HEAVY, border_style=LINE, header_style=f"bold {INK}")
    table.add_column("#", justify="right", style=INK_MUTED)
    table.add_column("Product", style=f"bold {INK}")
    table.add_column("Qty", justify="right", style=INK)
    table.add_column("Unit", justify="right", style=INK_MUTED)
    table.add_column("Line", justify="right", style=INK)
    for line in lines:
        table.add_row(
            str(line["position"]),
            line["name"],
            str(line["quantity"]),
            money(line["unit_price_minor"]),
            money(line["line_total_minor"]),
        )
    console.print(table)
    if budget_minor is not None:
        total = sum(line.get("line_total_minor") or 0 for line in lines)
        remaining = budget_minor - total
        style = OK if remaining >= 0 else ERROR
        console.print(
            Panel(
                Text(
                    f"Subtotal: {money(total)}   Budget: {money(budget_minor)}   Remaining: {money(remaining)}",
                    style=f"bold {style}",
                ),
                box=SIMPLE_HEAVY,
                border_style=LINE,
                padding=(0, 1),
            )
        )
    console.print()


def status_panel(items: list[tuple[str, str, str]]) -> None:
    table = Table(box=SIMPLE_HEAVY, border_style=LINE, show_header=False)
    table.add_column("Item", style=INK_MUTED)
    table.add_column("Status", justify="center")
    table.add_column("Detail", style=INK)
    for name, status, detail in items:
        style = OK if status == "ok" else (WARN if status == "warn" else ERROR)
        table.add_row(name, Text(status.upper(), style=style), detail)
    console.print(Panel(table, title="Doctor", title_align="left", box=SIMPLE_HEAVY, border_style=LINE, padding=(0, 1)))
    console.print()


def ok(message: str) -> None:
    console.print(Text(f"✓ {message}", style=OK))


def warn(message: str) -> None:
    console.print(Text(f"⚠ {message}", style=WARN))


def error(message: str) -> None:
    console.print(Text(f"✗ {message}", style=ERROR))


@contextmanager
def spinner(message: str):
    with console.status(Text(f"▸ {message}", style=INK), spinner="dots"):
        yield
