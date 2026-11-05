from __future__ import annotations

from contextlib import contextmanager

from rich.align import Align
from rich.box import HEAVY, ROUNDED, SIMPLE_HEAVY
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.text import Text

console = Console(width=110)

# Lichtenstein pop-art palette over Ives minimalism
INK = "#0a0a0a"  # near-black
PAPER = "#ffffff"  # pure white
ACCENT = "#ff0033"  # Lichtenstein red
ACCENT_DARK = "#cc0022"
BLUE = "#0033ff"  # Lichtenstein blue
BLUE_DARK = "#0022cc"
YELLOW = "#ffcc00"  # Lichtenstein yellow
YELLOW_DARK = "#ccaa00"
MUTED = "#666666"
LINE = "#e5e5e5"


def header(title: str, subtitle: str | None = None) -> None:
    text = Text(title, style=f"bold {INK}")
    if subtitle:
        text.append(f"  ·  {subtitle}", style=MUTED)
    panel = Panel(
        Align.left(text, pad=(0, 2)),
        box=HEAVY,
        border_style=ACCENT_DARK,
        padding=(0, 1),
    )
    console.print()
    console.print(panel)
    console.print()


def section(title: str) -> None:
    console.print(Text(f"{title.upper()}", style=f"bold {MUTED}"))


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
    table = Table(
        title=title,
        box=SIMPLE_HEAVY,
        border_style=LINE,
        header_style=f"bold {INK}",
        show_lines=False,
    )
    table.add_column("Product", style=f"bold {INK}")
    table.add_column("Price", justify="right", style=ACCENT)
    table.add_column("Unit", justify="right", style=MUTED)
    table.add_column("Stock", justify="center", style=INK)
    for name, price, unit, stock in rows:
        stock_style = "#0033ff" if stock == "ok" else ACCENT
        table.add_row(name, price, unit, Text(stock, style=stock_style))
    if show_total and total_minor is not None:
        table.add_row(
            Text("Total", style=f"bold {INK}"),
            Text(money(total_minor), style=f"bold {ACCENT}"),
            "",
            "",
        )
    console.print(table)
    console.print()


def proposal_table(title: str, lines: list[dict], budget_minor: int | None = None) -> None:
    table = Table(
        title=title,
        box=SIMPLE_HEAVY,
        border_style=LINE,
        header_style=f"bold {INK}",
    )
    table.add_column("#", justify="right", style=MUTED)
    table.add_column("Product", style=f"bold {INK}")
    table.add_column("Qty", justify="right", style=INK)
    table.add_column("Unit", justify="right", style=MUTED)
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
        style = ACCENT if remaining >= 0 else BLUE
        console.print(
            Panel(
                Align.left(
                    Text(
                        f"Subtotal: {money(total)}   Budget: {money(budget_minor)}   Remaining: {money(remaining)}",
                        style=f"bold {style}",
                    ),
                    pad=(0, 1),
                ),
                box=SIMPLE_HEAVY,
                border_style=LINE,
                padding=(0, 1),
            )
        )
    console.print()


def status_panel(items: list[tuple[str, str, str]]) -> None:
    table = Table(box=SIMPLE_HEAVY, border_style=LINE, show_header=False)
    table.add_column("Item", style=MUTED)
    table.add_column("Status", justify="center")
    table.add_column("Detail", style=INK)
    for name, status, detail in items:
        style = "#0033ff" if status == "ok" else ACCENT
        table.add_row(name, Text(status.upper(), style=style), detail)
    console.print(
        Panel(
            table,
            title="Doctor",
            title_align="left",
            box=ROUNDED,
            border_style=INK,
            padding=(0, 1),
        )
    )
    console.print()


def ok(message: str) -> None:
    console.print(Text(f"✓ {message}", style="#0033ff"))


def warn(message: str) -> None:
    console.print(Text(f"⚠ {message}", style=ACCENT))


def error(message: str) -> None:
    console.print(Text(f"✗ {message}", style=ACCENT_DARK))


@contextmanager
def spinner(message: str):
    progress = Progress(
        SpinnerColumn(),
        TextColumn("{task.description}"),
        transient=True,
    )
    with progress:
        progress.add_task(message)
        yield
