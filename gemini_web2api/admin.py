import json
import os
import time
import urllib.request
import ssl
from .config import CONFIG, save_config, set_current_account, get_current_account
from .gemini import _build_headers, _get_ssl_ctx
from .database import get_all_accounts, add_or_update_account, delete_account_db

def verify_all_accounts():
    results = []
    accounts = get_all_accounts()
    ctx = _get_ssl_ctx()
    
    for acc in accounts:
        try:
            # Temporarily set this account
            set_current_account(acc.get("name"))
            auth_user = acc.get("auth_user") or "0"
            url = f"https://gemini.google.com/u/{auth_user}/app"
            headers = _build_headers()
            
            req = urllib.request.Request(url, headers=headers, method="GET")
            resp = urllib.request.urlopen(req, context=ctx, timeout=10)
            
            if resp.geturl() != url and "accounts.google.com" in resp.geturl():
                status = "Expired (Redirected to login)"
                valid = False
            else:
                html = resp.read().decode("utf-8", errors="ignore")
                if "WIZ_global_data" in html or "SNlM0e" in html:
                    status = "Healthy (Cookies valid)"
                    valid = True
                else:
                    status = "Invalid (Missing auth tokens)"
                    valid = False
                    
        except Exception as e:
            status = f"Error: {e}"
            valid = False
            
        results.append({
            "name": acc.get("name"),
            "auth_user": acc.get("auth_user"),
            "status": status,
            "valid": valid
        })
    return results

def get_stats():
    now = time.time()
    accounts = get_all_accounts()
    stats = []
    
    for acc in accounts:
        name = acc.get("name")
        cooldown_until = acc.get("rate_limited_until", 0) or 0
        
        is_limited = cooldown_until > now
        remaining_cooldown = int(cooldown_until - now) if is_limited else 0
        
        stats.append({
            "name": name,
            "api_key": acc.get("api_key"),
            "auth_user": acc.get("auth_user"),
            "cookie_file": acc.get("cookie_file"),
            "status": "Rate Limited" if is_limited else "Ready",
            "cooldown_seconds": remaining_cooldown
        })
        
    raw_master = CONFIG.get("api_keys") or []
    if isinstance(raw_master, str):
        raw_master = [raw_master]
    if CONFIG.get("api_key") and CONFIG.get("api_key") not in raw_master:
        raw_master.append(CONFIG.get("api_key"))
    real_master = [k.strip() for k in raw_master if k and k.strip() not in ("sk-gemini-example-key", "sk-hermes-test")]
    master_key_display = real_master[0] if real_master else "Open / Any key (Local Developer Mode)"

    return {
        "master_key": master_key_display,
        "total_accounts": len(accounts),
        "temporary_chats": CONFIG.get("temporary_chats", False),
        "accounts": stats
    }

def delete_account(name):
    return delete_account_db(name)

def handle_extension_sync(payload):
    """Handles auto-pushed cookies from the Chrome Extension across multiple browser profiles."""
    auth_user = payload.get("auth_user")
    cookie = payload.get("cookie")
    xsrf = payload.get("xsrf_token")
    sapisid = payload.get("sapisid")
    acc_name_req = payload.get("account_name")
    
    if not cookie or not xsrf:
        raise ValueError("Missing cookie or xsrf_token")
        
    accounts = get_all_accounts()
    target = None
    
    # Priority 1: Match by explicitly requested account name
    if acc_name_req:
        target = next((a for a in accounts if a.get("name") == acc_name_req), None)
        
    # Priority 2: Match by session fingerprint (SAPISID) AND auth_user
    if not target and sapisid:
        for a in accounts:
            if str(a.get("auth_user")) == str(auth_user):
                cf = a.get("cookie_file")
                if cf and os.path.exists(cf):
                    try:
                        with open(cf, "r") as f:
                            cdata = json.load(f)
                            if cdata.get("sapisid") == sapisid:
                                target = a
                                break
                    except:
                        pass
                        
    # Priority 3: Fallback if only one account exists with this auth_user
    if not target and not acc_name_req:
        matching_auth = [a for a in accounts if str(a.get("auth_user")) == str(auth_user)]
        if len(matching_auth) == 1:
            target = matching_auth[0]
            
    os.makedirs("cookies", exist_ok=True)
    
    if target:
        acc_name = target["name"]
        file_path = f"cookies/{acc_name}.json"
        with open(file_path, "w") as f:
            json.dump(payload, f)
        add_or_update_account(acc_name, auth_user, file_path, xsrf, target["api_key"])
        return f"Updated existing account {acc_name} (auth_user: {auth_user})"
    else:
        import uuid
        if acc_name_req:
            acc_name = acc_name_req
        else:
            prefix = sapisid[:4].replace("/", "_").replace("+", "_") if sapisid else "p"
            acc_name = f"AutoAcc_{prefix}_{auth_user}"
            
        file_path = f"cookies/{acc_name}.json"
        with open(file_path, "w") as f:
            json.dump(payload, f)
        api_key = f"sk-gemini-{acc_name}-{uuid.uuid4().hex[:8]}"
        add_or_update_account(acc_name, auth_user, file_path, xsrf, api_key)
        return f"Created new account {acc_name} (auth_user: {auth_user})"

# Two-way terminal-to-extension bridge state
_sync_requested = False

def request_sync():
    global _sync_requested
    _sync_requested = True
    return True

def get_sync_status():
    global _sync_requested
    status = _sync_requested
    # Auto-reset the flag after it's read by the extension
    if status:
        _sync_requested = False
    return status
