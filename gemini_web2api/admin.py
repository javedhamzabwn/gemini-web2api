import json
import os
import time
import urllib.request
import ssl
from .config import CONFIG, save_config, set_current_account, get_current_account
from .gemini import _build_headers, _get_ssl_ctx
from .database import get_all_accounts, add_or_update_account, delete_account_db, COOKIES_DIR, resolve_cookie_path

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

def _extract_cookie_dict(cookie_str: str) -> dict:
    if not cookie_str:
        return {}
    pairs = {}
    for part in cookie_str.split(";"):
        if "=" in part:
            k, v = part.strip().split("=", 1)
            pairs[k.strip()] = v.strip()
    return pairs

def _get_cookie_session_sig(cookie_str: str, sapisid: str = None) -> tuple:
    cdict = _extract_cookie_dict(cookie_str)
    psid = cdict.get("__Secure-1PSID") or cdict.get("__Secure-3PSID") or cdict.get("SID") or ""
    sap = sapisid or cdict.get("SAPISID") or ""
    return sap, psid

def handle_extension_sync(payload):
    """Handles auto-pushed cookies from the Chrome Extension across multiple browser profiles.
    Guarantees no account is unintentionally overwritten or dropped."""
    raw_auth_user = payload.get("auth_user")
    auth_user = str(raw_auth_user).strip() if (raw_auth_user is not None and str(raw_auth_user).strip() not in ("", "None", "null")) else "0"
    
    cookie = payload.get("cookie")
    xsrf = payload.get("xsrf_token")
    sapisid = payload.get("sapisid")
    acc_name_req = (payload.get("account_name") or "").strip() or None
    
    if not cookie or not xsrf:
        raise ValueError("Missing required cookie or xsrf_token")
        
    accounts = get_all_accounts()
    target = None
    
    # Extract identity signature of incoming session
    sap_in, psid_in = _get_cookie_session_sig(cookie, sapisid)
    
    # Priority 1: Match by explicitly requested account name
    if acc_name_req:
        target = next((a for a in accounts if a.get("name") == acc_name_req), None)
        
    # Priority 2: Match by session identity signature against existing saved cookies
    if not target and not acc_name_req:
        for a in accounts:
            cf = resolve_cookie_path(a.get("cookie_file"))
            if cf and os.path.exists(cf):
                try:
                    with open(cf, "r", encoding="utf-8") as f:
                        content = f.read().strip()
                    if content.startswith("{"):
                        cdata = json.loads(content)
                        exist_cookie = cdata.get("cookie", "")
                        exist_sapisid = cdata.get("sapisid", "")
                    else:
                        exist_cookie = content
                        exist_sapisid = ""
                    
                    exist_sap, exist_psid = _get_cookie_session_sig(exist_cookie, exist_sapisid)
                    
                    # Match condition: If PSID matches, it is definitely the same Google account!
                    if psid_in and exist_psid and psid_in == exist_psid:
                        target = a
                        break
                    # Or if SAPISID and auth_user match
                    if sap_in and exist_sap and sap_in == exist_sap and str(a.get("auth_user") or "0") == str(auth_user):
                        target = a
                        break
                except Exception:
                    pass
                    
    # Priority 3 (SAFE): NEVER blindly overwrite an account just because auth_user matches!
    # If no explicit name match and no session signature match, this is a distinct account.
    
    os.makedirs(COOKIES_DIR, exist_ok=True)
    
    import uuid
    if target:
        acc_name = target["name"]
        file_path = os.path.join(COOKIES_DIR, f"{acc_name}.json")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        add_or_update_account(acc_name, auth_user, file_path, xsrf, target.get("api_key"))
        return f"Updated existing account '{acc_name}' (auth_user: {auth_user})"
    else:
        if acc_name_req:
            acc_name = acc_name_req
        else:
            # Generate deterministic yet unique friendly name
            prefix = (sap_in[:6] if sap_in else (psid_in[:6] if psid_in else uuid.uuid4().hex[:6])).replace("/", "_").replace("+", "_").replace("=", "")
            base_name = f"Account_u{auth_user}_{prefix}"
            existing_names = {a.get("name") for a in accounts}
            acc_name = base_name
            counter = 2
            while acc_name in existing_names:
                acc_name = f"{base_name}_{counter}"
                counter += 1
            
        file_path = os.path.join(COOKIES_DIR, f"{acc_name}.json")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
            
        api_key = f"sk-gemini-{acc_name}-{uuid.uuid4().hex[:8]}"
        add_or_update_account(acc_name, auth_user, file_path, xsrf, api_key)
        return f"Created new account '{acc_name}' (auth_user: {auth_user})"

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
