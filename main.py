"""
Trading Intelligence Platform — Main Entry Point

Commands:
    python main.py scan          — Run a one-time signal scan across all symbols
    python main.py loop          — Run continuous signal scanning (every 60 min)
    python main.py journal       — Show trade journal statistics
    python main.py backtest      — Run backtesting on configured symbols
"""
import asyncio
import sys
from pathlib import Path

from loguru import logger
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import print as rprint

from src.config import settings
from src.signals.generator import SignalGenerator
from src.intelligence.evaluator import SignalResult
from src.notifications.telegram import TelegramNotifier
from src.journal.journal import TradeJournal

console = Console()
notifier = TelegramNotifier()
journal = TradeJournal()


def on_signal(signal: SignalResult):
    """Callback triggered when an approved signal is generated."""
    print_signal(signal)
    asyncio.create_task(notifier.send_signal(signal))


def print_signal(signal: SignalResult):
    """Print a formatted signal to the console."""
    color = "green" if signal.direction == "LONG" else "red"
    status = "[bold green]APPROVED[/]" if signal.approved else f"[bold red]REJECTED — {signal.rejection_reason}[/]"

    panel_text = f"""
[bold]Direction:[/] [{color}]{signal.direction}[/]
[bold]Entry:[/]     {signal.entry:.4f}
[bold]Stop Loss:[/] {signal.stop_loss:.4f}
[bold]TP1:[/]       {signal.take_profit[0]:.4f if signal.take_profit else 'N/A'}
[bold]TP2:[/]       {signal.take_profit[1]:.4f if len(signal.take_profit) > 1 else 'N/A'}
[bold]R/R:[/]       {signal.risk_reward:.2f}:1
[bold]Score:[/]     {signal.score:.1f}/100
[bold]Confidence:[/]{signal.confidence:.0%}
[bold]Regime:[/]    {signal.market_regime}
[bold]Status:[/]    {status}

[bold]Confluence:[/]
{chr(10).join(f'  • {f}' for f in signal.confluence_factors)}

[bold]Reasoning:[/]
{signal.reasoning[:400]}{"..." if len(signal.reasoning) > 400 else ""}
"""
    console.print(Panel(
        panel_text,
        title=f"[bold]{signal.asset} Signal[/]",
        border_style=color,
    ))


async def cmd_scan():
    """One-time scan of all configured symbols."""
    console.print(f"\n[bold blue]Scanning {settings.symbol_list}...[/]\n")

    generator = SignalGenerator(
        knowledge_dir=str(Path(__file__).parent / "knowledge"),
        on_signal=on_signal,
    )

    signals = await generator.run_scan()

    if not signals:
        console.print("[yellow]No approved signals found in this scan.[/]")
    else:
        console.print(f"\n[bold green]{len(signals)} approved signal(s) generated.[/]")


async def cmd_loop():
    """Continuous scanning loop."""
    console.print("[bold blue]Starting continuous signal loop (every 60 minutes)...[/]")
    console.print(f"Monitoring: {settings.symbol_list}")
    console.print("Press Ctrl+C to stop.\n")

    generator = SignalGenerator(
        knowledge_dir=str(Path(__file__).parent / "knowledge"),
        on_signal=on_signal,
    )

    await notifier.send_message("Trading platform started. Monitoring: " + ", ".join(settings.symbol_list))
    await generator.run_loop(interval_minutes=60)


def cmd_journal():
    """Display trade journal statistics."""
    stats = journal.get_statistics()

    if stats.get("total_trades", 0) == 0:
        console.print("[yellow]No closed trades in journal yet.[/]")
        return

    table = Table(title="Trade Journal Statistics", show_header=True)
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")

    table.add_row("Total Trades", str(stats["total_trades"]))
    table.add_row("Win Rate", f"{stats['win_rate']:.1%}")
    table.add_row("Avg Win (R)", f"{stats['avg_win_r']:.2f}R")
    table.add_row("Avg Loss (R)", f"{stats['avg_loss_r']:.2f}R")
    table.add_row("Expectancy", f"{stats['expectancy']:.3f}R")
    table.add_row("Profit Factor", f"{stats['profit_factor']:.2f}")
    table.add_row("Max Drawdown", f"{stats['max_drawdown']:.1%}")
    table.add_row("Total P&L (R)", f"{stats['total_r']:.2f}R")

    console.print(table)

    if stats.get("edge_by_setup"):
        console.print("\n[bold]Edge by Setup Type:[/]")
        setup_table = Table()
        setup_table.add_column("Setup Type")
        setup_table.add_column("Trades", justify="right")
        setup_table.add_column("Win Rate", justify="right")
        setup_table.add_column("Avg R", justify="right")

        for setup, data in stats["edge_by_setup"].items():
            setup_table.add_row(
                setup,
                str(data["sample_size"]),
                f"{data['win_rate']:.1%}",
                f"{data['avg_r']:.2f}R",
            )
        console.print(setup_table)


def main():
    args = sys.argv[1:]
    cmd = args[0] if args else "scan"

    if cmd == "scan":
        asyncio.run(cmd_scan())
    elif cmd == "loop":
        asyncio.run(cmd_loop())
    elif cmd == "journal":
        cmd_journal()
    elif cmd == "help":
        console.print(__doc__)
    else:
        console.print(f"[red]Unknown command: {cmd}[/]")
        console.print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
