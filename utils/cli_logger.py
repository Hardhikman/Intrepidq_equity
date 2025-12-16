"""
IntrepidQ CLI Logger
Provides Rich-formatted logging with clean, professional CLI interface.
Features: Status spinners, live progress tables, timing metrics.
"""

import time
from typing import Dict, Any, List, Optional
from contextlib import contextmanager
from rich.console import Console, Group
from rich.panel import Panel
from rich.text import Text
from rich.tree import Tree
from rich.style import Style
from rich.layout import Layout
from rich.box import DOUBLE, ROUNDED
from rich.table import Table
from rich.live import Live
from rich.spinner import Spinner
from rich.status import Status

console = Console(width=100)

# ASCII Art Header
HEADER_ART = """
[bold cyan]██╗███╗   ██╗████████╗██████╗ ███████╗██████╗ ██╗██████╗  ██████╗ [/]
[bold blue]██║████╗  ██║╚══██╔══╝██╔══██╗██╔════╝██╔══██╗██║██╔══██╗██╔═══██╗[/]
[bold magenta]██║██╔██╗ ██║   ██║   ██████╔╝█████╗  ██████╔╝██║██║  ██║██║   ██║[/]
[bold magenta]██║██║╚██╗██║   ██║   ██╔══██╗██╔══╝  ██╔═══╝ ██║██║  ██║██║▄▄ ██║[/]
[bold blue]██║██║ ╚████║   ██║   ██║  ██║███████╗██║     ██║██████╔╝╚██████╔╝[/]
[bold cyan]╚═╝╚═╝  ╚═══╝   ╚═╝   ╚═╝  ╚═╝╚══════╝╚═╝     ╚═╝╚═════╝  ╚══▀▀═╝ [/]
"""

# Phase definitions for the workflow
PHASES = ["Data Collection", "Validation", "Analysis", "Synthesis"]


class PhaseTracker:
    """Tracks progress and timing for each phase of the workflow."""
    
    def __init__(self):
        self.phases: Dict[str, Dict[str, Any]] = {}
        self.current_phase: Optional[str] = None
        self.ticker: str = ""
        
    def reset(self, ticker: str):
        """Reset tracker for a new analysis run."""
        self.ticker = ticker
        self.phases = {
            phase: {"status": "pending", "start_time": None, "end_time": None, "details": []}
            for phase in PHASES
        }
        self.current_phase = None
        
    def start_phase(self, phase: str):
        """Mark a phase as started."""
        if phase in self.phases:
            self.phases[phase]["status"] = "active"
            self.phases[phase]["start_time"] = time.time()
            self.current_phase = phase
            
    def complete_phase(self, phase: str):
        """Mark a phase as completed."""
        if phase in self.phases:
            self.phases[phase]["status"] = "done"
            self.phases[phase]["end_time"] = time.time()
            if self.current_phase == phase:
                self.current_phase = None
                
    def add_detail(self, phase: str, detail: str):
        """Add a detail message to a phase."""
        if phase in self.phases:
            self.phases[phase]["details"].append(detail)
            
    def get_elapsed(self, phase: str) -> str:
        """Get elapsed time for a phase."""
        if phase not in self.phases:
            return "-"
        p = self.phases[phase]
        if p["status"] == "pending":
            return "-"
        elif p["status"] == "active":
            elapsed = time.time() - p["start_time"]
            return f"{elapsed:.1f}s"
        else:  # done
            elapsed = p["end_time"] - p["start_time"]
            return f"{elapsed:.1f}s"
            
    def get_status_icon(self, phase: str) -> str:
        """Get status icon for a phase."""
        if phase not in self.phases:
            return "○"
        status = self.phases[phase]["status"]
        if status == "pending":
            return "[dim]○[/dim]"
        elif status == "active":
            return "[yellow]◉[/yellow]"
        else:  # done
            return "[green]✓[/green]"
            
    def build_progress_table(self) -> Table:
        """Build the progress tracking table."""
        table = Table(
            title=f"[bold]IntrepidQ Analysis: {self.ticker}[/bold]",
            box=ROUNDED,
            show_header=True,
            header_style="bold cyan",
            width=70
        )
        table.add_column("Phase", style="white", width=20)
        table.add_column("Status", justify="center", width=12)
        table.add_column("Time", justify="right", width=10)
        table.add_column("Details", style="dim", width=25)
        
        for phase in PHASES:
            icon = self.get_status_icon(phase)
            elapsed = self.get_elapsed(phase)
            details = self.phases.get(phase, {}).get("details", [])
            detail_str = details[-1] if details else ""
            if len(detail_str) > 25:
                detail_str = detail_str[:22] + "..."
            table.add_row(phase, icon, elapsed, detail_str)
            
        return table


class IntrepidQLogger:
    """
    Manages structured logging for the IntrepidQ application.
    Features clean progress visualization with spinners and live tables.
    """
    
    def __init__(self, verbose: bool = False):
        self.console = console
        self.verbose = verbose
        self.tracker = PhaseTracker()
        self._live: Optional[Live] = None
        self._status: Optional[Status] = None
        
    def print_header(self):
        """Print the application header."""
        self.console.print(Panel(
            Text("Welcome to IntrepidQ", justify="center", style="bold white"),
            box=DOUBLE,
            style="cyan",
            width=100
        ))
        self.console.print(HEADER_ART)
        self.console.print(Text("Your AI assistant for equity analysis.\n", justify="center", style="dim"))

    def start_analysis(self, ticker: str):
        """Initialize tracking for a new analysis run."""
        self.tracker.reset(ticker)
        self.console.print()
        self.console.print(f"[bold cyan]▶ Starting Analysis for [white]{ticker}[/white][/bold cyan]")
        self.console.print()
        
    def show_progress(self):
        """Display the current progress table."""
        self.console.print(self.tracker.build_progress_table())
        
    @contextmanager
    def phase(self, phase_name: str):
        """Context manager for tracking a phase with spinner."""
        self.tracker.start_phase(phase_name)
        try:
            with self.console.status(
                f"[bold blue]{phase_name}...[/bold blue]",
                spinner="dots"
            ) as status:
                self._status = status
                yield status
        finally:
            self._status = None
            self.tracker.complete_phase(phase_name)
            
    def update_status(self, message: str):
        """Update the current spinner status message."""
        if self._status:
            self._status.update(f"[bold blue]{message}[/bold blue]")
            
    def phase_detail(self, phase: str, detail: str):
        """Add a detail to a phase (shown in progress table)."""
        self.tracker.add_detail(phase, detail)

    # === Legacy methods for backward compatibility ===
    
    def start_section(self, title: str, style: str = "bold cyan"):
        """Start a new major section (like a phase of analysis)."""
        self.console.print()
        self.console.print(f"[{style}]>> {title}[/{style}]")

    def log_step(self, message: str, emoji: str = "🔹"):
        """Log a generic step."""
        if self.verbose:
            self.console.print(f" {emoji} {message}")
        # Update spinner if active
        if self._status:
            self._status.update(f"[bold blue]{message}[/bold blue]")

    def log_success(self, message: str):
        """Log a success message."""
        self.console.print(f"[green] ✓ {message}[/green]")

    def log_warning(self, message: str):
        """Log a warning."""
        self.console.print(f"[yellow] ⚠ {message}[/yellow]")
    
    def log_error(self, message: str):
        """Log an error."""
        self.console.print(f"[red] ✗ {message}[/red]")

    def start_task(self, task_name: str):
        """Start a specific task visualization."""
        if self.verbose:
            self.console.print(f"[bold blue] ▶ Task:[/bold blue] {task_name}")
        
    def log_tool_used(self, tool_name: str, args: Any = None, result: Any = None):
        """Log that a tool was used."""
        if not self.verbose:
            return  # Hide tool details in clean mode
            
        tool_msg = f"[bold magenta]⚡ {tool_name}[/bold magenta]"
        if args:
            args_str = str(args)
            if len(args_str) > 60:
                args_str = args_str[:57] + "..."
            tool_msg += f" [dim]({args_str})[/dim]"
        
        self.console.print(f"   {tool_msg}")
        
        if result:
            res_str = str(result)
            if len(res_str) > 100:
                res_str = res_str[:97] + "..."
            self.console.print(f"     [dim]→ {res_str}[/dim]")

    def print_panel(self, content: str, title: str, style: str = "cyan"):
        """Print detailed content in a panel."""
        self.console.print(Panel(content, title=title, border_style=style))
    
    def log_financial_data(self, data) -> None:
        """
        Display financial data as a Rich table.
        
        Args:
            data: FinancialData Pydantic model or dict with financial metrics
        """
        from utils.models import FinancialData
        
        # Temporarily stop spinner if active (so table displays properly)
        spinner_was_active = self._status is not None
        if spinner_was_active:
            self._status.stop()
        
        # Handle both Pydantic model and dict
        if isinstance(data, dict):
            try:
                data = FinancialData(**data)
            except Exception as e:
                self.log_warning(f"Could not parse financial data: {e}")
                if spinner_was_active and self._status:
                    self._status.start()
                return
        
        # Build the table
        table = Table(
            title=f"📊 [bold]{data.ticker}[/bold] Financial Summary",
            box=ROUNDED,
            show_header=True,
            header_style="bold cyan",
            width=80
        )
        table.add_column("Category", style="cyan", width=20)
        table.add_column("Metric", style="white", width=25)
        table.add_column("Value", style="green", justify="right", width=20)
        
        # Helper to format values
        def fmt(val, fmt_type="number"):
            if val is None:
                return "[dim]N/A[/dim]"
            if fmt_type == "price":
                return f"${val:,.2f}"
            elif fmt_type == "percent":
                return f"{val * 100:.1f}%"
            elif fmt_type == "ratio":
                return f"{val:.2f}"
            elif fmt_type == "large":
                if val >= 1e12:
                    return f"${val / 1e12:.2f}T"
                elif val >= 1e9:
                    return f"${val / 1e9:.2f}B"
                elif val >= 1e6:
                    return f"${val / 1e6:.2f}M"
                return f"${val:,.0f}"
            return f"{val:.2f}"
        
        # Price & Valuation
        table.add_row("💰 Price", "Current Price", fmt(data.current_price, "price"))
        table.add_row("", "Market Cap", fmt(data.market_cap, "large"))
        table.add_row("", "P/E (Trailing)", fmt(data.trailing_pe, "ratio"))
        table.add_row("", "P/E (Forward)", fmt(data.forward_pe, "ratio"))
        table.add_row("", "PEG Ratio", fmt(data.peg_ratio, "ratio"))
        
        # Growth & Margins
        table.add_row("📈 Growth", "Revenue Growth", fmt(data.revenue_growth, "percent"))
        table.add_row("", "Profit Margin", fmt(data.profit_margins, "percent"))
        table.add_row("", "ROE", fmt(data.return_on_equity, "percent"))
        
        # Risk
        table.add_row("⚠️ Risk", "Beta", fmt(data.beta, "ratio"))
        table.add_row("", "Debt/Equity", fmt(data.debt_to_equity, "ratio"))
        
        # Technicals (if available)
        if data.technicals:
            t = data.technicals
            table.add_row("📉 Technical", "RSI", fmt(t.rsi, "ratio"))
            table.add_row("", "SMA 50", fmt(t.sma_50, "price"))
            table.add_row("", "SMA 200", fmt(t.sma_200, "price"))
            if t.sma_200_weeks:
                table.add_row("", "SMA 200 Weeks", fmt(t.sma_200_weeks, "price"))
        
        # Risk Metrics (if available)
        if data.risk_metrics:
            r = data.risk_metrics
            table.add_row("📊 Risk Metrics", "Sharpe Ratio", fmt(r.sharpe_ratio, "ratio"))
            table.add_row("", "Volatility", fmt(r.volatility_annualized, "percent"))
            table.add_row("", "Max Drawdown", fmt(r.max_drawdown, "percent"))
        
        self.console.print()
        self.console.print(table)
        self.console.print()
        
        # Restart spinner if it was active
        if spinner_was_active and self._status:
            self._status.start()
    
    def log_news_item(self, title: str, date: str, source: str) -> None:
        """
        Log a single news item in real-time as it's fetched.
        
        Args:
            title: News headline
            date: Publication date
            source: Source domain (e.g., reuters.com)
        """
        # Truncate title if too long
        if len(title) > 60:
            title = title[:57] + "..."
        
        # Format: 📰 [source] Title (date)
        self.console.print(f"  📰 [cyan]{source}[/cyan] {title} [dim]({date})[/dim]")
    
    def log_news_signals(self, ticker: str, signals: list) -> None:
        """
        Display news signals as a Rich table.
        
        Args:
            ticker: Stock ticker
            signals: List of signal dicts with title, date, url
        """
        if not signals:
            self.console.print("[dim]  No news signals found.[/dim]")
            return
        
        # Temporarily stop spinner if active
        spinner_was_active = self._status is not None
        if spinner_was_active:
            self._status.stop()
        
        # Build the table
        table = Table(
            title=f"📰 [bold]{ticker}[/bold] News Signals ({len(signals)} found)",
            box=ROUNDED,
            show_header=True,
            header_style="bold cyan",
            width=90
        )
        table.add_column("Source", style="cyan", width=18)
        table.add_column("Title", style="white", width=50)
        table.add_column("Date", style="dim", width=18)
        
        # Import here to avoid circular imports
        from tools.definitions import _extract_domain
        
        # Show up to 10 signals to keep it readable
        for signal in signals[:10]:
            title = signal.get("title", "")
            if len(title) > 48:
                title = title[:45] + "..."
            source = _extract_domain(signal.get("url", ""))
            date = signal.get("date", "")[:18] if signal.get("date") else ""
            table.add_row(source, title, date)
        
        if len(signals) > 10:
            table.add_row("...", f"[dim]+{len(signals) - 10} more signals[/dim]", "")
        
        self.console.print()
        self.console.print(table)
        self.console.print()
        
        # Restart spinner if it was active
        if spinner_was_active and self._status:
            self._status.start()
        
    def print_summary(self):
        """Print the final progress summary table."""
        self.console.print()
        self.console.print(self.tracker.build_progress_table())
        self.console.print()
        
        # Calculate total time
        total_time = 0
        for phase in PHASES:
            p = self.tracker.phases.get(phase, {})
            if p.get("start_time") and p.get("end_time"):
                total_time += p["end_time"] - p["start_time"]
        
        self.console.print(f"[bold green]✓ Analysis complete in {total_time:.1f}s[/bold green]")
        self.console.print()

# Global instance
logger = IntrepidQLogger(verbose=False)
