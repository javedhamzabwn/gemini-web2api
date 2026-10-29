# 🌐 Gemini Web2API Gateway

> **A high-performance local developer gateway bridging Google Gemini Web to OpenAI-compatible clients, Anthropic Claude agents, and Model Context Protocol (MCP) workflows.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![OpenAI Compatible](https://img.shields.io/badge/API-OpenAI%20Compatible-green.svg)](#)
[![Anthropic Claude Ready](https://img.shields.io/badge/API-Anthropic%20Claude-purple.svg)](#)
[![MCP Ready](https://img.shields.io/badge/MCP-Model%20Context%20Protocol-orange.svg)](#)
[![Cloudflare Ready](https://img.shields.io/badge/Cloudflare-Edge%20Worker-yellow.svg)](#)

---

## 📌 Overview

**Gemini Web2API Gateway** is an open-source multi-protocol bridge that translates your Google Gemini Web session into standardized, drop-in replacement REST APIs for:
1. **OpenAI API** (`/v1/chat/completions`, `/v1/models`)
2. **Anthropic Claude Messages API** (`/v1/messages`, `/claude/v1/messages`)
3. **Gemini Deep Research** (`/gemini/v1beta/interactions`)
4. **OpenAI Codex Responses** (`/v1/responses`)
5. **Google GenAI Native REST** (`/v1beta/models/...`)

Designed specifically for developers, researchers, and agentic workflows, it connects Gemini Web directly to IDE plugins, local developer tools, and autonomous coding assistants like **Claude Code**, **Cline**, **OpenCode**, **Cursor**, and **OpenDevin** without protocol incompatibilities.

---

## 🏛️ Architecture & Workflow

```
┌────────────────────────────────────────────────────────────────────────┐
│                          Developer Clients                             │
│       OpenCode  •  Cline  •  Cursor  •  Claude Code  •  OpenDevin      │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Standard OpenAI (/v1) or Claude (/v1/messages)
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                        Gemini Web2API Gateway                          │
│  • Anthropic Claude Adapter (translates messages, system & thinking)   │
│  • Agent Tool Adapter (formats MCP schemas & parallel tool execution)  │
│  • Deep Research Engine (autonomous multi-stage web-grounded research) │
│  • Hardened Scotty Resumable Upload (multimodal vision + fallback)     │
│  • Anti-Extension Keyword Sanitizer (avoids Google Workspace traps)    │
│  • Conversation Compactor (preserves agent state up to 300k chars)     │
└───────────────────┬────────────────────────────────┬───────────────────┘
                    │                                │
                    ▼                                ▼
┌───────────────────────────────────────┐  ┌─────────────────────────────┐
│     SQLite Session Pool & Router      │  │ Browser Companion Extension │
│  • Multi-Account Rotation & Failover  │  │  • Multi-Profile Sync       │
│  • Cooldown Backoff Tracking          │  │  • Automated Session Refresh│
│  • Account-Specific API Keys          │  │  • Background Worker Keep   │
└───────────────────┬───────────────────┘  └──────────────┬──────────────┘
                    │                                     │
                    └───────────────────┬─────────────────┘
                                        │ HTTPS Session Stream
                                        ▼
                        ┌───────────────────────────────┐
                        │       Google Gemini Web       │
                        │  3.8 Flash • 3.5 Lite • Pro   │
                        │  Deep Research • Web Search   │
                        └───────────────────────────────┘
```

---

## 🌟 Key Highlights

- **🔌 Universal Multi-Protocol Support**:
  - Full **OpenAI** compatibility (`/v1/chat/completions`, `/v1/models`).
  - Full **Anthropic Claude** compatibility (`/v1/messages`, `/claude/v1/messages`, `/v1/messages/count_tokens`).
  - Native **Gemini Deep Research** pipeline (`/gemini/v1beta/interactions`).
- **🚀 Frontier & Extended Reasoning**:
  - Out-of-the-box support for **Gemini 3.8 Flash**, **Gemini 3.5 Flash-Lite**, and **Gemini 3.1 Pro**.
  - Drop-in aliases for **Claude 3.7 Sonnet**, **Claude 3.5 Sonnet**, **Claude 3.5 Haiku**, **GPT-4o**, and **GPT-4**.
  - Thinking depth adjustable on any model via `@think=0` suffix.
- **🖼️ Hardened Scotty Resumable Multimodal Upload**:
  - Dual authentication (page tokens + static internal fallback `Basic c2F2...`).
  - Auto-compression and support for base64 data URIs, raw base64, Claude image blocks, and URLs.
- **🛡️ Anti-Extension Keyword Sanitizer**:
  - Prevents Gemini's pre-flight classifier from mistakenly flagging prompts containing words like *"Google Docs"*, *"Google Drive"*, *"Gmail"*, *"YouTube"*, or *"Webflow"* with permission traps.
- **⚡ Autonomous Agent Optimizations**:
  - 300k-character smart compactor preserves Cline / OpenCode / Claude Code state machines during massive parallel tool loops.
- **☁️ Cloudflare Edge Worker Edition**:
  - Includes `./cloudflare/worker.js` and `./cloudflare/wrangler.toml` for 1-click zero-cost serverless deployment on Cloudflare Workers.
- **📊 Real-time Web Dashboard**:
  - Interactive HTML dashboard (`/dashboard` or `/`) with live multi-protocol playground, account health checks, and sync triggers.

---

## 📋 Model Directory & Aliases

| Model ID (API Name) | Protocol Target | Reasoning Engine | Recommended For |
| :--- | :--- | :---: | :--- |
| `gemini-3.8-flash` | OpenAI / Claude / Native | Standard | General coding, fast completions, small edits |
| `gemini-3.8-flash-thinking` | OpenAI / Claude / Native | 🧠 Extended (`mode: 2`) | **Autonomous coding agents, MCP, complex logic** |
| `claude-3-7-sonnet` | Anthropic Claude (`/v1/messages`) | 🧠 Extended | **Claude Code, Cursor, complex agentic workflows** |
| `claude-3-5-sonnet` | Anthropic Claude (`/v1/messages`) | 🧠 Extended | High-accuracy code architecture & refactoring |
| `claude-3-5-haiku` | Anthropic Claude (`/v1/messages`) | Standard (`mode: 6`) | Ultra-fast token streaming, summaries, lookups |
| `gemini-deep-research` | Interactions / OpenAI | 🔍 Grounded Research | Multi-source investigation and report generation |
| `gemini-3.1-pro` | OpenAI / Claude / Native | Standard (`mode: 3`) | Gemini Advanced subscribers |
| `gpt-4o` | OpenAI drop-in | 🧠 Extended | Tools with hardcoded model selectors |

---

## 🚀 Quick Start

### 1. Installation

```bash
git clone https://github.com/javedhamzabwn/gemini-web2api.git
cd gemini-web2api
pip install -r requirements.txt
```

### 2. Start the Gateway

**On Windows:**
Double-click `start_manager.bat` and select option `4`.

**Or via Command Line:**
```bash
python -m gemini_web2api --port 10012
```

Access the Web Dashboard at: **`http://localhost:10012/`**

---

## 🛠️ Client Configuration

### 1. Claude Code / Terminal Agent
```bash
export ANTHROPIC_BASE_URL="http://localhost:10012"
export ANTHROPIC_API_KEY="sk-gemini-example-key"
export CLAUDE_MODEL="claude-3-7-sonnet"
claude
```

### 2. Cline / Roo Code (VS Code Extension)
- **API Provider**: `Anthropic` or `OpenAI Compatible`
- **Base URL**: `http://localhost:10012` (for Anthropic) or `http://localhost:10012/v1` (for OpenAI)
- **API Key**: `sk-gemini-example-key`
- **Model ID**: `claude-3-7-sonnet` or `gemini-3.8-flash-thinking`

### 3. OpenCode / OpenCode Studio
In your custom provider settings:
- **Provider**: `OpenAI-Compatible`
- **Base URL**: `http://localhost:10012/v1`
- **API Key**: Enter any key or your account-specific key.
- **Model**: `gemini-3.8-flash-thinking`

### 4. Cursor / Continue.dev
In `.cursorrules` or `continue/config.json`:
```json
{
  "models": [
    {
      "title": "Gemini 3.8 Flash Thinking",
      "provider": "openai",
      "model": "gemini-3.8-flash-thinking",
      "apiBase": "http://localhost:10012/v1",
      "apiKey": "sk-gemini-example-key"
    },
    {
      "title": "Claude 3.7 Sonnet (via Gemini)",
      "provider": "anthropic",
      "model": "claude-3-7-sonnet",
      "apiBase": "http://localhost:10012",
      "apiKey": "sk-gemini-example-key"
    }
  ]
}
```

---

## 🧪 End-to-End Verification

A comprehensive automated test suite is included:

```bash
python -m unittest tests.test_end_to_end
```

Covers:
- OpenAI `/v1/chat/completions` compatibility
- Anthropic Claude `/v1/messages` non-streaming, streaming, and tool calls
- Token estimation `/v1/messages/count_tokens`
- Scotty resumable upload MIME parsing and image extraction
- Deep Research plan generation and synthesis
- Live server dispatch and multi-account SQLite session integrity

---

## ☁️ Cloudflare Edge Worker Deployment

To deploy serverless on Cloudflare's edge network:

1. Navigate to the `cloudflare/` directory:
   ```bash
   cd cloudflare
   ```
2. Configure your secret cookie:
   ```bash
   npx wrangler secret put COOKIE_STRING
   ```
3. Deploy:
   ```bash
   npx wrangler deploy
   ```

See [`cloudflare/README.MD`](cloudflare/README.MD) for full details.

---

## 📄 License

Distributed under the [MIT License](LICENSE).
