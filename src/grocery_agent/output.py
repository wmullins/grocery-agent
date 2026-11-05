from __future__ import annotations

from contextlib import contextmanager

from rich.box import ROUNDED
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console(width=100)

PRIMARY = "#1a202c"
ACCENT = "#e53e3e"
MUTED = "#718096"
SUCCESS = "#38a169"
WARN = "#d69e2e"


def header(title: str, subtitle: str | None = None) -> None:
    text = Text(title, style=f"bold {PRIMARY}")
    if subtitle:
        text.append(f"\n{subtitle}", style=MUTED)
    console.print()
    console.print(Panel(text, box=ROUNDED, border_style=PRIMARY, padding=(1, 2)))
    console.print()


def section(title: str) -> None:
    console.print(Text(f"▸ {title}", style=f"bold {ACCENT}"))


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
    table = Table(title=title, box=ROUNDED, border_style=PRIMARY, header_style=f"bold {PRIMARY}")
    table.add_column("Product", style="bold")
    table.add_column("Price", justify="right")
    table.add_column("Unit", justify="right", style=MUTED)
    table.add_column("Stock", justify="center")
    for name, price, unit, stock in rows:
        stock_style = SUCCESS if stock == "ok" else (WARN if stock == "unknown" else ACCENT)
        table.add_row(name, price, unit, Text(stock, style=stock_style))
    if show_total and total_minor is not None:
        table.add_row(Text("Total", style=f"bold {PRIMARY}"), Text(money(total_minor), style=f"bold {PRIMARY}"), "", "")
    console.print(table)
    console.print()


def proposal_table(title: str, lines: list[dict], budget_minor: int | None = None) -> None:
    table = Table(title=title, box=ROUNDED, border_style=PRIMARY, header_style=f"bold {PRIMARY}")
    table.add_column("#", justify="right", style=MUTED)
    table.add_column("Product", style="bold")
    table.add_column("Qty", justify="right")
    table.add_column("Unit", justify="right", style=MUTED)
    table.add_column("Line", justify="right")
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
        style = SUCCESS if remaining >= 0 else ACCENT
        console.print(
            Panel(
                Text(
                    f"Subtotal: {money(total)}   Budget: {money(budget_minor)}   Remaining: {money(remaining)}",
                    style=f"bold {style}",
                ),
                box=ROUNDED,
                border_style=style,
                padding=(0, 1),
            )
        )
    console.print()


def status_panel(items: list[tuple[str, str, str]]) -> None:
    table = Table(box=ROUNDED, border_style=PRIMARY, show_header=False)
    table.add_column("Item", style=MUTED)
    table.add_column("Status", justify="center")
    table.add_column("Detail")
    for name, status, detail in items:
        style = SUCCESS if status == "ok" else (WARN if status == "warn" else ACCENT)
        table.add_row(name, Text(status.upper(), style=style), detail)
    console.print(Panel(table, title="Doctor", title_align="left", box=ROUNDED, border_style=PRIMARY))
    console.print()


def ok(message: str) -> None:
    console.print(Text(f"✓ {message}", style=SUCCESS))


def warn(message: str) -> None:
    console.print(Text(f"⚠ {message}", style=WARN))


def error(message: str) -> None:
    console.print(Text(f"✗ {message}", style=ACCENT))


@contextmanager
def spinner(message: str):
    with console.status(Text(f"▸ {message}", style=PRIMARY), spinner="dots"):
        yield
