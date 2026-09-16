# 🌐 Gemini Web2API

> **A high-performance local developer gateway bridging Google Gemini Web to OpenAI-compatible clients, autonomous coding agents, and Model Context Protocol (MCP) workflows.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![OpenAI Compatible](https://img.shields.io/badge/API-OpenAI%20Compatible-green.svg)](#)
[![MCP Ready](https://img.shields.io/badge/MCP-Model%20Context%20Protocol-purple.svg)](#)

---

## 📌 Overview

**Gemini Web2API** is an open-source developer bridge that provides an OpenAI-compatible REST API interface (`/v1/chat/completions`, `/v1/models`) powered by your own Google Gemini session. 

Designed specifically for developers, researchers, and agentic workflows, it enables you to connect Gemini Web to IDE plugins, local developer tools, and autonomous coding assistants like **OpenCode**, **Cline**, **Claude Code**, **OpenDevin**, and **Cursor** without protocol incompatibilities.

---

## 🏗️ Architecture & Workflow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           Developer Clients                             │
│       OpenCode  •  Cline  •  Cursor  •  Claude Code  •  OpenDevin       │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │ Standard OpenAI API (/v1/chat/completions)
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         Gemini Web2API Gateway                          │
│  • Agent Tool Adapter (formats MCP schemas & file/terminal operations)  │
│  • Streaming Indexer (sequences parallel tool calls into SSE deltas)    │
│  • Conversation Compactor (optimizes context for multi-turn sessions)   │
└───────────────────┬─────────────────────────────────┬───────────────────┘
                    │                                 │
                    ▼                                 ▼
┌──────────────────────────────────────┐  ┌───────────────────────────────┐
│     SQLite Session Pool & Router     │  │  Browser Companion Extension  │
│  • Manages multiple user accounts    │  │  • Multi-Profile Sync         │
│  • Smart request distribution        │  │  • Automated Session Refresh  │
│  • Account-specific API Keys         │  │  • Seamless Token Management  │
└───────────────────┬──────────────────┘  └───────────────┬───────────────┘
                    │                                     │
                    └──────────────────┬──────────────────┘
                                       │ HTTPS Session Stream
                                       ▼
                       ┌───────────────────────────────┐
                       │       Google Gemini Web       │
                       │  3.8 Flash • 3.5 Lite • Pro   │
                       └───────────────────────────────┘
```

---

## ✨ Key Highlights

- **🔌 Standard OpenAI & Native Endpoints**: Compatible with official OpenAI client SDKs, `/v1/chat/completions`, `/v1/models`, and Google Native endpoints.
- **⚡ Modern 2026 Model Support**: Out-of-the-box support for **Gemini 3.8 Flash**, **Gemini 3.5 Flash-Lite**, and **Gemini 3.1 Pro**.
- **🧠 Extended Thinking & Reasoning**: Native activation for deep thinking modes (`mode: 2`) delivering comprehensive multi-step reasoning.
- **🛠️ Agent & MCP Tool Integration**: Specially tuned for Model Context Protocol (MCP) servers and autonomous agents requiring reliable parallel tool execution and resilient JSON parsing.
- **👥 Multi-Session Management**: SQLite-backed session pool with automatic round-robin request distribution across multiple configured accounts.
- **🔄 Browser Companion Extension**: Automated background session keep-alive eliminates manual cookie copying and keeps connections active 24/7.
- **🖥️ Integrated Web Dashboard**: Real-time management interface to monitor session health, manage accounts, toggle temporary chats, and test prompts via an interactive playground.

---

## 📋 Model Directory (OpenCode & Agent Setup)

When configuring **OpenCode**, **Cline**, **Cursor**, or custom providers, use the following model parameters:

| Model ID (API Name) | Display Name (UI Label) | Reasoning Engine | Recommended For |
| :--- | :--- | :---: | :--- |
| `gemini-3.8-flash` | `Gemini 3.8 Flash` | Standard | General assistance, fast responses, small edits |
| `gemini-3.8-flash-thinking` | `Gemini 3.8 Flash (Thinking)` | ✅ Extended | **Autonomous coding agents, MCP, complex logic** |
| `gemini-3.5-flash-lite` | `Gemini 3.5 Flash-Lite` | Standard | High-speed documentation lookups & quick summaries |
| `gemini-3.1-pro` | `Gemini 3.1 Pro` | Standard | High-complexity reasoning & architectural analysis |
| `gemini-3.1-pro-thinking` | `Gemini 3.1 Pro (Thinking)` | ✅ Extended | Advanced mathematical proofs & deep code analysis |
| `gemini-auto` | `Gemini Auto` | Adaptive | Dynamic selection handled automatically by Google |

> **Note:** Extended thinking can also be explicitly toggled by adding `@think=0` to any model name (e.g., `gemini-3.8-flash@think=0`).

---

## ⚡ Quick Start

### 1. Installation

```bash
git clone https://github.com/yourusername/gemini-web2api.git
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

## 🍪 Adding Accounts via Browser Extension

1. Open Chrome and navigate to `chrome://extensions`.
2. Enable **Developer mode** (toggle in the top-right corner).
3. Click **Load unpacked** and select the `gemini-cookie-sync-extension` folder from this repository.
4. Log into [Google Gemini](https://gemini.google.com).
5. Click the extension icon in your Chrome toolbar.
6. Enter an account identifier (e.g. `main-account`, `work-profile`) and click **Sync Cookies**.
7. The extension will sync with your local gateway and keep session credentials fresh automatically.

*(Supports syncing across multiple separate Chrome browser profiles simultaneously).*

---

## ⚙️ Coding Agent & Tool Integrations

### 1. OpenCode / OpenCode Studio
In your OpenCode custom provider settings:
- **Provider**: `OpenAI-Compatible`
- **Base URL**: `http://localhost:10012/v1`
- **API Key**: Enter any key (e.g. `sk-gemini-example-key`) or leave blank if managed via headers.
- **Models**:
  - `model-id`: `gemini-3.8-flash-thinking` | `Display Name`: `Gemini 3.8 Flash (Thinking)`
  - `model-id`: `gemini-3.8-flash` | `Display Name`: `Gemini 3.8 Flash`
  - `model-id`: `gemini-3.1-pro` | `Display Name`: `Gemini 3.1 Pro`

### 2. Cline / Roo Code (VS Code Extension)
- **API Provider**: `OpenAI Compatible`
- **Base URL**: `http://localhost:10012/v1`
- **API Key**: `sk-gemini-example-key`
- **Model ID**: `gemini-3.8-flash-thinking`

### 3. Claude Code / Terminal Agents
```bash
export OPENAI_BASE_URL="http://localhost:10012/v1"
export OPENAI_API_KEY="sk-gemini-example-key"
export MODEL="gemini-3.8-flash-thinking"
```

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
    }
  ]
}
```

---

## 💻 Python Developer Example

```python
from openai import OpenAI

# Connect to local Gemini Web2API gateway
client = OpenAI(
    base_url="http://localhost:10012/v1",
    api_key="sk-gemini-example-key"
)

# Request completion with Extended Thinking
response = client.chat.completions.create(
    model="gemini-3.8-flash-thinking",
    messages=[
        {"role": "system", "content": "You are an expert software engineer."},
        {"role": "user", "content": "Explain the raft consensus protocol step by step."}
    ],
    stream=True
)

for chunk in response:
    content = chunk.choices[0].delta.content or ""
    print(content, end="", flush=True)
```

---

## ❓ Frequently Asked Questions (FAQ)

#### Q: Why does the model answer "Gemini 3.8 Flash" when asked about its identity?
**A:** Google's web chat server includes a global baseline identity card. When presented with meta-queries like *"what model are you?"*, Google returns a standardized response template. The underlying reasoning depth, context length, and execution logic strictly correspond to the model mode you selected.

#### Q: How can I verify that Extended Thinking is engaged?
**A:** Run a complex reasoning or multi-step logic problem. Standard Flash responses return concise answers in single-digit tokens; when Extended Thinking (`mode: 2`) is active, Google's thinking engine processes the problem deeply and outputs hundreds of reasoning tokens.

#### Q: How can I keep my Gemini Web conversation sidebar clean?
**A:** Enable **🕵️ Incognito Mode** from the Web Dashboard. All requests will use temporary chat sessions, ensuring automated agent runs never clutter your personal browser chat history.

---

## ⚖️ Disclaimer

This project is an independent open-source developer tool intended for personal experimentation, research, and local workflow automation. It is not affiliated with, maintained by, or endorsed by Google LLC. All trademarks and brand names belong to their respective owners.

---

## 📜 License

Distributed under the [MIT License](LICENSE).
