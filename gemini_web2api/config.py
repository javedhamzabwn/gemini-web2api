"""Configuration management."""
import json
import os
import threading
import random
import time

from .database import set_rate_limit, get_all_accounts, get_account_by_name, get_account_by_api_key

DEFAULT_CONFIG = {
    "port": 10012,
    "host": "0.0.0.0",
    "retry_attempts": 3,
    "retry_delay_sec": 2,
    "request_timeout_sec": 180,
    "gemini_bl": "boq_assistant-bard-web-server_20260716.08_p0",
    "auth_user": None,
    "xsrf_token": None,
    "default_model": "gemini-3.8-flash",
    "log_requests": True,
    "cookie_file": None,
    "proxy": None,
    "api_keys": [],
    "temporary_chats": True,
    "accounts": [],
}

CONFIG = dict(DEFAULT_CONFIG)


def load_config(path: str = None):
    """Load config from JSON file."""
    if path and os.path.exists(path):
        with open(path) as f:
            CONFIG.update(json.load(f))
    return CONFIG


def save_config(path: str = "config.json"):
    """Save current config back to JSON file."""
    with open(path, "w") as f:
        json.dump(CONFIG, f, indent=4)


def find_config():
    """Search for config file in standard locations."""
    for p in ["./config.json", os.path.expanduser("~/.config/gemini-web2api/config.json")]:
        if os.path.exists(p):
            return p
    return None


_local = threading.local()

def mark_account_rate_limited(name: str, duration_sec=3600):
    if name:
        cooldown_until = time.time() + duration_sec
        set_rate_limit(name, cooldown_until)
        print(f"[-] Account '{name}' rate-limited. Put on cooldown for {duration_sec} seconds.")

def set_current_account(force_name=None):
    _local.forced = bool(force_name)
    accounts = get_all_accounts()
    
    if not accounts:
        _local.account = {
            "cookie_file": CONFIG.get("cookie_file"),
            "auth_user": CONFIG.get("auth_user"),
            "xsrf_token": CONFIG.get("xsrf_token"),
            "name": "default"
        }
        return

    if force_name:
        for acc in accounts:
            if acc.get("name") == force_name:
                _local.account = acc
                return
        raise ValueError(f"Account '{force_name}' not found")

    now = time.time()
    available = [a for a in accounts if a.get("rate_limited_until", 0) < now]
    
    if available:
        _local.account = random.choice(available)
    else:
        # Fallback if all are rate-limited
        _local.account = random.choice(accounts)

def get_current_account():
    return getattr(_local, "account", {
        "cookie_file": CONFIG.get("cookie_file"),
        "auth_user": CONFIG.get("auth_user"),
        "xsrf_token": CONFIG.get("xsrf_token"),
        "name": "default"
    })

def is_current_account_forced():
    return getattr(_local, "forced", False)
