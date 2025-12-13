"""
SQLite-based memory for saving deep equity analysis reports and (optionally) chat.
"""

import sqlite3
import time
from contextlib import contextmanager
from typing import List, Optional, Dict, Any


DB_PATH = "equity_ai.db"

# Configuration
REPORTS_TO_KEEP = 3  # Keep latest 3 reports per ticker
DB_RETRY_ATTEMPTS = 3
DB_RETRY_DELAY = 0.5  # seconds


@contextmanager
def _db_connect(db_path: str = DB_PATH, max_retries: int = DB_RETRY_ATTEMPTS):
    """
    Context manager for SQLite connections with retry logic for threading issues.
    Handles 'database is locked' errors with exponential backoff.
    """
    last_error = None
    for attempt in range(max_retries):
        try:
            conn = sqlite3.connect(db_path, timeout=10)
            try:
                yield conn
                conn.commit()
                return
            finally:
                conn.close()
        except sqlite3.OperationalError as e:
            last_error = e
            if "locked" in str(e).lower() and attempt < max_retries - 1:
                wait_time = DB_RETRY_DELAY * (2 ** attempt)
                print(f"Database locked, retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})")
                time.sleep(wait_time)
            else:
                raise
    raise last_error


def init_db() -> None:
    """Initialize the SQLite database and create tables if needed."""
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()

        # Analysis reports
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS analysis_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT UNIQUE,
                user_id TEXT,
                ticker TEXT,
                report TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Add indexes for performance
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_ticker 
            ON analysis_reports(ticker)
            """
        )
        
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_ticker_created 
            ON analysis_reports(ticker, created_at DESC)
            """
        )

        conn.commit()


# Initialize on import
init_db()

def cleanup_old_report_files(ticker: str, keep_latest_n: int = REPORTS_TO_KEEP) -> int:
    """
    Delete old report files for a specific ticker, keeping only the latest N.
    
    Args:
        ticker: Stock ticker symbol
        keep_latest_n: Number of latest report files to keep
    
    Returns:
        Number of files deleted
    """
    from pathlib import Path
    import re
    
    reports_dir = Path("reports")
    if not reports_dir.exists():
        return 0
    
    # Find all files for this ticker (pattern: TICKER_YYYYMMDD_HHMMSS.md)
    pattern = re.compile(rf"^{ticker.upper()}_\d{{8}}_\d{{6}}\.md$")
    ticker_files = sorted(
        [f for f in reports_dir.iterdir() if pattern.match(f.name)],
        key=lambda x: x.stat().st_mtime,
        reverse=True  # Latest first
    )
    
    # Delete all except the latest N
    files_to_delete = ticker_files[keep_latest_n:]
    for f in files_to_delete:
        f.unlink()
    
    return len(files_to_delete)


def cleanup_old_reports(ticker: str, keep_latest_n: int = REPORTS_TO_KEEP) -> int:
    """
    Delete old reports for a specific ticker, keeping only the latest N.
    Also cleans up old report files in the reports/ directory.
    
    Args:
        ticker: Stock ticker symbol
        keep_latest_n: Number of latest reports to keep (default: 3)
    
    Returns:
        Number of database reports deleted
    """
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        
        # Get IDs of reports to delete (all except latest N)
        cur.execute(
            """
            SELECT id FROM analysis_reports
            WHERE ticker = ?
            ORDER BY created_at DESC
            LIMIT -1 OFFSET ?
            """,
            (ticker.upper(), keep_latest_n)
        )
        
        ids_to_delete = [row[0] for row in cur.fetchall()]
        
        if ids_to_delete:
            placeholders = ','.join('?' * len(ids_to_delete))
            cur.execute(
                f"DELETE FROM analysis_reports WHERE id IN ({placeholders})",
                ids_to_delete
            )
            conn.commit()
    
    # Also cleanup old report files
    files_deleted = cleanup_old_report_files(ticker, keep_latest_n)
    if files_deleted > 0:
        print(f" [File Cleanup] Deleted {files_deleted} old file(s) for {ticker}")
            
    return len(ids_to_delete)


def cleanup_all_tickers(keep_latest_n: int = REPORTS_TO_KEEP) -> Dict[str, int]:
    """
    Cleanup old reports for all tickers.
    
    Args:
        keep_latest_n: Number of latest reports to keep per ticker
    
    Returns:
        Dictionary mapping ticker to number of reports deleted
    """
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        
        # Get all unique tickers
        cur.execute("SELECT DISTINCT ticker FROM analysis_reports")
        tickers = [row[0] for row in cur.fetchall()]
    
    results = {}
    for ticker in tickers:
        deleted_count = cleanup_old_reports(ticker, keep_latest_n)
        if deleted_count > 0:
            results[ticker] = deleted_count
    
    return results


def get_report_count_by_ticker(ticker: str) -> int:
    """
    Get the number of reports for a specific ticker.
    
    Args:
        ticker: Stock ticker symbol
    
    Returns:
        Number of reports for the ticker
    """
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM analysis_reports WHERE ticker = ?",
            (ticker.upper(),)
        )
        return cur.fetchone()[0]


def get_all_ticker_counts() -> List[Dict[str, Any]]:
    """
    Get report counts for all tickers.
    
    Returns:
        List of dicts with ticker and count
    """
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT ticker, COUNT(*) as count
            FROM analysis_reports
            GROUP BY ticker
            ORDER BY count DESC, ticker ASC
            """
        )
        rows = cur.fetchall()
    
    return [{"ticker": row[0], "count": row[1]} for row in rows]


def delete_all_ticker_reports(ticker: str) -> int:
    """
    Delete all reports for a specific ticker.
    
    Args:
        ticker: Stock ticker symbol
    
    Returns:
        Number of reports deleted
    """
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM analysis_reports WHERE ticker = ?",
            (ticker.upper(),)
        )
        deleted = cur.rowcount
        conn.commit()
        
    return deleted



async def save_analysis_to_memory(
    session_id: str,
    user_id: str,
    ticker: str,
    report: str,
    auto_cleanup: bool = True,
) -> None:
    """
    Persist a completed analysis report.
    
    Args:
        session_id: Unique session identifier
        user_id: User identifier
        ticker: Stock ticker symbol
        report: Analysis report content
        auto_cleanup: Whether to automatically cleanup old reports (default: True)
    """
    ticker = ticker.upper()
    
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()

        cur.execute(
            """
            INSERT OR REPLACE INTO analysis_reports
            (session_id, user_id, ticker, report)
            VALUES (?, ?, ?, ?)
            """,
            (session_id, user_id, ticker, report),
        )

        conn.commit()
    
    # Automatic cleanup: keep only latest N reports per ticker
    if auto_cleanup:
        deleted_count = cleanup_old_reports(ticker, REPORTS_TO_KEEP)
        if deleted_count > 0:
            print(f" [DB Cleanup] Deleted {deleted_count} old report(s) for {ticker}, keeping latest {REPORTS_TO_KEEP}")



def get_latest_reports(user_id: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Return metadata for recent reports for a user (optional helper)."""
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT session_id, ticker, created_at
            FROM analysis_reports
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (user_id, limit),
        )

        rows = cur.fetchall()

    return [
        {"session_id": r[0], "ticker": r[1], "created_at": r[2]}
        for r in rows
    ]


def get_report(session_id: str) -> Optional[str]:
    """Fetch a saved report by session_id."""
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()

        cur.execute(
            "SELECT report FROM analysis_reports WHERE session_id = ?",
            (session_id,),
        )
        row = cur.fetchone()

    if row:
        return row[0]
    return None
