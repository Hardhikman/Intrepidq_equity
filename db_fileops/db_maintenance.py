"""
Database maintenance utility for equity_ai.db

Provides CLI commands for database cleanup, statistics, and management.
"""

import sys
import os

# Add parent directory to path to allow imports from context_engineering
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import sqlite3
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from typing import Optional

app = typer.Typer()
console = Console()

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "equity_ai.db")


@app.command()
def cleanup(
    ticker: Optional[str] = None,
    keep: int = 3,
    dry_run: bool = False
):
    """
    Delete old reports, keeping only the latest N per ticker.
    
    Args:
        ticker: Optional ticker symbol to cleanup (if not provided, cleans all)
        keep: Number of latest reports to keep per ticker (default: 3)
        dry_run: Preview what would be deleted without actually deleting
    """
    from context_engineering.memory import cleanup_old_reports, cleanup_all_tickers, get_all_ticker_counts
    
    if dry_run:
        console.print("[yellow]DRY RUN MODE - No changes will be made[/yellow]\n")
    
    if ticker:
        ticker = ticker.upper()
        # Get current count
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT COUNT(*) FROM analysis_reports WHERE ticker = ?",
                (ticker,)
            )
            current_count = cur.fetchone()[0]
        
        if current_count == 0:
            console.print(f"[yellow]No reports found for {ticker}[/yellow]")
            return
        
        to_delete = max(0, current_count - keep)
        
        if to_delete == 0:
            console.print(f"[green]{ticker} has {current_count} report(s), no cleanup needed (keeping {keep})[/green]")
            return
        
        console.print(f"[cyan]{ticker}:[/cyan] {current_count} reports -> will keep {keep}, delete {to_delete}")
        
        if not dry_run:
            deleted = cleanup_old_reports(ticker, keep)
            console.print(f"[green]✓ Deleted {deleted} old report(s) for {ticker}[/green]")
    else:
        # Cleanup all tickers
        ticker_counts = get_all_ticker_counts()
        
        if not ticker_counts:
            console.print("[yellow]No reports in database[/yellow]")
            return
        
        table = Table(title="Cleanup Preview" if dry_run else "Cleanup Results")
        table.add_column("Ticker", style="cyan")
        table.add_column("Current", style="yellow")
        table.add_column("To Delete", style="red")
        table.add_column("Keep", style="green")
        
        total_to_delete = 0
        
        for item in ticker_counts:
            ticker_name = item["ticker"]
            count = item["count"]
            to_delete = max(0, count - keep)
            
            if to_delete > 0:
                table.add_row(ticker_name, str(count), str(to_delete), str(keep))
                total_to_delete += to_delete
        
        console.print(table)
        console.print(f"\n[bold]Total reports to delete:[/bold] {total_to_delete}")
        
        if not dry_run and total_to_delete > 0:
            results = cleanup_all_tickers(keep)
            console.print(f"\n[green]✓ Cleanup complete! Deleted {sum(results.values())} report(s) across {len(results)} ticker(s)[/green]")


@app.command()
def stats():
    """Show database statistics and storage information."""
    from context_engineering.memory import get_all_ticker_counts
    
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        
        # Total reports
        cur.execute("SELECT COUNT(*) FROM analysis_reports")
        total = cur.fetchone()[0]
        
        # Database size
        cur.execute("SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size()")
        db_size = cur.fetchone()[0]
        db_size_mb = db_size / (1024 * 1024)
    
    ticker_counts = get_all_ticker_counts()
    
    # Summary panel
    summary = f"""
[bold cyan]Total Reports:[/bold cyan] {total}
[bold cyan]Unique Tickers:[/bold cyan] {len(ticker_counts)}
[bold cyan]Database Size:[/bold cyan] {db_size_mb:.2f} MB
    """
    
    console.print(Panel(summary.strip(), title="Database Statistics", border_style="cyan"))
    
    if ticker_counts:
        console.print()
        table = Table(title="Reports by Ticker")
        table.add_column("Ticker", style="yellow")
        table.add_column("Count", style="green")
        table.add_column("Status", style="white")
        
        for item in ticker_counts:
            ticker = item["ticker"]
            count = item["count"]
            
            if count > 3:
                status = f"⚠️  {count - 3} excess report(s)"
                style = "yellow"
            else:
                status = "✓ OK"
                style = "green"
            
            table.add_row(ticker, str(count), f"[{style}]{status}[/{style}]")
        
        console.print(table)
        
        # Cleanup recommendation
        excess_count = sum(max(0, item["count"] - 3) for item in ticker_counts)
        if excess_count > 0:
            console.print(f"\n[yellow]💡 Tip: Run 'python db_fileops/db_maintenance.py cleanup' to remove {excess_count} excess report(s)[/yellow]")


@app.command()
def delete_ticker(ticker: str, confirm: bool = typer.Option(False, "--confirm", help="Confirm deletion")):
    """
    Delete all reports for a specific ticker.
    
    WARNING: This permanently deletes all reports for the ticker.
    """
    from context_engineering.memory import delete_all_ticker_reports, get_report_count_by_ticker
    
    ticker = ticker.upper()
    count = get_report_count_by_ticker(ticker)
    
    if count == 0:
        console.print(f"[yellow]No reports found for {ticker}[/yellow]")
        return
    
    if not confirm:
        console.print(f"[red]⚠️  WARNING: This will permanently delete {count} report(s) for {ticker}[/red]")
        console.print(f"[yellow]Use --confirm flag to proceed: python db_fileops/db_maintenance.py delete-ticker {ticker} --confirm[/yellow]")
        return
    
    deleted = delete_all_ticker_reports(ticker)
    console.print(f"[green]✓ Deleted {deleted} report(s) for {ticker}[/green]")


@app.command(name="cleanup-by-date")
def cleanup_by_date(
    before: Optional[str] = typer.Option(None, help="Delete reports before this date (YYYY-MM-DD)"),
    older_than: Optional[int] = typer.Option(None, help="Delete reports older than N days"),
    ticker: Optional[str] = typer.Option(None, help="Only cleanup specific ticker"),
    dry_run: bool = typer.Option(False, help="Preview what would be deleted without actually deleting")
):
    """
    Delete reports based on date criteria.
    
    Examples:
        python db_fileops/db_maintenance.py cleanup-by-date --before 2025-12-08
        python db_fileops/db_maintenance.py cleanup-by-date --older-than 7
        python db_fileops/db_maintenance.py cleanup-by-date --older-than 7 --ticker TSLA
    """
    from datetime import datetime, timedelta
    
    if not before and older_than is None:
        console.print("[red]Error: Must specify either --before DATE or --older-than DAYS[/red]")
        return
    
    # Calculate cutoff date
    if before:
        try:
            cutoff_date = datetime.strptime(before, "%Y-%m-%d")
        except ValueError:
            console.print("[red]Error: Invalid date format. Use YYYY-MM-DD[/red]")
            return
    else:
        cutoff_date = datetime.now() - timedelta(days=older_than)
    
    cutoff_str = cutoff_date.strftime("%Y-%m-%d %H:%M:%S")
    
    if dry_run:
        console.print("[yellow]DRY RUN MODE - No changes will be made[/yellow]\n")
    
    console.print(f"[cyan]Cutoff date:[/cyan] {cutoff_date.strftime('%Y-%m-%d')}")
    if ticker:
        console.print(f"[cyan]Filtering by ticker:[/cyan] {ticker.upper()}")
    console.print()
    
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        
        # Build query
        if ticker:
            cur.execute(
                """
                SELECT id, ticker, created_at, LENGTH(report) as report_len 
                FROM analysis_reports 
                WHERE created_at < ? AND ticker = ?
                ORDER BY created_at DESC
                """,
                (cutoff_str, ticker.upper())
            )
        else:
            cur.execute(
                """
                SELECT id, ticker, created_at, LENGTH(report) as report_len 
                FROM analysis_reports 
                WHERE created_at < ?
                ORDER BY created_at DESC
                """,
                (cutoff_str,)
            )
        
        rows = cur.fetchall()
        
        if not rows:
            console.print("[green]No reports found matching the criteria[/green]")
            return
        
        # Display reports to be deleted
        table = Table(title=f"Reports to Delete ({len(rows)} total)")
        table.add_column("ID", style="dim")
        table.add_column("Ticker", style="cyan")
        table.add_column("Date", style="yellow")
        table.add_column("Report Size", style="white")
        
        for row in rows:
            report_id, tick, date, report_len = row
            size_display = f"{report_len:,} chars"
            if report_len < 2000:
                size_display = f"[red]{size_display} (incomplete?)[/red]"
            table.add_row(str(report_id), tick, date, size_display)
        
        console.print(table)
        
        if not dry_run:
            # Delete the reports
            ids_to_delete = [row[0] for row in rows]
            placeholders = ','.join('?' * len(ids_to_delete))
            cur.execute(f"DELETE FROM analysis_reports WHERE id IN ({placeholders})", ids_to_delete)
            conn.commit()
            console.print(f"\n[green]✓ Deleted {len(rows)} report(s)[/green]")
        else:
            console.print(f"\n[yellow]Would delete {len(rows)} report(s). Run without --dry-run to execute.[/yellow]")


@app.command()
def list_tickers():
    """List all tickers in the database with report counts."""
    from context_engineering.memory import get_all_ticker_counts
    
    ticker_counts = get_all_ticker_counts()
    
    if not ticker_counts:
        console.print("[yellow]No tickers found in database[/yellow]")
        return
    
    table = Table(title=f"All Tickers ({len(ticker_counts)} total)")
    table.add_column("#", style="dim")
    table.add_column("Ticker", style="cyan bold")
    table.add_column("Reports", style="green")
    
    for idx, item in enumerate(ticker_counts, 1):
        table.add_row(str(idx), item["ticker"], str(item["count"]))
    
    console.print(table)


@app.command(name="purge-all")
def purge_all(confirm: bool = typer.Option(False, "--confirm", help="Confirm deletion of ALL reports")):
    """
    Delete ALL reports from the database.
    
    WARNING: This permanently deletes all analysis reports!
    
    Example:
        python db_fileops/db_maintenance.py purge-all --confirm
    """
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM analysis_reports")
        total = cur.fetchone()[0]
    
    if total == 0:
        console.print("[yellow]Database is already empty[/yellow]")
        return
    
    if not confirm:
        console.print(f"[red]⚠️  WARNING: This will permanently delete ALL {total} report(s)[/red]")
        console.print("[yellow]Use --confirm flag to proceed: python db_fileops/db_maintenance.py purge-all --confirm[/yellow]")
        return
    
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM analysis_reports")
        conn.commit()
    
    console.print(f"[green]✓ Deleted all {total} report(s) from database[/green]")


@app.command(name="cleanup-files")
def cleanup_files(
    ticker: Optional[str] = typer.Option(None, help="Only cleanup specific ticker"),
    keep: int = typer.Option(3, help="Number of latest files to keep per ticker"),
    dry_run: bool = typer.Option(False, help="Preview what would be deleted without actually deleting")
):
    """
    Cleanup old report files in the reports/ directory.
    
    This command manages markdown report files, keeping only the latest N per ticker.
    
    Examples:
        python db_fileops/db_maintenance.py cleanup-files
        python db_fileops/db_maintenance.py cleanup-files --ticker AAPL
        python db_fileops/db_maintenance.py cleanup-files --keep 1 --dry-run
    """
    from pathlib import Path
    import re
    
    reports_dir = Path(os.path.dirname(os.path.dirname(__file__))) / "reports"
    
    if not reports_dir.exists():
        console.print("[yellow]No reports directory found[/yellow]")
        return
    
    if dry_run:
        console.print("[yellow]DRY RUN MODE - No changes will be made[/yellow]\n")
    
    # Group files by ticker
    ticker_files = {}
    file_pattern = re.compile(r"^([A-Z]+)_\d{8}_\d{6}\.md$")
    
    for f in reports_dir.iterdir():
        if f.is_file():
            match = file_pattern.match(f.name)
            if match:
                tick = match.group(1)
                if ticker and tick != ticker.upper():
                    continue
                if tick not in ticker_files:
                    ticker_files[tick] = []
                ticker_files[tick].append(f)
    
    if not ticker_files:
        console.print("[green]No report files found matching criteria[/green]")
        return
    
    # Sort each ticker's files by modification time (latest first)
    for tick in ticker_files:
        ticker_files[tick].sort(key=lambda x: x.stat().st_mtime, reverse=True)
    
    # Build table
    table = Table(title="Report Files Cleanup" + (" Preview" if dry_run else ""))
    table.add_column("Ticker", style="cyan")
    table.add_column("Total Files", style="yellow")
    table.add_column("To Delete", style="red")
    table.add_column("Keep", style="green")
    
    total_to_delete = 0
    files_to_delete = []
    
    for tick, files in sorted(ticker_files.items()):
        to_delete = max(0, len(files) - keep)
        if to_delete > 0:
            table.add_row(tick, str(len(files)), str(to_delete), str(keep))
            total_to_delete += to_delete
            files_to_delete.extend(files[keep:])
    
    if total_to_delete == 0:
        console.print("[green]No files need cleanup[/green]")
        return
    
    console.print(table)
    console.print(f"\n[bold]Total files to delete:[/bold] {total_to_delete}")
    
    if dry_run:
        console.print("\n[bold]Files that would be deleted:[/bold]")
        for f in files_to_delete:
            console.print(f"  [dim]{f.name}[/dim]")
    else:
        for f in files_to_delete:
            f.unlink()
        console.print(f"\n[green]✓ Deleted {total_to_delete} file(s)[/green]")


if __name__ == "__main__":
    app()
