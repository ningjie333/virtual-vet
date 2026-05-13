"""SQLite connection manager."""

from pathlib import Path
import sqlite3


def connect(db_path: str | Path) -> sqlite3.Connection:
    """
    Open a SQLite connection with WAL journal mode and foreign keys enabled.

    Args:
        db_path: Path to the .db file (directories are created as needed).

    Returns:
        A configured sqlite3.Connection with Row factory.
    """
    p = Path(db_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn