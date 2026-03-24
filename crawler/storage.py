import sqlite3
from contextlib import contextmanager


def init_db(db_path: str):
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")

    conn.execute("""
    CREATE TABLE IF NOT EXISTS jobs (
        job_id INTEGER PRIMARY KEY AUTOINCREMENT,
        origin TEXT NOT NULL,
        max_depth INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'running',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS pages (
        url TEXT PRIMARY KEY,
        content TEXT,
        fetched_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS discoveries (
        job_id INTEGER NOT NULL,
        url TEXT NOT NULL,
        origin TEXT NOT NULL,
        depth INTEGER NOT NULL,
        PRIMARY KEY (job_id, url),
        FOREIGN KEY (job_id) REFERENCES jobs(job_id)
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS inverted_index (
        term TEXT NOT NULL,
        url TEXT NOT NULL,
        freq INTEGER NOT NULL DEFAULT 1,
        PRIMARY KEY (term, url)
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS frontier (
        job_id INTEGER NOT NULL,
        url TEXT NOT NULL,
        depth INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        PRIMARY KEY (job_id, url),
        FOREIGN KEY (job_id) REFERENCES jobs(job_id)
    )
    """)

    conn.execute("CREATE INDEX IF NOT EXISTS idx_inverted_term ON inverted_index(term)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_discoveries_url ON discoveries(url)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_frontier_status ON frontier(status)")

    conn.execute("""
    CREATE TABLE IF NOT EXISTS logs (
        log_id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id INTEGER NOT NULL,
        level TEXT NOT NULL DEFAULT 'INFO',
        message TEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (job_id) REFERENCES jobs(job_id)
    )
    """)
    
    conn.commit()
    return conn


def get_connection(db_path: str):
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection):
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise