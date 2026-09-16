"""HTTP server: OpenAI-compatible API endpoints."""
import json
import time
import sys
import threading
import uuid
import re
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

from .config import CONFIG, set_current_account
from .models import MODELS, resolve_model
from .gemini import generate, generate_stream, log
from .tools import messages_to_prompt, parse_tool_calls, google_contents_to_prompt, parse_google_function_calls
from .multimodal import detect_image_mime, fetch_image_bytes, upload_image
from .database import get_all_accounts
from .admin import verify_all_accounts, get_stats, delete_account, handle_extension_sync, request_sync, get_sync_status
from .dashboard_html import DASHBOARD_HTML
from . import __version__


def _usage(prompt: str, text: str) -> dict:
    p = len(prompt) // 4
    c = len(text or "") // 4
    return {"prompt_tokens": p, "completion_tokens": c, "total_tokens": p + c}


def _upload_images(images: list) -> list:
    """Upload images and return list of file references. Returns None if no images."""
    if not images:
        return None
    file_refs = []
    for item in images:
        if not (isinstance(item, tuple) and len(item) == 2):
            continue
        data, mime = item
        if isinstance(data, str):
            data = fetch_image_bytes(data)
            mime = mime or "image/png"
        if not data:
            raise RuntimeError("image fetch failed")
        mime = detect_image_mime(data, mime or "image/png")
        try:
            ref = upload_image(data, "image.png", mime or "image/png")
            file_refs.append(ref)
        except Exception as e:
            raise RuntimeError(f"image upload failed: {e}") from e
    return file_refs if file_refs else None


class GeminiHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        client_ip = self.client_address[0] if self.client_address else "-"
        log(f"{client_ip} {fmt % args}")

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _start_sse(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-transform")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()

    def _parse_body(self, body: bytes) -> dict:
        try:
            return json.loads(body)
        except (json.JSONDecodeError, ValueError):
            return None

    def _read_request_body(self) -> bytes:
        transfer_encoding = self.headers.get("Transfer-Encoding", "")
        if "chunked" in transfer_encoding.lower():
            chunks = []
            while True:
                size_line = self.rfile.readline()
                if not size_line:
                    break
                size_text = size_line.split(b";", 1)[0].strip()
                try:
                    size = int(size_text, 16)
                except ValueError:
                    raise ValueError("invalid chunked request body")
                if size == 0:
                    while True:
                        trailer = self.rfile.readline()
                        if trailer in (b"\r\n", b"\n", b""):
                            break
                    break
                chunks.append(self.rfile.read(size))
                self.rfile.read(2)
            return b"".join(chunks)

        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length) if length else b""

    def _authorized(self):
        keys = CONFIG.get("api_keys") or []
        if not keys:
            return True
        # Authorization: Bearer <key>
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer ") and auth[7:] in keys:
            return True
        # header keys (OpenAI x-api-key / Google x-goog-api-key)
        for h in ("x-api-key", "x-goog-api-key"):
            if self.headers.get(h, "") in keys:
                return True
        # query param ?key= (Gemini CLI native style)
        if "?" in self.path:
            for pair in self.path.split("?", 1)[1].split("&"):
                if pair.startswith("key=") and pair[4:] in keys:
                    return True
        return False

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()

    def log_message(self, format, *args):
        # Suppress extremely frequent dashboard polling logs to keep terminal clean
        if "/api/stats" in args[0] or "/api/status" in args[0]:
            return
        super().log_message(format, *args)

    def _set_headers(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()
        
    def _set_html_headers(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

    def _authenticate(self):
        """Returns (is_authorized, forced_account_name)"""
        raw_master = CONFIG.get("api_keys") or []
        if isinstance(raw_master, str):
            raw_master = [raw_master]
        if CONFIG.get("api_key") and CONFIG.get("api_key") not in raw_master:
            raw_master.append(CONFIG.get("api_key"))
            
        PLACEHOLDERS = {"sk-gemini-example-key", "sk-hermes-test", "example", ""}
        master_keys = [k.strip() for k in raw_master if k and isinstance(k, str) and k.strip()]
        has_real_master = any(k not in PLACEHOLDERS for k in master_keys)
        
        token = None
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth.split(" ", 1)[1].strip()
        else:
            for h in ("x-api-key", "x-goog-api-key"):
                val = self.headers.get(h)
                if val:
                    token = val.strip()
                    break
            if not token and "?" in self.path:
                for pair in self.path.split("?", 1)[1].split("&"):
                    if pair.startswith("key="):
                        token = pair[4:].strip()
                        break
                        
        if token:
            token = token.strip().strip('"').strip("'")
            if not token:
                token = None

        accounts = get_all_accounts()

        # 1. If token matches a specific account key or name, force that account
        if token:
            for acc in accounts:
                acc_key = (acc.get("api_key") or "").strip()
                acc_name = (acc.get("name") or "").strip()
                if (acc_key and token == acc_key) or (acc_name and token == acc_name):
                    return True, acc_name

        # 2. If real master keys are configured, check against them
        if has_real_master:
            if token and any(token == k for k in master_keys if k not in PLACEHOLDERS):
                return True, None
            return False, None

        # 3. Default developer mode: no master key set (or placeholder key used).
        # Allow any token (or no token) and auto-balance across all accounts!
        return True, None

    def do_GET(self):
        try:
            clean_path = self.path.split("?")[0].rstrip("/")
            if not clean_path:
                clean_path = "/"
                
            if clean_path in ("/dashboard", "/"):
                self._set_html_headers()
                self.wfile.write(DASHBOARD_HTML.encode("utf-8"))
                return
                
            if clean_path in ("/v1", "/v1/"):
                accounts = get_all_accounts()
                self.send_json({
                    "status": "ok",
                    "service": "Gemini Web2API Gateway",
                    "version": __version__,
                    "active_accounts": len(accounts),
                    "endpoints": {
                        "models": "/v1/models",
                        "chat": "/v1/chat/completions"
                    },
                    "note": "Gateway is online and ready for OpenAI-compatible clients."
                })
                return

            if clean_path == "/favicon.ico":
                self.send_response(204)
                self.end_headers()
                return
                
            if clean_path == "/api/stats":
                self._set_headers()
                self.wfile.write(json.dumps(get_stats()).encode("utf-8"))
                return
                
            if clean_path == "/api/status":
                self._set_headers()
                self.wfile.write(json.dumps({"sync_requested": get_sync_status()}).encode("utf-8"))
                return

            if clean_path == "/api/check":
                self._set_headers()
                self.wfile.write(json.dumps(verify_all_accounts()).encode("utf-8"))
                return
                
            is_auth, force_acc = self._authenticate()
            if not is_auth:
                self.send_json({"error": {"message": "invalid api key"}}, 401)
                return
                
            set_current_account(force_acc)
            
            if clean_path in ("/v1/models", "/models", "/api/models"):
                models_list = []
                for n, c in MODELS.items():
                    models_list.append({
                        "id": n,
                        "object": "model",
                        "created": 1700000000,
                        "owned_by": "google",
                        "permission": [],
                        "root": n,
                        "parent": None,
                        "description": f"[{force_acc}] {c['desc']}" if force_acc else c["desc"]
                    })
                
                # If auto-routing, also offer auto/ and per-account prefixes
                if not force_acc:
                    for n, c in list(MODELS.items())[:6]:
                        models_list.append({
                            "id": f"auto/{n}",
                            "object": "model",
                            "created": 1700000000,
                            "owned_by": "google",
                            "permission": [],
                            "root": n,
                            "parent": None,
                            "description": f"[Auto-routed] {c['desc']}"
                        })
                    for acc in get_all_accounts():
                        acc_name = acc.get("name")
                        if acc_name:
                            for n, c in list(MODELS.items())[:3]:
                                models_list.append({
                                    "id": f"{acc_name}/{n}",
                                    "object": "model",
                                    "created": 1700000000,
                                    "owned_by": "google",
                                    "permission": [],
                                    "root": n,
                                    "parent": None,
                                    "description": f"[{acc_name}] {c['desc']}"
                                })
                    
                self.send_json({"object": "list", "data": models_list})
            elif clean_path.startswith("/v1beta/models") or clean_path.startswith("/models/"):
                self.send_json({"models": [
                    {"name": f"models/{n}", "displayName": n, "description": c["desc"],
                     "supportedGenerationMethods": ["generateContent", "streamGenerateContent"]}
                    for n, c in MODELS.items()
                ]})
            else:
                self.send_json({"error": "not found"}, 404)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_DELETE(self):
        try:
            clean_path = self.path.split("?")[0].rstrip("/")
            if clean_path == "/api/accounts" and "?" in self.path:
                qs = urllib.parse.parse_qs(self.path.split("?", 1)[1])
                name = qs.get("name", [""])[0]
                if name and delete_account(name):
                    self.send_response(200)
                    self.end_headers()
                else:
                    self.send_json({"error": "not found"}, 404)
                return
        except Exception:
            pass
            
    def do_POST(self):
        try:
            clean_path = self.path.split("?")[0].rstrip("/")
            if not clean_path:
                clean_path = "/"
                
            if clean_path == "/api/sync-cookies":
                length = int(self.headers.get("Content-Length", 0))
                payload = json.loads(self.rfile.read(length))
                msg = handle_extension_sync(payload)
                self._set_headers()
                self.wfile.write(json.dumps({"message": msg}).encode("utf-8"))
                return
                
            if clean_path == "/api/config":
                try:
                    length = int(self.headers.get("Content-Length", 0))
                    payload = json.loads(self.rfile.read(length))
                    if "temporary_chats" in payload:
                        CONFIG["temporary_chats"] = bool(payload["temporary_chats"])
                        
                        try:
                            if os.path.exists("config.json"):
                                with open("config.json", "r") as f:
                                    c = json.load(f)
                                c["temporary_chats"] = CONFIG["temporary_chats"]
                                with open("config.json", "w") as f:
                                    json.dump(c, f, indent=2)
                        except:
                            pass
                    
                    self._set_headers()
                    self.wfile.write(json.dumps({"status": "success", "temporary_chats": CONFIG["temporary_chats"]}).encode("utf-8"))
                except Exception as e:
                    self.send_json({"error": str(e)}, 400)
                return
                
            if clean_path == "/api/request-sync":
                request_sync()
                self.send_json({"status": "success", "message": "Sync flag set. Extension will sync on next ping."})
                return
                
            is_auth, force_acc = self._authenticate()
            if not is_auth:
                self.send_json({"error": {"message": "invalid api key"}}, 401)
                return
            set_current_account(force_acc)
            
            body = self._read_request_body()
            if clean_path in ("/v1/chat/completions", "/chat/completions"):
                self._handle_chat(body, force_acc)
            elif clean_path in ("/v1/responses", "/responses"):
                self._handle_responses(body)
            elif ":streamGenerateContent" in clean_path:
                self._handle_google_generate(body, stream=True)
            elif ":generateContent" in clean_path:
                self._handle_google_generate(body, stream=False)
            else:
                self.send_json({"error": "not found"}, 404)
        except (BrokenPipeError, ConnectionResetError):
            pass

    # ─── /v1/chat/completions ─────────────────────────────────────────────────

    def _handle_chat(self, body: bytes, auth_force_acc: str = None):
        req = self._parse_body(body)
        if req is None:
            self.send_json({"error": {"message": "invalid JSON"}}, 400)
            return
            
        req_model = req.get("model", CONFIG["default_model"])
        force_account = auth_force_acc
        
        # If model has account prefix, extract it and clean model name
        if "/" in req_model:
            parts = req_model.split("/", 1)
            if not force_account and parts[0] != "auto":
                force_account = parts[0]
            req_model = parts[1]
            
        try:
            set_current_account(force_account)
        except ValueError as e:
            self.send_json({"error": {"message": str(e)}}, 400)
            return
            
        model_name, model_id, think_mode, err, extra_fields = resolve_model(req_model)
        if err:
            self.send_json({"error": {"message": err}}, 400)
            return

        tools = req.get("tools")
        tool_choice = req.get("tool_choice", "auto")
        prompt, images = messages_to_prompt(req.get("messages", []), tools, tool_choice)
        if not prompt.strip():
            self.send_json({"error": {"message": "empty prompt"}}, 400)
            return

        stream = req.get("stream", False)
        cid = f"chatcmpl-{uuid.uuid4().hex[:12]}"
        
        if stream and (not tools or tool_choice == "none"):
            try:
                self._start_sse()
                first_chunk = {
                    "id": cid,
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": model_name,
                    "choices": [{
                        "index": 0,
                        "delta": {"role": "assistant"},
                        "finish_reason": None,
                    }],
                }
                self.wfile.write(f"data: {json.dumps(first_chunk)}\n\n".encode())
                self.wfile.flush()
                for delta in generate_stream(prompt, model_id, think_mode, file_refs=None, extra_fields=extra_fields, images=images):
                    chunk = {"id": cid, "object": "chat.completion.chunk", "created": int(time.time()),
                             "model": model_name, "choices": [{"index": 0, "delta": {"content": delta}, "finish_reason": None}]}
                    self.wfile.write(f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n".encode())
                    self.wfile.flush()
                end = {"id": cid, "object": "chat.completion.chunk", "created": int(time.time()),
                       "model": model_name, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}
                self.wfile.write(f"data: {json.dumps(end)}\n\n".encode())
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception as e:
                log(f"Stream error: {e}")
            return

        try:
            text = generate(prompt, model_id, think_mode, file_refs=None, extra_fields=extra_fields, images=images)
        except Exception as e:
            self.send_json({"error": {"message": f"upstream error: {e}"}}, 502)
            return

        tool_calls = None
        if tools and text and tool_choice != "none":
            text, tool_calls = parse_tool_calls(text)
        msg = {"role": "assistant", "content": text or None}
        if tool_calls:
            msg["tool_calls"] = tool_calls
        finish = "tool_calls" if tool_calls else "stop"

        if stream:
            self._start_sse()
            
            # Send initial role chunk
            chunk_init = {"id": cid, "object": "chat.completion.chunk", "created": int(time.time()),
                          "model": model_name, "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]}
            self.wfile.write(f"data: {json.dumps(chunk_init, ensure_ascii=False)}\n\n".encode())
            
            # Send content chunk if any
            if text:
                chunk_text = {"id": cid, "object": "chat.completion.chunk", "created": int(time.time()),
                              "model": model_name, "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}]}
                self.wfile.write(f"data: {json.dumps(chunk_text, ensure_ascii=False)}\n\n".encode())
                
            # Send tool calls chunks properly indexed
            if tool_calls:
                for i, tc in enumerate(tool_calls):
                    tc_header = {
                        "id": cid, "object": "chat.completion.chunk", "created": int(time.time()),
                        "model": model_name, "choices": [{"index": 0, "delta": {
                            "tool_calls": [{
                                "index": i,
                                "id": tc["id"],
                                "type": "function",
                                "function": {"name": tc["function"]["name"], "arguments": ""}
                            }]
                        }, "finish_reason": None}]
                    }
                    self.wfile.write(f"data: {json.dumps(tc_header, ensure_ascii=False)}\n\n".encode())
                    
                    tc_args = {
                        "id": cid, "object": "chat.completion.chunk", "created": int(time.time()),
                        "model": model_name, "choices": [{"index": 0, "delta": {
                            "tool_calls": [{
                                "index": i,
                                "function": {"arguments": tc["function"]["arguments"]}
                            }]
                        }, "finish_reason": None}]
                    }
                    self.wfile.write(f"data: {json.dumps(tc_args, ensure_ascii=False)}\n\n".encode())
                    
            # Send finish chunk
            chunk_finish = {"id": cid, "object": "chat.completion.chunk", "created": int(time.time()),
                            "model": model_name, "choices": [{"index": 0, "delta": {}, "finish_reason": finish}]}
            self.wfile.write(f"data: {json.dumps(chunk_finish, ensure_ascii=False)}\n\n".encode())
            
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        else:
            self.send_json({
                "id": cid, "object": "chat.completion", "created": int(time.time()),
                "model": model_name,
                "choices": [{"index": 0, "message": msg, "finish_reason": finish}],
                "usage": {"prompt_tokens": len(prompt)//4, "completion_tokens": len(text or "")//4,
                          "total_tokens": (len(prompt)+len(text or ""))//4},
            })

    # ─── /v1/responses (Codex CLI) ───────────────────────────────────────────

    def _handle_responses(self, body: bytes):
        req = self._parse_body(body)
        if req is None:
            self.send_json({"error": {"message": "invalid JSON"}}, 400)
            return
        model_name, model_id, think_mode, err, extra_fields = resolve_model(
            req.get("model", CONFIG["default_model"]))
        if err:
            self.send_json({"error": {"message": err}}, 400)
            return

        input_items = req.get("input", [])
        tools = req.get("tools")
        messages = []
        if req.get("instructions"):
            messages.append({"role": "system", "content": req["instructions"]})
        if isinstance(input_items, str):
            messages.append({"role": "user", "content": input_items})
        elif isinstance(input_items, list):
            for item in input_items:
                if isinstance(item, str):
                    messages.append({"role": "user", "content": item})
                elif isinstance(item, dict):
                    if item.get("type") == "function_call_output":
                        messages.append({"role": "tool", "tool_call_id": item.get("call_id", ""),
                                         "name": item.get("name", ""), "content": item.get("output", "")})
                    elif item.get("type") in ("input_text", "input_image", "image"):
                        messages.append({"role": "user", "content": [item]})
                    elif item.get("role") == "assistant" or (item.get("type") == "message" and item.get("role") == "assistant"):
                        cp = item.get("content", [])
                        text_acc, tc_list = "", []
                        if isinstance(cp, list):
                            for c in cp:
                                if isinstance(c, dict):
                                    if c.get("type") == "output_text":
                                        text_acc += c.get("text", "")
                                    elif c.get("type") == "function_call":
                                        tc_list.append(c)
                        elif isinstance(cp, str):
                            text_acc = cp
                        m = {"role": "assistant", "content": text_acc or None}
                        if tc_list:
                            m["tool_calls"] = [{"id": tc.get("call_id", f"call_{i}"), "type": "function",
                                                "function": {"name": tc.get("name",""), "arguments": tc.get("arguments","{}")}}
                                               for i, tc in enumerate(tc_list)]
                        messages.append(m)
                    else:
                        role = item.get("role", "user")
                        messages.append({"role": role, "content": item.get("content", "")})

        if tools:
            tools = [{"type": "function", "function": {"name": t["name"], "description": t.get("description", ""), "parameters": t.get("parameters", {})}}
                     if t.get("type") == "function" and "function" not in t else t for t in tools]

        tool_choice = req.get("tool_choice", "auto")
        prompt, images = messages_to_prompt(messages, tools, tool_choice)
        if not prompt.strip():
            self.send_json({"error": {"message": "empty input"}}, 400)
            return

        try:
            file_refs = _upload_images(images)
            text = generate(prompt, model_id, think_mode, file_refs, extra_fields)
        except Exception as e:
            self.send_json({"error": {"message": f"upstream error: {e}"}}, 502)
            return

        tool_calls = None
        if tools and text and tool_choice != "none":
            text, tool_calls = parse_tool_calls(text)

        rid = f"resp_{uuid.uuid4().hex[:16]}"
        mid = f"msg_{uuid.uuid4().hex[:12]}"
        output = []
        if tool_calls:
            for tc in tool_calls:
                output.append({"type": "function_call", "id": tc["id"], "call_id": tc["id"],
                               "name": tc["function"]["name"], "arguments": tc["function"]["arguments"], "status": "completed"})
        if text or not tool_calls:
            output.append({"type": "message", "id": mid, "role": "assistant", "status": "completed",
                           "content": [{"type": "output_text", "text": text or "", "annotations": []}]})

        if req.get("stream"):
            self._start_sse()
            sequence_number = 0

            def emit(event_type, **fields):
                nonlocal sequence_number
                sequence_number += 1
                event = {
                    "type": event_type,
                    "sequence_number": sequence_number,
                    **fields,
                }
                self.wfile.write(
                    f"event: {event_type}\ndata: {json.dumps(event)}\n\n".encode()
                )

            usage = {
                "input_tokens": len(prompt) // 4,
                "output_tokens": len(text or "") // 4,
                "total_tokens": (len(prompt) + len(text or "")) // 4,
            }
            base_response = {
                "id": rid,
                "object": "response",
                "created_at": int(time.time()),
                "model": model_name,
            }
            emit(
                "response.created",
                response={
                    **base_response,
                    "status": "in_progress",
                    "output": [],
                    "usage": None,
                },
            )
            emit(
                "response.in_progress",
                response={
                    **base_response,
                    "status": "in_progress",
                    "output": [],
                    "usage": None,
                },
            )
            for output_index, item in enumerate(output):
                if item["type"] == "function_call":
                    pending_item = {
                        "type": "function_call",
                        "id": item["id"],
                        "call_id": item["call_id"],
                        "name": item["name"],
                        "arguments": "",
                        "status": "in_progress",
                    }
                    emit(
                        "response.output_item.added",
                        output_index=output_index,
                        item=pending_item,
                    )
                    emit(
                        "response.function_call_arguments.delta",
                        item_id=item["id"],
                        output_index=output_index,
                        delta=item["arguments"],
                    )
                    emit(
                        "response.function_call_arguments.done",
                        item_id=item["id"],
                        output_index=output_index,
                        arguments=item["arguments"],
                    )
                    emit(
                        "response.output_item.done",
                        output_index=output_index,
                        item=item,
                    )
                elif item["type"] == "message":
                    pending_item = {
                        "type": "message",
                        "id": item["id"],
                        "role": "assistant",
                        "status": "in_progress",
                        "content": [],
                    }
                    emit(
                        "response.output_item.added",
                        output_index=output_index,
                        item=pending_item,
                    )
                    for content_index, content_part in enumerate(item["content"]):
                        event_fields = {
                            "item_id": item["id"],
                            "output_index": output_index,
                            "content_index": content_index,
                        }
                        emit(
                            "response.content_part.added",
                            **event_fields,
                            part={
                                "type": "output_text",
                                "text": "",
                                "annotations": [],
                            },
                        )
                        emit(
                            "response.output_text.delta",
                            **event_fields,
                            delta=content_part["text"],
                        )
                        emit(
                            "response.output_text.done",
                            **event_fields,
                            text=content_part["text"],
                        )
                        emit(
                            "response.content_part.done",
                            **event_fields,
                            part=content_part,
                        )
                    emit(
                        "response.output_item.done",
                        output_index=output_index,
                        item=item,
                    )
            emit(
                "response.completed",
                response={
                    **base_response,
                    "status": "completed",
                    "output": output,
                    "usage": usage,
                },
            )
            self.wfile.flush()
        else:
            self.send_json({"id": rid, "object": "response", "created_at": int(time.time()), "status": "completed",
                            "model": model_name, "output": output,
                            "usage": {"input_tokens": len(prompt)//4, "output_tokens": len(text or "")//4, "total_tokens": (len(prompt)+len(text or ""))//4}})

    # ─── /v1beta/models (Google Gemini CLI) ──────────────────────────────────

    def _handle_google_generate(self, body: bytes, stream: bool):
        req = self._parse_body(body)
        if req is None:
            self.send_json({"error": {"message": "invalid JSON"}}, 400)
            return
        m = re.match(r'/v1beta/models/([^:?]+)', self.path)
        model_name = m.group(1) if m else CONFIG["default_model"]
        model_name, model_id, think_mode, err, extra_fields = resolve_model(model_name)
        if err:
            self.send_json({"error": {"message": err}}, 400)
            return

        tool_config = req.get("toolConfig", {})
        fc_mode = tool_config.get("functionCallingConfig", {}).get("mode", "AUTO")
        has_tools = bool(req.get("tools")) and fc_mode != "NONE"
        prompt, images = google_contents_to_prompt(req)
        if not prompt.strip():
            self.send_json({"error": {"message": "empty content"}}, 400)
            return

        try:
            file_refs = _upload_images(images)
        except RuntimeError as e:
            self.send_json({"error": {"message": f"upstream error: {e}"}}, 502)
            return
        log(f"Google API: model={model_name} stream={stream} tools={has_tools} prompt_len={len(prompt)}")

        if stream and not has_tools:
            try:
                self._start_sse()
                full_text = ""
                for delta in generate_stream(prompt, model_id, think_mode, file_refs, extra_fields):
                    if not delta:
                        continue
                    full_text += delta
                    chunk_obj = {
                        "candidates": [{"content": {"parts": [{"text": delta}], "role": "model"}, "index": 0}],
                        "modelVersion": model_name,
                    }
                    self.wfile.write(f"data: {json.dumps(chunk_obj, ensure_ascii=False)}\n\n".encode())
                    self.wfile.flush()
                final_chunk = {
                    "candidates": [{"finishReason": "STOP", "index": 0}],
                    "usageMetadata": {
                        "promptTokenCount": len(prompt) // 4,
                        "candidatesTokenCount": len(full_text) // 4,
                        "totalTokenCount": (len(prompt) + len(full_text)) // 4,
                    },
                    "modelVersion": model_name,
                }
                self.wfile.write(f"data: {json.dumps(final_chunk, ensure_ascii=False)}\n\n".encode())
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception as e:
                log(f"Google stream error: {e}")
            return

        try:
            text = generate(prompt, model_id, think_mode, file_refs, extra_fields)
        except Exception as e:
            self.send_json({"error": {"message": f"upstream error: {e}"}}, 502)
            return

        if not text:
            log("Warning: empty response from Gemini")

        response_parts = []
        if has_tools and text:
            clean_text, function_calls = parse_google_function_calls(text)
            if function_calls:
                if clean_text:
                    response_parts.append({"text": clean_text})
                for fc in function_calls:
                    response_parts.append({"functionCall": {"name": fc["name"], "args": fc["args"]}})
            else:
                response_parts.append({"text": text})
        else:
            response_parts.append({"text": text or "I apologize, but I was unable to generate a response. Please try again."})

        candidate = {
            "content": {"parts": response_parts, "role": "model"},
            "finishReason": "STOP",
            "index": 0,
        }
        usage = {
            "promptTokenCount": len(prompt) // 4,
            "candidatesTokenCount": len(text or "") // 4,
            "totalTokenCount": (len(prompt) + len(text or "")) // 4,
        }
        response_obj = {
            "candidates": [candidate],
            "usageMetadata": usage,
            "modelVersion": model_name,
        }

        if stream:
            self._start_sse()
            self.wfile.write(f"data: {json.dumps(response_obj, ensure_ascii=False)}\n\n".encode())
            self.wfile.flush()
        else:
            self.send_json(response_obj)


class ThreadedServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True
