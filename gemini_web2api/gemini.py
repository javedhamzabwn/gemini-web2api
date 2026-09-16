"""Gemini StreamGenerate protocol implementation with curl_cffi streaming."""
import json
import time
import uuid
import random
import re
import urllib.request
import urllib.parse
import ssl
import os
import hashlib
from typing import Iterator

HAS_HTTPX = False
try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    pass

try:
    from curl_cffi import requests
    # Temporarily force-disabled to bypass DNS resolution issues on Windows
    HAS_CURL_CFFI = False
except ImportError:
    HAS_CURL_CFFI = False

from .config import CONFIG, get_current_account

_ssl_ctx = None
_cookie_cache = {}
_httpx_client = None


def log(msg: str):
    if CONFIG.get("log_requests", True):
        import sys
        import os
        
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
        formatted = f"[{timestamp}] {msg}\n"
        
        # Write to stderr
        sys.stderr.write(formatted)
        sys.stderr.flush()
        
        # Write to log file
        try:
            os.makedirs("logs", exist_ok=True)
            with open("logs/gemini_proxy.log", "a") as f:
                f.write(formatted)
        except Exception:
            pass


def _get_ssl_ctx():
    global _ssl_ctx
    if _ssl_ctx is None:
        _ssl_ctx = ssl.create_default_context()
    return _ssl_ctx


def _get_httpx_client():
    global _httpx_client
    if _httpx_client is None and HAS_HTTPX:
        proxy = CONFIG.get("proxy")
        transport = httpx.HTTPTransport(proxy=proxy) if proxy else None
        _httpx_client = httpx.Client(transport=transport, timeout=CONFIG.get("request_timeout_sec", 60), verify=True)
    return _httpx_client

def _get_session():
    if not HAS_CURL_CFFI:
        return None
    proxy = CONFIG.get("proxy")
    proxies = {"http": proxy, "https": proxy} if proxy else None
    
    # We impersonate a real Chrome browser to bypass TLS fingerprinting
    return requests.Session(
        impersonate="chrome",
        proxies=proxies,
        timeout=CONFIG.get("request_timeout_sec", 60)
    )


def load_cookie() -> tuple:
    """Load cookie from file with mtime-based caching."""
    account = get_current_account()
    cookie_file = account.get("cookie_file")
    if not cookie_file or not os.path.exists(cookie_file):
        return "", None
        
    cache_entry = _cookie_cache.setdefault(cookie_file, {"str": "", "sapisid": None, "mtime": 0})
    try:
        mtime = os.path.getmtime(cookie_file)
        if mtime == cache_entry["mtime"] and cache_entry["str"]:
            return cache_entry["str"], cache_entry["sapisid"]
        with open(cookie_file, "r") as f:
            content = f.read().strip()
        if content.startswith("{"):
            data = json.loads(content)
            cookie_str = data.get("cookie", "")
            sapisid = data.get("sapisid", "")
        else:
            cookie_str = content
            pairs = dict(p.split("=", 1) for p in cookie_str.split("; ") if "=" in p)
            sapisid = pairs.get("SAPISID", "")
        cache_entry.update({"str": cookie_str, "sapisid": sapisid or None, "mtime": mtime})
        return cookie_str, sapisid if sapisid else None
    except Exception as e:
        log(f"Cookie load error: {e}")
        return cache_entry["str"], cache_entry["sapisid"]


def make_sapisidhash(sapisid: str) -> str:
    ts = int(time.time())
    h = hashlib.sha1(f"{ts} {sapisid} https://gemini.google.com".encode()).hexdigest()
    return f"SAPISIDHASH {ts}_{h}"


def _account_prefix() -> str:
    """Return the Gemini account path prefix for non-default Google accounts."""
    account = get_current_account()
    auth_user = account.get("auth_user")
    if auth_user is None or auth_user == "":
        return ""
    return f"/u/{auth_user}"


def _build_headers() -> dict:
    account_prefix = _account_prefix()
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": "https://gemini.google.com",
        "Referer": f"https://gemini.google.com{account_prefix}/app",
        "X-Same-Domain": "1",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    if account_prefix:
        account = get_current_account()
        headers["X-Goog-AuthUser"] = str(account.get("auth_user"))
    cookie_str, sapisid = load_cookie()
    if cookie_str:
        headers["Cookie"] = cookie_str
    if sapisid:
        headers["Authorization"] = make_sapisidhash(sapisid)
    return headers


def _apply_chat_persistence_flags(inner: list) -> None:
    """Apply Gemini Web persistence flags to an outgoing request payload."""
    if CONFIG.get("temporary_chats", False):
        # Match Gemini Web temporary-chat requests.
        inner[41] = [1]
        inner[45] = 1
    else:
        inner[41] = [2]


def _build_payload(prompt: str, model_id: int, think_mode: int, file_refs: list = None, extra_fields: dict = None) -> str:
    inner = [None] * 102
    if file_refs:
        refs = [[None, None, ref] for ref in file_refs]
        inner[0] = [prompt, 0, None, refs, None, None, 0]
    else:
        inner[0] = [prompt, 0, None, None, None, None, 0]
    inner[1] = ["en"]
    inner[2] = ["", "", "", None, None, None, None, None, None, ""]
    inner[6] = [0]
    inner[7] = 1
    inner[10] = 1
    inner[11] = 0
    inner[17] = [[think_mode]]
    inner[18] = 0
    inner[27] = 1
    inner[30] = [4]
    _apply_chat_persistence_flags(inner)
    inner[53] = 0
    inner[59] = str(uuid.uuid4())
    inner[61] = []
    inner[68] = 1
    inner[79] = model_id
    if extra_fields:
        for k, v in extra_fields.items():
            inner[k] = v
    outer = [None, json.dumps(inner)]
    params = {"f.req": json.dumps(outer)}
    account = get_current_account()
    if account.get("xsrf_token"):
        params["at"] = account.get("xsrf_token")
    return urllib.parse.urlencode(params)


def _get_url() -> str:
    reqid = int(time.time()) % 1000000
    account_prefix = _account_prefix()
    return (
        f"https://gemini.google.com{account_prefix}/_/BardChatUi/data/"
        "assistant.lamda.BardFrontendService/StreamGenerate"
        f"?bl={CONFIG['gemini_bl']}&hl=en&_reqid={reqid}&rt=c"
    )


def clean_text(text: str, strip: bool = True) -> str:
    text = re.sub(
        r'```(?:python|javascript|text)\?code_(?:reference|stdout)&code_event_index=\d+\n.*?```\n?',
        '', text, flags=re.DOTALL
    )
    text = re.sub(r'http://googleusercontent\.com/card_content/\d+\n?', '', text)
    return text.strip() if strip else text


def _extract_texts_from_line(line: str) -> list:
    """Parse a single wrb.fr line and return list of text strings found."""
    if '"wrb.fr"' not in line or len(line) < 200:
        return []
    try:
        arr = json.loads(line)
        inner_str = arr[0][2]
        if not inner_str or len(inner_str) < 50:
            return []
        inner = json.loads(inner_str)
        if not (isinstance(inner, list) and len(inner) > 4 and inner[4]):
            return []
        texts = []
        for part in inner[4]:
            if isinstance(part, list) and len(part) > 1 and part[1] and isinstance(part[1], list):
                for t in part[1]:
                    if isinstance(t, str) and t:
                        texts.append(t)
                        
        # Attempt to recursively extract generated image URLs (googleusercontent)
        def find_images(obj, found):
            if isinstance(obj, list):
                if len(obj) >= 3 and isinstance(obj[0], str) and obj[0].startswith("https://") and "googleusercontent.com" in obj[0]:
                    # Heuristic: [url, [width, height], ...]
                    if isinstance(obj[1], list) and len(obj[1]) == 2 and isinstance(obj[1][0], int):
                        found.append(obj[0])
                for item in obj:
                    find_images(item, found)
            elif isinstance(obj, dict):
                for v in obj.values():
                    find_images(v, found)
        
        images = []
        find_images(inner, images)
        if images:
            # Append markdown images to the text
            img_md = "\n\n" + "\n".join([f"![Generated Image]({url})" for url in images])
            if texts:
                texts[-1] += img_md
            else:
                texts.append(img_md)
                
        return texts
    except (json.JSONDecodeError, IndexError, TypeError):
        return []


def extract_response_text(raw: str) -> str:
    """Parse full response to get final text."""
    bard_err = re.search(r'BardErrorInfo\s*\[(\d+)\]', raw)
    if bard_err:
        raise RuntimeError(f"Gemini upstream rejected request: BardErrorInfo [{bard_err.group(1)}]")
    last_text = ""
    for line in raw.split("\n"):
        for t in _extract_texts_from_line(line):
            if len(t) > len(last_text):
                last_text = t
    return clean_text(last_text)


def generate(prompt: str, model_id: int, think_mode: int, file_refs: list = None, extra_fields: dict = None, images: list = None) -> str:
    """Non-streaming generation with curl_cffi / urllib retry."""
    session = _get_session()
    ctx = _get_ssl_ctx()

    last_err = None
    for attempt in range(CONFIG["retry_attempts"]):
        prompt = optimize_payload(prompt, attempt)
        try:
            if images:
                from .multimodal import upload_images
                file_refs = upload_images(images)
                
            body = _build_payload(prompt, model_id, think_mode, file_refs, extra_fields)
            url = _get_url()
            headers = _build_headers()
            
            if session:
                resp = session.post(url, data=body, headers=headers)
                if resp.status_code != 200:
                    raise RuntimeError(f"HTTP Error {resp.status_code}: {resp.text}")
                raw = resp.content.decode("utf-8", errors="replace")
            else:
                req = urllib.request.Request(url, data=body.encode(), headers=headers, method="POST")
                proxy = CONFIG.get("proxy")
                if proxy:
                    opener = urllib.request.build_opener(
                        urllib.request.ProxyHandler({"http": proxy, "https": proxy}),
                        urllib.request.HTTPSHandler(context=ctx)
                    )
                    resp = opener.open(req, timeout=CONFIG.get("request_timeout_sec", 60))
                else:
                    resp = urllib.request.urlopen(req, context=ctx, timeout=CONFIG.get("request_timeout_sec", 60))
                raw = resp.read().decode("utf-8", errors="replace")
                
            return extract_response_text(raw)
        except Exception as e:
            last_err = e
            if session and "Could not resolve host" in str(e) or "Failed to perform" in str(e):
                log("curl_cffi failed, falling back to httpx engine for next retry...")
                session = None
            err_str = str(e)
            if "BardErrorInfo" in err_str or "429" in err_str or "HTTP Error" in err_str:
                from .config import mark_account_rate_limited, set_current_account, get_current_account, is_current_account_forced
                if is_current_account_forced():
                    raise RuntimeError("Forced account is currently rate-limited. Please wait or select auto.")
                acc_name = get_current_account().get("name")
                if acc_name:
                    mark_account_rate_limited(acc_name, 3600)
                try:
                    set_current_account() # Pick new account
                except:
                    pass
            if attempt < CONFIG["retry_attempts"] - 1:
                log(f"Retry {attempt+1}/{CONFIG['retry_attempts']}: {e}")
                time.sleep(CONFIG["retry_delay_sec"])
    raise last_err


def optimize_payload(prompt: str, attempt: int) -> str:
    if attempt > 0 and len(prompt) > 20000:
        import re
        prompt = re.sub(r'\n{3,}', '\n\n', prompt)
    return prompt

def generate_stream(prompt: str, model_id: int, think_mode: int, file_refs: list = None, extra_fields: dict = None, images: list = None):
    """Streaming generation with curl_cffi / httpx retry."""
    session = _get_session()
    client = _get_httpx_client() if not session else None
    
    if not session and not client:
        text = generate(prompt, model_id, think_mode, file_refs, extra_fields, images)
        if text:
            yield text
        return

    last_err = None
    emitted_raw_text = ""
    for attempt in range(CONFIG["retry_attempts"]):
        prompt = optimize_payload(prompt, attempt)
        
        if images:
            from .multimodal import upload_images
            file_refs = upload_images(images)
            
        body = _build_payload(prompt, model_id, think_mode, file_refs, extra_fields)
        url = _get_url()
        headers = _build_headers()
        try:
            if session:
                resp = session.post(url, data=body, headers=headers, stream=True)
                try:
                    if resp.status_code != 200:
                        raise RuntimeError(f"HTTPStatusError: {resp.status_code}")
                    buf = ""
                    for chunk in resp.iter_content():
                        if chunk:
                            buf += chunk.decode('utf-8', errors='replace')
                            if "BardErrorInfo" in buf:
                                bard_err = re.search(r'BardErrorInfo\s*\[(\d+)\]', buf)
                                if bard_err:
                                    raise RuntimeError(f"Gemini upstream rejected request: BardErrorInfo [{bard_err.group(1)}]")
                            while "\n" in buf:
                                line, buf = buf.split("\n", 1)
                                for t in _extract_texts_from_line(line):
                                    if t == emitted_raw_text or emitted_raw_text.startswith(t):
                                        continue
                                    if not t.startswith(emitted_raw_text):
                                        raise RuntimeError("Gemini stream content changed during retry")
                                    delta = clean_text(t[len(emitted_raw_text):], strip=False)
                                    emitted_raw_text = t
                                    if delta:
                                        yield delta
                finally:
                    resp.close()
            elif client:
                with client.stream("POST", url, content=body.encode(), headers=headers) as resp:
                    resp.raise_for_status()
                    buf = ""
                    for chunk in resp.iter_text():
                        buf += chunk
                        if "BardErrorInfo" in buf:
                            bard_err = re.search(r'BardErrorInfo\s*\[(\d+)\]', buf)
                            if bard_err:
                                raise RuntimeError(f"Gemini upstream rejected request: BardErrorInfo [{bard_err.group(1)}]")
                        while "\n" in buf:
                            line, buf = buf.split("\n", 1)
                            for t in _extract_texts_from_line(line):
                                if t == emitted_raw_text or emitted_raw_text.startswith(t):
                                    continue
                                if not t.startswith(emitted_raw_text):
                                    raise RuntimeError("Gemini stream content changed during retry")
                                delta = clean_text(t[len(emitted_raw_text):], strip=False)
                                emitted_raw_text = t
                                if delta:
                                    yield delta
            return
        except Exception as e:
            last_err = e
            # If curl_cffi throws a DNS or fatal network error, seamlessly fallback to httpx for the next retry attempt
            if session and "Could not resolve host" in str(e) or "Failed to perform" in str(e):
                log("curl_cffi failed, falling back to httpx engine for next retry...")
                session = None
                client = _get_httpx_client()
            err_str = str(e)
            if "BardErrorInfo" in err_str or "429" in err_str or "HTTPStatusError" in err_str:
                from .config import mark_account_rate_limited, set_current_account, get_current_account, is_current_account_forced
                if is_current_account_forced():
                    raise RuntimeError("Forced account is currently rate-limited. Please wait or select auto.")
                    
                acc_name = get_current_account().get("name")
                if acc_name:
                    mark_account_rate_limited(acc_name, 3600)
                try:
                    set_current_account()
                except:
                    pass
            if attempt < CONFIG["retry_attempts"] - 1:
                log(f"Stream retry {attempt+1}/{CONFIG['retry_attempts']}: {e}")
                time.sleep(CONFIG["retry_delay_sec"])
    raise last_err
