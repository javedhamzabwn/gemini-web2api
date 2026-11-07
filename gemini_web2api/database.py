import sqlite3
import os
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS_DIR = os.path.join(BASE_DIR, "logs")
COOKIES_DIR = os.path.join(BASE_DIR, "cookies")
DB_PATH = os.path.join(LOGS_DIR, "gemini.db")

def resolve_cookie_path(cookie_file: str) -> str:
    """Normalize and resolve cookie file path to an absolute path."""
    if not cookie_file:
        return ""
    if os.path.isabs(cookie_file) and os.path.exists(cookie_file):
        return cookie_file
    # Try relative to BASE_DIR
    candidate = os.path.join(BASE_DIR, cookie_file)
    if os.path.exists(candidate):
        return os.path.abspath(candidate)
    # Try in COOKIES_DIR by filename
    candidate = os.path.join(COOKIES_DIR, os.path.basename(cookie_file))
    if os.path.exists(candidate):
        return os.path.abspath(candidate)
    if os.path.exists(cookie_file):
        return os.path.abspath(cookie_file)
    # Fallback to absolute path in COOKIES_DIR even if file doesn't exist yet
    return os.path.abspath(os.path.join(COOKIES_DIR, os.path.basename(cookie_file)))

def get_connection():
    os.makedirs(LOGS_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    c = conn.cursor()
    
    # Create accounts table
    c.execute('''
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            auth_user TEXT,
            cookie_file TEXT,
            xsrf_token TEXT,
            api_key TEXT UNIQUE,
            created_at REAL
        )
    ''')
    
    # Create account_state table
    c.execute('''
        CREATE TABLE IF NOT EXISTS account_state (
            account_id INTEGER PRIMARY KEY,
            rate_limited_until REAL DEFAULT 0,
            total_requests INTEGER DEFAULT 0,
            total_tokens INTEGER DEFAULT 0,
            FOREIGN KEY (account_id) REFERENCES accounts (id) ON DELETE CASCADE
        )
    ''')
    
    conn.commit()
    conn.close()

def get_account_by_name(name):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM accounts WHERE name = ?", (name,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def get_account_by_api_key(api_key):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM accounts WHERE api_key = ?", (api_key,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def get_all_accounts():
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        SELECT a.*, s.rate_limited_until, s.total_requests, s.total_tokens 
        FROM accounts a 
        LEFT JOIN account_state s ON a.id = s.account_id
    ''')
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

def add_or_update_account(name, auth_user, cookie_file, xsrf_token, api_key=None):
    conn = get_connection()
    c = conn.cursor()
    
    resolved_cf = resolve_cookie_path(cookie_file) if cookie_file else None
    
    c.execute("SELECT id, api_key FROM accounts WHERE name = ?", (name,))
    existing = c.fetchone()
    
    if existing:
        final_key = api_key or existing["api_key"]
        c.execute('''
            UPDATE accounts 
            SET auth_user=?, cookie_file=?, xsrf_token=?, api_key=?
            WHERE name=?
        ''', (auth_user, resolved_cf, xsrf_token, final_key, name))
    else:
        import uuid
        final_key = api_key or f"sk-gemini-{name}-{uuid.uuid4().hex[:8]}"
        # Ensure final_key is unique across all accounts
        c.execute("SELECT id FROM accounts WHERE api_key = ?", (final_key,))
        if c.fetchone():
            final_key = f"{final_key}-{uuid.uuid4().hex[:4]}"
            
        c.execute('''
            INSERT INTO accounts (name, auth_user, cookie_file, xsrf_token, api_key, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (name, auth_user, resolved_cf, xsrf_token, final_key, time.time()))
        
        account_id = c.lastrowid
        c.execute("INSERT OR IGNORE INTO account_state (account_id) VALUES (?)", (account_id,))
        
    conn.commit()
    conn.close()

def delete_account_db(name):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM accounts WHERE name = ?", (name,))
    deleted = c.rowcount > 0
    conn.commit()
    conn.close()
    return deleted

def set_rate_limit(name, cooldown_until):
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        UPDATE account_state 
        SET rate_limited_until = ? 
        WHERE account_id = (SELECT id FROM accounts WHERE name = ?)
    ''', (cooldown_until, name))
    conn.commit()
    conn.close()

# Initialize DB on module load
init_db()
