DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Gemini Web2API Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-100 font-sans p-8">
    <div class="max-w-6xl mx-auto">
        <h1 class="text-3xl font-bold mb-8 text-blue-600">Gemini Web2API Admin Dashboard</h1>
        
        <div class="grid grid-cols-1 md:grid-cols-2 gap-8 mb-8">
            <div class="bg-white p-6 rounded-lg shadow">
                <h2 class="text-xl font-bold mb-4">Master Info</h2>
                <p><strong>Master API Key:</strong> <span id="master-key" class="font-mono text-sm bg-gray-200 px-1 rounded">Loading...</span></p>
                <p><strong>Total Accounts:</strong> <span id="total-accounts">0</span></p>
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
                    <button onclick="runHealthCheck()" class="bg-green-500 hover:bg-green-600 text-white font-bold py-2 px-4 rounded">
                        Verify All
                    </button>
                    <button onclick="triggerAutoSync()" class="bg-blue-500 hover:bg-blue-600 text-white font-bold py-2 px-4 rounded">
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
            <div class="flex justify-between items-center mb-4">
                <h2 class="text-xl font-bold">API Playground & Connection Test</h2>
                <div class="flex items-center space-x-2">
                    <label class="flex items-center space-x-1.5 text-xs text-gray-700 font-medium cursor-pointer bg-gray-100 px-2.5 py-1.5 rounded border border-gray-300">
                        <input type="checkbox" id="chat-thinking" class="form-checkbox h-3.5 w-3.5 text-blue-600 rounded">
                        <span>🧠 Extended thinking</span>
                    </label>
                    <select id="chat-account" class="border rounded px-3 py-1 text-sm bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500">
                        <option value="auto">Auto Load-Balance</option>
                    </select>
                    <select id="chat-model" class="border rounded px-3 py-1 text-sm bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500">
                        <option value="gemini-3.8-flash">3.8 Flash</option>
                        <option value="gemini-3.5-flash-lite">3.5 Flash-Lite</option>
                        <option value="gemini-3.1-pro">3.1 Pro</option>
                    </select>
                </div>
            </div>
            <div id="chat-history" class="bg-gray-50 border p-4 rounded-lg h-64 overflow-y-auto mb-4 text-sm flex flex-col space-y-3">
                <div class="text-gray-500 text-center italic">Send a message to test the API connection...</div>
            </div>
            <div class="flex space-x-2">
                <input type="text" id="chat-input" placeholder="Type a message..." class="flex-grow border rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500" onkeypress="if(event.key === 'Enter') sendChatMessage()">
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
                    // Populate dropdown
                    const option = document.createElement('option');
                    option.value = acc.api_key;
                    option.textContent = `Force: ${acc.name}`;
                    if (currentSelection === acc.api_key) option.selected = true;
                    accountDropdown.appendChild(option);

                    // Populate table
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
            const masterKey = document.getElementById('master-key').textContent;
            const selectedModel = document.getElementById('chat-model').value;
            const selectedAccount = document.getElementById('chat-account').value;
            
            if (!text) return;
            
            // Remove placeholder if it exists
            if (chatMessages.length === 0) history.innerHTML = '';
            
            // Add user message to UI
            input.value = '';
            input.disabled = true;
            btn.disabled = true;
            
            chatMessages.push({role: "user", content: text});
            history.innerHTML += `<div class="self-end bg-blue-100 text-blue-900 rounded-lg py-2 px-4 max-w-[80%]">${text.replace(/</g, "&lt;")}</div>`;
            history.scrollTop = history.scrollHeight;
            
            // Add bot thinking bubble
            const botId = "bot-msg-" + Date.now();
            history.innerHTML += `<div class="self-start bg-gray-200 text-gray-800 rounded-lg py-2 px-4 max-w-[80%] whitespace-pre-wrap" id="${botId}">...</div>`;
            history.scrollTop = history.scrollHeight;
            const botBubble = document.getElementById(botId);
            
            try {
                const authToken = selectedAccount === "auto" ? "sk-gemini-auto" : selectedAccount;
                let modelToUse = selectedModel;
                if (document.getElementById('chat-thinking')?.checked) {
                    modelToUse += "@think=0";
                }
                
                const response = await fetch('/v1/chat/completions', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': 'Bearer ' + authToken
                    },
                    body: JSON.stringify({
                        model: modelToUse,
                        messages: chatMessages,
                        stream: true
                    })
                });
                
                if (!response.ok) {
                    const err = await response.json();
                    throw new Error(err.error?.message || response.statusText);
                }
                
                const reader = response.body.getReader();
                const decoder = new TextDecoder("utf-8");
                botBubble.textContent = "";
                let botFullText = "";
                
                while (true) {
                    const {done, value} = await reader.read();
                    if (done) break;
                    const chunk = decoder.decode(value);
                    const lines = chunk.split('\\n');
                    for (const line of lines) {
                        if (line.startsWith('data: ') && line !== 'data: [DONE]') {
                            try {
                                const data = JSON.parse(line.substring(6));
                                const token = data.choices[0].delta?.content || "";
                                botFullText += token;
                                botBubble.textContent = botFullText;
                                history.scrollTop = history.scrollHeight;
                            } catch(e) {}
                        }
                    }
                }
                chatMessages.push({role: "assistant", content: botFullText});
                
            } catch (error) {
                botBubble.textContent = "Error: " + error.message;
                botBubble.className = "self-start bg-red-100 text-red-800 rounded-lg py-2 px-4 max-w-[80%]";
                chatMessages.pop(); // remove user message so they can try again
            } finally {
                input.disabled = false;
                btn.disabled = false;
                input.focus();
            }
        }

        // Auto-refresh stats every 5 seconds
        setInterval(loadStats, 5000);
        loadStats();
    </script>
</body>
</html>
"""
