"""End-to-End Verification Test Suite for Gemini Web2API Multi-Protocol Gateway.

Tests:
1. Model resolution across native Gemini, Claude, and Deep Research aliases.
2. Claude protocol request-to-prompt conversion, system instruction, and image extraction.
3. Claude response building and SSE streaming event sequencing.
4. Scotty multimodal image MIME detection and upload handler logic.
5. Deep Research plan extraction and progress event structures.
6. Local HTTP Server integration test for /v1/models, /claude/v1/models, /v1/messages, /v1/messages/count_tokens.
7. Mocked Claude /v1/messages response dispatch and Deep Research interaction dispatch.
"""
import unittest
import json
import base64
import threading
import time
import urllib.request
import urllib.error
from unittest.mock import patch

from gemini_web2api.models import resolve_model, MODELS
from gemini_web2api.claude_adapter import (
    claude_messages_to_prompt,
    build_claude_response,
    claude_stream_events
)
from gemini_web2api.multimodal import detect_image_mime, upload_images
from gemini_web2api.deep_research import _extract_json_block, DeepResearchEngine
from gemini_web2api.server import GeminiHandler, ThreadedServer


class TestModelResolution(unittest.TestCase):
    def test_claude_aliases(self):
        name, mode, think, err, _ = resolve_model("claude-3-7-sonnet")
        self.assertIsNone(err)
        self.assertEqual(mode, 2)  # Extended thinking mode
        self.assertEqual(think, 0) # Deepest thinking level

        name, mode, think, err, _ = resolve_model("claude-3-5-haiku")
        self.assertIsNone(err)
        self.assertEqual(mode, 6)  # Flash-lite
        self.assertEqual(think, 4)

    def test_deep_research_models(self):
        name, mode, think, err, _ = resolve_model("gemini-deep-research")
        self.assertIsNone(err)
        self.assertEqual(mode, 2)

    def test_think_override(self):
        name, mode, think, err, _ = resolve_model("gemini-3.8-flash@think=0")
        self.assertIsNone(err)
        self.assertEqual(think, 0)
        self.assertEqual(mode, 2) # Auto-escalated to mode 2


class TestClaudeAdapter(unittest.TestCase):
    def test_message_conversion(self):
        req = {
            "model": "claude-3-7-sonnet",
            "system": "You are a senior systems engineer.",
            "messages": [
                {"role": "user", "content": "How does Raft handle leader election?"},
                {"role": "assistant", "content": "Raft uses randomized election timeouts."},
                {"role": "user", "content": "What happens on a tie?"}
            ],
            "tools": [
                {
                    "name": "lookup_raft_term",
                    "description": "Look up raft term in cluster",
                    "input_schema": {
                        "type": "object",
                        "properties": {"node_id": {"type": "string"}},
                        "required": ["node_id"]
                    }
                }
            ]
        }

        prompt, images, tool_defs = claude_messages_to_prompt(req)
        self.assertIn("System Instruction", prompt)
        self.assertIn("senior systems engineer", prompt)
        self.assertIn("[User]: How does Raft handle leader election?", prompt)
        self.assertIn("[Assistant]: Raft uses randomized election timeouts.", prompt)
        self.assertIn("lookup_raft_term", prompt)
        self.assertEqual(len(tool_defs), 1)
        self.assertEqual(tool_defs[0]["name"], "lookup_raft_term")

    def test_multimodal_image_extraction(self):
        sample_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        b64_png = base64.b64encode(sample_png).decode()

        req = {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Inspect this diagram:"},
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": b64_png
                            }
                        }
                    ]
                }
            ]
        }

        prompt, images, _ = claude_messages_to_prompt(req)
        self.assertIn("Inspect this diagram:", prompt)
        self.assertIn("[Image attached]", prompt)
        self.assertEqual(len(images), 1)
        self.assertEqual(images[0][0], sample_png)
        self.assertEqual(images[0][1], "image/png")

    def test_claude_response_building(self):
        # Normal text response
        resp = build_claude_response("claude-3-7-sonnet", "Here is the explanation.", tool_defs=[], prompt_len=100)
        self.assertTrue(resp["id"].startswith("msg_"))
        self.assertEqual(resp["type"], "message")
        self.assertEqual(resp["role"], "assistant")
        self.assertEqual(resp["content"][0]["type"], "text")
        self.assertEqual(resp["content"][0]["text"], "Here is the explanation.")
        self.assertEqual(resp["stop_reason"], "end_turn")

        # Tool use response
        tool_call_text = '```tool_call\n{"name": "fetch_logs", "arguments": {"lines": 50}}\n```'
        tool_defs = [{"name": "fetch_logs"}]
        resp_tool = build_claude_response("claude-3-7-sonnet", tool_call_text, tool_defs=tool_defs, prompt_len=100)
        self.assertEqual(resp_tool["stop_reason"], "tool_use")
        self.assertEqual(resp_tool["content"][0]["type"], "tool_use")
        self.assertEqual(resp_tool["content"][0]["name"], "fetch_logs")
        self.assertEqual(resp_tool["content"][0]["input"], {"lines": 50})

    def test_claude_sse_streaming(self):
        def fake_text_stream():
            yield "Hello "
            yield "from "
            yield "Claude!"

        events = list(claude_stream_events("claude-3-7-sonnet", fake_text_stream(), prompt_len=50))
        event_names = [e[0] for e in events]
        self.assertIn("message_start", event_names)
        self.assertIn("content_block_start", event_names)
        self.assertIn("content_block_delta", event_names)
        self.assertIn("content_block_stop", event_names)
        self.assertIn("message_delta", event_names)
        self.assertIn("message_stop", event_names)


    def test_claude_sse_streaming_with_tools(self):
        def fake_tool_stream():
            yield '```tool_call\n{"name": "execute_shell", "arguments": {"command": "ls"}}\n```'

        tool_defs = [{"name": "execute_shell"}]
        events = list(claude_stream_events("claude-3-7-sonnet", fake_tool_stream(), prompt_len=50, tool_defs=tool_defs))
        event_names = [e[0] for e in events]
        self.assertIn("message_start", event_names)
        self.assertIn("content_block_start", event_names)
        self.assertIn("content_block_delta", event_names)
        
        # Check tool use block
        has_tool_block = any(e[1].get("content_block", {}).get("type") == "tool_use" for e in events if e[0] == "content_block_start")
        self.assertTrue(has_tool_block)


class TestMultimodalUtils(unittest.TestCase):
    def test_detect_image_mime(self):
        png_magic = b"\x89PNG\r\n\x1a\n"
        jpeg_magic = b"\xff\xd8\xff"
        gif_magic = b"GIF89a"
        webp_magic = b"RIFF\x00\x00\x00\x00WEBP"

        self.assertEqual(detect_image_mime(png_magic), "image/png")
        self.assertEqual(detect_image_mime(jpeg_magic), "image/jpeg")
        self.assertEqual(detect_image_mime(gif_magic), "image/gif")
        self.assertEqual(detect_image_mime(webp_magic), "image/webp")


class TestDeepResearchUtils(unittest.TestCase):
    def test_json_extraction(self):
        fenced = '```json\n{"sub_questions": ["q1", "q2"], "outline": ["o1"]}\n```'
        clean = _extract_json_block(fenced)
        data = json.loads(clean)
        self.assertEqual(data["sub_questions"], ["q1", "q2"])

        raw_in_text = 'Some introductory text {"key": "value"} and trailer text.'
        clean_raw = _extract_json_block(raw_in_text)
        data_raw = json.loads(clean_raw)
        self.assertEqual(data_raw["key"], "value")


class TestServerEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.port = 19891
        cls.server = ThreadedServer(("127.0.0.1", cls.port), GeminiHandler)
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        time.sleep(0.5)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_get_models_openai(self):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/v1/models")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertEqual(data["object"], "list")
            model_ids = [m["id"] for m in data["data"]]
            self.assertIn("gemini-3.8-flash", model_ids)
            self.assertIn("claude-3-7-sonnet", model_ids)
            self.assertIn("gemini-deep-research", model_ids)

    def test_get_models_claude(self):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/claude/v1/models")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertIn("data", data)
            model_ids = [m["id"] for m in data["data"]]
            self.assertIn("claude-3-7-sonnet", model_ids)

    def test_claude_count_tokens(self):
        payload = json.dumps({
            "messages": [{"role": "user", "content": "Count tokens in this test message."}]
        }).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/v1/messages/count_tokens",
            data=payload,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertIn("input_tokens", data)
            self.assertGreater(data["input_tokens"], 0)

    @patch("gemini_web2api.server.generate")
    def test_claude_messages_dispatch(self, mock_generate):
        mock_generate.return_value = "This is a verified response from Gemini."
        
        payload = json.dumps({
            "model": "claude-3-7-sonnet",
            "messages": [{"role": "user", "content": "Hello Claude server!"}],
            "max_tokens": 1024
        }).encode()

        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/v1/messages",
            data=payload,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertEqual(data["type"], "message")
            self.assertEqual(data["role"], "assistant")
            self.assertEqual(data["content"][0]["text"], "This is a verified response from Gemini.")
            self.assertEqual(data["model"], "claude-3-7-sonnet")

    @patch("gemini_web2api.server.generate")
    def test_claude_messages_namespaced_dispatch(self, mock_generate):
        mock_generate.return_value = "Namespaced Claude route verified."
        
        payload = json.dumps({
            "model": "claude-3-5-sonnet",
            "messages": [{"role": "user", "content": "Hello namespaced route!"}],
        }).encode()

        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/claude/v1/messages",
            data=payload,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertEqual(data["content"][0]["text"], "Namespaced Claude route verified.")

    @patch("gemini_web2api.deep_research.generate")
    def test_deep_research_interactions_dispatch(self, mock_research_generate):
        mock_research_generate.return_value = "Synthesized Master Research Paper Content."
        
        payload = json.dumps({
            "input": "Distributed transactions consensus protocols",
            "stream": False
        }).encode()

        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/gemini/v1beta/interactions",
            data=payload,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertEqual(data["status"], "completed")
            self.assertIn("Synthesized Master Research Paper Content", data["outputs"][0]["text"])


if __name__ == "__main__":
    unittest.main()
