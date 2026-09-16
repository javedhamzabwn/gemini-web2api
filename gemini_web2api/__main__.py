"""Entry point: python -m gemini_web2api"""
import argparse
import os
import json

from .config import CONFIG, load_config, save_config, find_config
from .models import MODELS
from .gemini import HAS_HTTPX
from .server import GeminiHandler, ThreadedServer
from . import __version__


from .database import init_db, add_or_update_account, get_all_accounts

def interactive_add_account(config_path):
    print("=== Add a Gemini Account ===")
    cookie_file = input("Enter path to cookie file or exported JSON (e.g. gemini-auth.json): ").strip()
    
    default_auth = ""
    default_xsrf = ""
    if cookie_file and os.path.exists(cookie_file):
        try:
            with open(cookie_file, "r") as f:
                data = json.load(f)
                default_auth = data.get("auth_user") or ""
                default_xsrf = data.get("xsrf_token") or ""
        except:
            pass
            
    auth_prompt = f"Enter auth_user (default: {default_auth}): " if default_auth else "Enter auth_user (leave blank if default): "
    auth_user = input(auth_prompt).strip()
    if not auth_user and default_auth:
        auth_user = default_auth
        
    xsrf_prompt = f"Enter xsrf_token (default: {default_xsrf[:10]}...): " if default_xsrf else "Enter xsrf_token (leave blank if none): "
    xsrf_token = input(xsrf_prompt).strip()
    if not xsrf_token and default_xsrf:
        xsrf_token = default_xsrf
        
    import uuid
    acc_name = f"Acc_{uuid.uuid4().hex[:4]}"
    api_key = generate_api_key(acc_name)
    add_or_update_account(acc_name, auth_user, cookie_file, xsrf_token, api_key)
    print(f"Account added successfully! API Key: {api_key}")


def generate_api_key(acc_name):
    import uuid
    safe_name = "".join(c if c.isalnum() else "" for c in acc_name)
    return f"sk-gemini-{safe_name}-{uuid.uuid4().hex[:8]}"

def batch_import_accounts(config_path, folder_path):
    print(f"=== Batch Import Accounts from {folder_path} ===")
    if not os.path.exists(folder_path):
        print(f"Error: Folder '{folder_path}' does not exist.")
        return
        
    imported = 0
    updated = 0
    for filename in os.listdir(folder_path):
        if filename.endswith(".json"):
            filepath = os.path.join(folder_path, filename)
            try:
                with open(filepath, "r") as f:
                    data = json.load(f)
                
                auth_user = data.get("auth_user") or None
                xsrf_token = data.get("xsrf_token") or None
                acc_name = filename.replace(".json", "")
                
                add_or_update_account(acc_name, auth_user, filepath, xsrf_token, generate_api_key(acc_name))
                imported += 1
                print(f"Imported/Updated: {filename}")
            except Exception as e:
                print(f"Failed to parse {filename}: {e}")
                
    if imported > 0:
        print(f"\nSuccess! Imported {imported} accounts to SQLite database.")

def show_apis():
    accounts = get_all_accounts()
    print("=== Gemini Web2API Active Accounts (SQLite) ===")
    print(f"Master API Key: {CONFIG.get('api_key', 'Not set')}\n")
    for acc in accounts:
        print(f"Account: {acc.get('name')}")
        print(f"API Key: {acc.get('api_key')}")
        print(f"Cookie:  {acc.get('cookie_file')}")
        print("-" * 40)
    if not accounts:
        print("No accounts tracked yet. Run --import-cookies first.")


def main():
    parser = argparse.ArgumentParser(description="Gemini Web to OpenAI API")
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--config", type=str, default=None)
    parser.add_argument("--cookie-file", type=str, default=None)
    parser.add_argument("--proxy", type=str, default=None, help="HTTP proxy, e.g. http://127.0.0.1:7890")
    parser.add_argument("--add-account", action="store_true", help="Interactively add a new Gemini account to config")
    parser.add_argument("--import-cookies", type=str, metavar="FOLDER", help="Batch import all .json cookie files from a folder")
    parser.add_argument("--show-apis", action="store_true", help="Show all currently active API keys and their accounts")
    parser.add_argument("--version", action="version", version=f"gemini-web2api {__version__}")
    args = parser.parse_args()

    config_path = args.config or os.environ.get("GEMINI_WEB2API_CONFIG") or find_config()
    if config_path:
        load_config(config_path)

    init_db()
    
    # Migrate from config.json to SQLite
    old_accounts = CONFIG.get("accounts", [])
    if old_accounts:
        print("Migrating old accounts to SQLite...")
        for acc in old_accounts:
            add_or_update_account(
                acc.get("name"), acc.get("auth_user"), 
                acc.get("cookie_file"), acc.get("xsrf_token"), 
                acc.get("api_key") or generate_api_key(acc.get("name"))
            )
        # Clear them out so we don't migrate again
        CONFIG["accounts"] = []
        save_config(config_path)

    if args.show_apis:
        show_apis()
        return

    if args.add_account:
        interactive_add_account(config_path)
        return
        
    if args.import_cookies:
        batch_import_accounts(config_path, args.import_cookies)
        return

    if args.port:
        CONFIG["port"] = args.port
    if args.cookie_file:
        CONFIG["cookie_file"] = args.cookie_file
    if args.proxy:
        CONFIG["proxy"] = args.proxy

    port = CONFIG["port"]
    server = ThreadedServer((CONFIG["host"], port), GeminiHandler)
    
    accounts = get_all_accounts()
    accounts_count = len(accounts)
    if accounts_count == 0 and CONFIG.get("cookie_file"):
        accounts_count = 1
        
    print(f"gemini-web2api v{__version__}")
    print(f"  Listening: http://0.0.0.0:{port}")
    print(f"  Base URL:  http://localhost:{port}/v1")
    print(f"  Models:    {', '.join(MODELS.keys())}")
    print(f"  Accounts:  {accounts_count} configured")
    print(f"  Proxy:     {CONFIG.get('proxy') or 'system env'}")
    print(f"  Streaming: curl_cffi (with httpx fallback)")
    print(f"  Temporary: {'yes' if CONFIG.get('temporary_chats', False) else 'no'}")
    print()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.shutdown()


if __name__ == "__main__":
    main()
