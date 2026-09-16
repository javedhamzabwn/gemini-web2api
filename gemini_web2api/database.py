import sqlite3
import os
import time

DB_PATH = "logs/gemini.db"

def get_connection():
    os.makedirs("logs", exist_ok=True)
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

def add_or_update_account(name, auth_user, cookie_file, xsrf_token, api_key):
    conn = get_connection()
    c = conn.cursor()
    
    c.execute("SELECT id FROM accounts WHERE name = ?", (name,))
    existing = c.fetchone()
    
    if existing:
        c.execute('''
            UPDATE accounts 
            SET auth_user=?, cookie_file=?, xsrf_token=?, api_key=?
            WHERE name=?
        ''', (auth_user, cookie_file, xsrf_token, api_key, name))
    else:
        c.execute('''
            INSERT INTO accounts (name, auth_user, cookie_file, xsrf_token, api_key, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (name, auth_user, cookie_file, xsrf_token, api_key, time.time()))
        
        account_id = c.lastrowid
        c.execute("INSERT INTO account_state (account_id) VALUES (?)", (account_id,))
        
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
