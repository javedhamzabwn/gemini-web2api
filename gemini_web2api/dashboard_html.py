DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Gemini Web2API Gateway Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-100 font-sans p-8">
    <div class="max-w-6xl mx-auto">
        <div class="flex items-center justify-between mb-8">
            <div>
                <h1 class="text-3xl font-bold text-blue-600">Gemini Web2API Gateway</h1>
                <p class="text-sm text-gray-500 mt-1">Universal Multi-Protocol Bridge: OpenAI • Anthropic Claude • Gemini Deep Research</p>
            </div>
            <span class="bg-blue-100 text-blue-800 text-xs font-semibold px-3 py-1 rounded-full border border-blue-200">v1.2.0 Universal</span>
        </div>
        
        <!-- Active Protocols Banner -->
        <div class="bg-white p-5 rounded-lg shadow mb-8 border-l-4 border-blue-500">
            <h2 class="text-base font-bold text-gray-800 mb-3 flex items-center">
                <span class="mr-2">🔌</span> Supported Protocols & Endpoints
            </h2>
            <div class="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs font-mono">
                <div class="bg-gray-50 p-3 rounded border">
                    <div class="font-bold text-gray-700 text-sm mb-1 font-sans">OpenAI Compatible</div>
                    <div class="text-blue-600">POST /v1/chat/completions</div>
                    <div class="text-gray-500 mt-1 font-sans">For Cline, OpenCode, Cursor, Chatbox</div>
                </div>
                <div class="bg-purple-50 p-3 rounded border border-purple-200">
                    <div class="font-bold text-purple-900 text-sm mb-1 font-sans">Anthropic Claude</div>
                    <div class="text-purple-600">POST /v1/messages</div>
                    <div class="text-gray-500 mt-1 font-sans">For Claude Code, LangChain, Anthropic SDK</div>
                </div>
                <div class="bg-emerald-50 p-3 rounded border border-emerald-200">
                    <div class="font-bold text-emerald-900 text-sm mb-1 font-sans">Gemini Deep Research</div>
                    <div class="text-emerald-600">POST /gemini/v1beta/interactions</div>
                    <div class="text-gray-500 mt-1 font-sans">Autonomous web-grounded research pipeline</div>
                </div>
            </div>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-2 gap-8 mb-8">
            <div class="bg-white p-6 rounded-lg shadow">
                <h2 class="text-xl font-bold mb-4">Master Info</h2>
                <p><strong>Master API Key:</strong> <span id="master-key" class="font-mono text-sm bg-gray-200 px-1 rounded">Loading...</span></p>
                <p class="mt-2"><strong>Total Accounts:</strong> <span id="total-accounts" class="font-semibold text-blue-600">0</span></p>
                <p class="mt-2 text-xs text-gray-500">Cloudflare Edge Worker available in <code class="bg-gray-100 px-1 rounded">./cloudflare/</code></p>
            </div>
            
            <div class="bg-white p-6 rounded-lg shadow flex items-center justify-between">
                <div>
                    <h2 class="text-xl font-bold mb-2">Health Check & Sync</h2>
                    <p class="text-sm text-gray-600 mb-2">Verify cookies or trigger auto-sync</p>
                    <label class="flex items-center space-x-2 text-sm text-gray-700 font-bold cursor-pointer bg-gray-100 px-3 py-1 rounded inline-flex">
                        <input type="checkbox" id="incognito-toggle" onchange="toggleIncognito(this.checked)" class="form-checkbox h-4 w-4 text-purple-600 transition duration-150 ease-in-out">
                        <span>🕵️ Incognito Mode (Temporary Chats)</span>
                    </label>
                </div>
                <div class="flex space-x-2">
                    <button onclick="runHealthCheck()" class="bg-green-500 hover:bg-green-600 text-white font-bold py-2 px-4 rounded text-sm transition-colors">
                        Verify All
                    </button>
                    <button onclick="triggerAutoSync()" class="bg-blue-500 hover:bg-blue-600 text-white font-bold py-2 px-4 rounded text-sm transition-colors">
                        Force Extension Sync
                    </button>
                </div>
            </div>
        </div>
        
        <div class="bg-white p-6 rounded-lg shadow mb-8">
            <h2 class="text-xl font-bold mb-4">Accounts & Quotas</h2>
            <div class="overflow-x-auto">
                <table class="min-w-full bg-white">
                    <thead class="bg-gray-800 text-white">
                        <tr>
                            <th class="py-2 px-4 text-left">Account Name</th>
                            <th class="py-2 px-4 text-left">API Key</th>
                            <th class="py-2 px-4 text-left">Auth User</th>
                            <th class="py-2 px-4 text-left">Status</th>
                            <th class="py-2 px-4 text-left">Cooldown</th>
                            <th class="py-2 px-4 text-left">Health</th>
                            <th class="py-2 px-4 text-center">Actions</th>
                        </tr>
                    </thead>
                    <tbody id="accounts-table" class="text-gray-700">
                        <tr><td colspan="7" class="py-4 text-center">Loading accounts...</td></tr>
                    </tbody>
                </table>
            </div>
        </div>
        
        <div class="bg-white p-6 rounded-lg shadow mb-8">
            <div class="flex justify-between items-center mb-4 flex-wrap gap-2">
                <h2 class="text-xl font-bold">API Playground & Connection Test</h2>
                <div class="flex items-center space-x-2 flex-wrap gap-2">
                    <label class="flex items-center space-x-1.5 text-xs text-gray-700 font-medium cursor-pointer bg-gray-100 px-2.5 py-1.5 rounded border border-gray-300">
                        <input type="checkbox" id="chat-thinking" class="form-checkbox h-3.5 w-3.5 text-blue-600 rounded">
                        <span>🧠 Extended thinking</span>
                    </label>
                    <select id="chat-protocol" class="border rounded px-2.5 py-1 text-sm bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500">
                        <option value="openai">Protocol: OpenAI (/v1/chat/completions)</option>
                        <option value="claude">Protocol: Claude (/v1/messages)</option>
                        <option value="research">Protocol: Deep Research</option>
                    </select>
                    <select id="chat-account" class="border rounded px-2.5 py-1 text-sm bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500">
                        <option value="auto">Auto Load-Balance</option>
                    </select>
                    <select id="chat-model" class="border rounded px-2.5 py-1 text-sm bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500">
                        <optgroup label="Gemini Native">
                            <option value="gemini-3.8-flash">Gemini 3.8 Flash</option>
                            <option value="gemini-3.8-flash-thinking">Gemini 3.8 Flash (Thinking)</option>
                            <option value="gemini-3.5-flash-lite">Gemini 3.5 Flash-Lite</option>
                            <option value="gemini-3.1-pro">Gemini 3.1 Pro</option>
                            <option value="gemini-deep-research">Gemini Deep Research</option>
                        </optgroup>
                        <optgroup label="Claude Drop-in">
                            <option value="claude-3-7-sonnet">Claude 3.7 Sonnet</option>
                            <option value="claude-3-5-sonnet">Claude 3.5 Sonnet</option>
                            <option value="claude-3-5-haiku">Claude 3.5 Haiku</option>
                        </optgroup>
                    </select>
                </div>
            </div>
            <div id="chat-history" class="bg-gray-50 border p-4 rounded-lg h-64 overflow-y-auto mb-4 text-sm flex flex-col space-y-3">
                <div class="text-gray-500 text-center italic">Send a message to test the API connection across OpenAI, Claude, or Deep Research...</div>
            </div>
            <div class="flex space-x-2">
                <input type="text" id="chat-input" placeholder="Type a message or research query..." class="flex-grow border rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500" onkeypress="if(event.key === 'Enter') sendChatMessage()">
                <button onclick="sendChatMessage()" id="chat-btn" class="bg-blue-600 hover:bg-blue-700 text-white font-bold py-2 px-6 rounded-lg transition-colors">
                    Send
                </button>
            </div>
        </div>
    </div>

    <script>
        async function loadStats() {
            try {
                const res = await fetch('/api/stats');
                const data = await res.json();
                
                document.getElementById('master-key').textContent = data.master_key || "None configured";
                document.getElementById('total-accounts').textContent = data.total_accounts;
                document.getElementById('incognito-toggle').checked = data.temporary_chats;
                
                const tbody = document.getElementById('accounts-table');
                tbody.innerHTML = '';
                
                const accountDropdown = document.getElementById('chat-account');
                const currentSelection = accountDropdown.value;
                accountDropdown.innerHTML = '<option value="auto">Auto Load-Balance</option>';
                
                if (data.accounts.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="7" class="py-4 text-center">No accounts configured.</td></tr>';
                    return;
                }
                
                data.accounts.forEach(acc => {
                    const option = document.createElement('option');
                    option.value = acc.api_key;
                    option.textContent = `Force: ${acc.name}`;
                    if (currentSelection === acc.api_key) option.selected = true;
                    accountDropdown.appendChild(option);

                    const statusClass = acc.status === "Ready" ? "text-green-600 font-bold" : "text-red-600 font-bold";
                    const tr = document.createElement('tr');
                    tr.className = "border-b hover:bg-gray-50";
                    tr.innerHTML = `
                        <td class="py-2 px-4">${acc.name}</td>
                        <td class="py-2 px-4 font-mono text-xs">${acc.api_key}</td>
                        <td class="py-2 px-4">${acc.auth_user || 0}</td>
                        <td class="py-2 px-4 ${statusClass}">${acc.status}</td>
                        <td class="py-2 px-4">${acc.cooldown_seconds > 0 ? acc.cooldown_seconds + 's' : '-'}</td>
                        <td class="py-2 px-4" id="health-${acc.name}">Unknown</td>
                        <td class="py-2 px-4 text-center">
                            <button onclick="deleteAccount('${acc.name}')" class="text-red-500 hover:text-red-700 text-sm">Delete</button>
                        </td>
                    `;
                    tbody.appendChild(tr);
                });
            } catch (err) {
                console.error(err);
            }
        }

        async function runHealthCheck() {
            try {
                const res = await fetch('/api/check');
                const results = await res.json();
                results.forEach(r => {
                    const el = document.getElementById('health-' + r.name);
                    if (el) {
                        el.textContent = r.status;
                        el.className = r.valid ? "py-2 px-4 text-green-600" : "py-2 px-4 text-red-600";
                    }
                });
            } catch(e) {
                alert("Health check failed: " + e);
            }
        }
        
        async function triggerAutoSync() {
            try {
                const res = await fetch('/api/request-sync', { method: 'POST' });
                const data = await res.json();
                alert(data.message || "Sync requested");
            } catch(e) {
                alert("Failed to request sync: " + e);
            }
        }
        
        async function toggleIncognito(isEnabled) {
            try {
                const res = await fetch('/api/config', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({temporary_chats: isEnabled})
                });
                if (!res.ok) alert("Failed to update config");
            } catch(e) {
                console.error(e);
            }
        }
        
        async function deleteAccount(name) {
            if (!confirm(`Delete account ${name}?`)) return;
            try {
                const res = await fetch('/api/accounts?name=' + encodeURIComponent(name), { method: 'DELETE' });
                if (res.ok) {
                    loadStats();
                } else {
                    alert("Failed to delete account");
                }
            } catch (e) {
                console.error(e);
            }
        }

        let chatMessages = [];
        
        async function sendChatMessage() {
            const input = document.getElementById('chat-input');
            const btn = document.getElementById('chat-btn');
            const history = document.getElementById('chat-history');
            const text = input.value.trim();
            const protocol = document.getElementById('chat-protocol').value;
            const selectedModel = document.getElementById('chat-model').value;
            const selectedAccount = document.getElementById('chat-account').value;
            
            if (!text) return;
            
            if (chatMessages.length === 0) history.innerHTML = '';
            
            input.value = '';
            input.disabled = true;
            btn.disabled = true;
            
            chatMessages.push({role: "user", content: text});
            history.innerHTML += `<div class="self-end bg-blue-100 text-blue-900 rounded-lg py-2 px-4 max-w-[80%]">${text.replace(/</g, "&lt;")}</div>`;
            history.scrollTop = history.scrollHeight;
            
            const botId = "bot-msg-" + Date.now();
            history.innerHTML += `<div class="self-start bg-gray-200 text-gray-800 rounded-lg py-2 px-4 max-w-[80%] whitespace-pre-wrap" id="${botId}">⏳ Connecting via ${protocol.toUpperCase()}...</div>`;
            history.scrollTop = history.scrollHeight;
            const botBubble = document.getElementById(botId);
            
            try {
                const authToken = selectedAccount === "auto" ? "sk-gemini-auto" : selectedAccount;
                let modelToUse = selectedModel;
                if (document.getElementById('chat-thinking')?.checked && !modelToUse.includes("thinking")) {
                    modelToUse += "@think=0";
                }
                
                let endpoint = '/v1/chat/completions';
                let payload = {};
                
                if (protocol === 'claude') {
                    endpoint = '/v1/messages';
                    payload = {
                        model: modelToUse,
                        messages: chatMessages,
                        max_tokens: 4096,
                        stream: false
                    };
                } else if (protocol === 'research') {
                    endpoint = '/gemini/v1beta/interactions';
                    payload = {
                        input: text,
                        model: modelToUse,
                        stream: false
                    };
                } else {
                    payload = {
                        model: modelToUse,
                        messages: chatMessages,
                        stream: false
                    };
                }
                
                const response = await fetch(endpoint, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': 'Bearer ' + authToken
                    },
                    body: JSON.stringify(payload)
                });
                
                const resData = await response.json();
                let reply = "";
                
                if (protocol === 'claude') {
                    if (resData.content && Array.isArray(resData.content)) {
                        reply = resData.content.map(b => b.text || (b.thinking ? `[Thinking]: ${b.thinking}` : "")).filter(Boolean).join("\\n");
                    } else if (resData.error) {
                        reply = "Error: " + JSON.stringify(resData.error);
                    }
                } else if (protocol === 'research') {
                    reply = resData.final_report || (resData.outputs && resData.outputs[0]?.text) || JSON.stringify(resData, null, 2);
                } else {
                    reply = resData.choices?.[0]?.message?.content || resData.error?.message || "No response received";
                }
                
                botBubble.textContent = reply;
                chatMessages.push({role: "assistant", content: reply});
            } catch (err) {
                botBubble.textContent = "Error: " + err.message;
            } finally {
                input.disabled = false;
                btn.disabled = false;
                input.focus();
                history.scrollTop = history.scrollHeight;
            }
        }

        window.onload = loadStats;
    </script>
</body>
</html>
"""
