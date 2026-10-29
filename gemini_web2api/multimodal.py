"""Multimodal: Scotty resumable upload for Gemini image input."""
import json
import base64
import urllib.request
import urllib.parse
import time
import ssl
import re
from urllib.parse import urlparse

from .config import CONFIG
from .gemini import load_cookie, make_sapisidhash, _get_ssl_ctx, log

# Google internal Scotty upload authorization fallback
DEFAULT_UPLOAD_AUTH = "Basic c2F2ZXM6cyNMdGhlNmxzd2F2b0RsN3J1d1U="


def _get_page_tokens() -> dict:
    """Fetch WIZ_global_data tokens from Gemini page (Push-ID, X-Client-Pctx)."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    cookie_str, sapisid = load_cookie()
    if cookie_str:
        headers["Cookie"] = cookie_str
    if sapisid:
        headers["Authorization"] = make_sapisidhash(sapisid)
    else:
        headers["Authorization"] = DEFAULT_UPLOAD_AUTH

    try:
        from .config import get_current_account
        account = get_current_account()
        auth_user = account.get("auth_user")
        prefix = f"/u/{auth_user}" if auth_user else ""
        req = urllib.request.Request(f"https://gemini.google.com{prefix}/app", headers=headers)
        proxy = CONFIG.get("proxy")
        if proxy:
            opener = urllib.request.build_opener(
                urllib.request.ProxyHandler({"http": proxy, "https": proxy}),
                urllib.request.HTTPSHandler(context=_get_ssl_ctx()),
            )
            resp = opener.open(req, timeout=30)
        else:
            resp = urllib.request.urlopen(req, context=_get_ssl_ctx(), timeout=30)
        html = resp.read().decode("utf-8", errors="ignore")
        tokens = {}
        for key, pattern in [
            ("push_id", r'"qKIAYe":"([^"]+)"'),
            ("pctx", r'"Ylro7b":"([^"]+)"'),
            ("at", r'"thykhd":"([^"]+)"'),
        ]:
            m = re.search(pattern, html)
            if m:
                tokens[key] = m.group(1)
        return tokens
    except Exception as e:
        log(f"Page token fetch failed: {e}")
        return {}


_page_tokens_cache = {}


def _cached_page_tokens() -> dict:
    now = time.time()
    from .config import get_current_account
    account = get_current_account()
    cookie_file = account.get("cookie_file") or "default"
    
    cache_entry = _page_tokens_cache.setdefault(cookie_file, {"tokens": {}, "ts": 0})
    if now - cache_entry["ts"] > 600:
        cache_entry["tokens"] = _get_page_tokens()
        cache_entry["ts"] = now
    return cache_entry["tokens"]


def detect_image_mime(image_bytes: bytes, fallback: str = "image/png") -> str:
    """Infer a common raster image MIME type from its file signature."""
    if not isinstance(image_bytes, bytes):
        return fallback
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if image_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if image_bytes.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if image_bytes.startswith(b"RIFF") and len(image_bytes) >= 12 and image_bytes[8:12] == b"WEBP":
        return "image/webp"
    if image_bytes.startswith(b"BM"):
        return "image/bmp"
    if image_bytes.startswith((b"II*\x00", b"MM\x00*")):
        return "image/tiff"
    if len(image_bytes) >= 12 and image_bytes[4:8] == b"ftyp":
        brand = image_bytes[8:12]
        if brand in (b"avif", b"avis"):
            return "image/avif"
        if brand in (b"heic", b"heix", b"hevc", b"hevx"):
            return "image/heic"
    return fallback


def upload_image(image_bytes: bytes, filename: str = "image.png", mime_type: str = "image/png") -> str:
    """Upload image via Scotty resumable upload. Returns file reference path."""
    tokens = _cached_page_tokens()
    push_id = tokens.get("push_id", "feeds/mcudyrk2a4khkz")
    pctx = tokens.get("pctx", "CgcSBWjK7pYx")

    cookie_str, sapisid = load_cookie()
    ctx = _get_ssl_ctx()
    proxy = CONFIG.get("proxy")

    # Step 1: Initiate resumable upload
    start_headers = {
        "Push-ID": push_id,
        "X-Tenant-Id": "bard-storage",
        "X-Client-Pctx": pctx,
        "X-Goog-Upload-Header-Content-Length": str(len(image_bytes)),
        "X-Goog-Upload-Header-Content-Type": mime_type,
        "X-Goog-Upload-Protocol": "resumable",
        "X-Goog-Upload-Command": "start",
        "Content-Type": "application/x-www-form-urlencoded;charset=utf-8",
        "Origin": "https://gemini.google.com",
        "Referer": "https://gemini.google.com/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }
    if cookie_str:
        start_headers["Cookie"] = cookie_str
    if sapisid:
        start_headers["Authorization"] = make_sapisidhash(sapisid)
    else:
        start_headers["Authorization"] = DEFAULT_UPLOAD_AUTH

    start_url = "https://content-push.googleapis.com/upload/"
    req = urllib.request.Request(start_url, data=b"", headers=start_headers, method="POST")

    if proxy:
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": proxy, "https": proxy}),
            urllib.request.HTTPSHandler(context=ctx)
        )
        resp = opener.open(req, timeout=30)
    else:
        resp = urllib.request.urlopen(req, context=ctx, timeout=30)

    upload_url = resp.headers.get("X-Goog-Upload-URL") or resp.headers.get("x-goog-upload-url")
    if not upload_url:
        raise RuntimeError(f"No upload URL in response headers: {dict(resp.headers)}")

    log(f"Upload session started: {upload_url[:80]}...")

    # Step 2: Upload file data + finalize
    upload_headers = {
        "X-Goog-Upload-Command": "upload, finalize",
        "X-Goog-Upload-Offset": "0",
        "Content-Type": mime_type or "application/octet-stream",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }

    req2 = urllib.request.Request(upload_url, data=image_bytes, headers=upload_headers, method="POST")
    if proxy:
        resp2 = opener.open(req2, timeout=60)
    else:
        resp2 = urllib.request.urlopen(req2, context=ctx, timeout=60)

    file_ref = resp2.read().decode("utf-8", errors="ignore").strip()
    if not file_ref or not file_ref.startswith("/"):
        raise RuntimeError(f"Invalid file reference: {file_ref[:100]}")

    log(f"Image uploaded successfully: {filename} -> {file_ref[:50]}...")
    return file_ref


def upload_images(images: list) -> list:
    """Upload list of images and return list of file references. Returns None if no images.
    
    Each item in images can be:
    - (bytes, mime_type)
    - (url_or_b64_str, mime_type)
    - dict with Claude source format: {'type': 'image', 'source': {'data': '...', 'media_type': '...'}}
    """
    if not images:
        return None
    file_refs = []
    for item in images:
        data = None
        mime = "image/png"
        
        if isinstance(item, tuple) and len(item) == 2:
            raw_data, mime = item
            if isinstance(raw_data, bytes):
                data = raw_data
            elif isinstance(raw_data, str):
                if raw_data.startswith("http://") or raw_data.startswith("https://"):
                    data = fetch_image_bytes(raw_data)
                elif raw_data.startswith("data:"):
                    # data URI: data:image/png;base64,....
                    header, b64 = raw_data.split(",", 1)
                    if ";base64" in header:
                        mime = header.split(";")[0].replace("data:", "")
                        data = base64.b64decode(b64)
                else:
                    try:
                        data = base64.b64decode(raw_data)
                    except Exception:
                        data = fetch_image_bytes(raw_data)
        elif isinstance(item, dict) and item.get("type") == "image":
            source = item.get("source", {})
            if source.get("type") == "base64":
                data = base64.b64decode(source.get("data", ""))
                mime = source.get("media_type", "image/png")
        elif isinstance(item, bytes):
            data = item
            mime = detect_image_mime(data)

        if not data:
            log(f"Warning: skipped empty or unparseable image item: {str(item)[:50]}")
            continue

        mime = detect_image_mime(data, mime or "image/png")
        try:
            ref = upload_image(data, "image.png", mime)
            file_refs.append(ref)
        except Exception as e:
            log(f"Warning: Image upload failed: {e}")
            raise RuntimeError(f"image upload failed: {e}") from e

    return file_refs if file_refs else None


def fetch_image_bytes(url: str) -> bytes:
    """Fetch image from URL."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        log(f"Image fetch skipped for unsupported URL scheme: {parsed.scheme or 'none'}")
        return b""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        proxy = CONFIG.get("proxy")
        if proxy:
            opener = urllib.request.build_opener(
                urllib.request.ProxyHandler({"http": proxy, "https": proxy}),
                urllib.request.HTTPSHandler(context=_get_ssl_ctx()),
            )
            resp = opener.open(req, timeout=30)
        else:
            resp = urllib.request.urlopen(req, context=_get_ssl_ctx(), timeout=30)
        return resp.read()
    except Exception as e:
        log(f"Image fetch failed: {e}")
        return b""
