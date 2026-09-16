// background.js

const CORE_REQUIRED = ["SAPISID"];
const SESSION_ALTERNATIVES = ["__Secure-1PSID", "__Secure-3PSID", "SID"];
const EXPORT_ORDER = [
  "SID", "HSID", "SSID", "APISID", "SAPISID", "LSID", "OSID", "SIDCC", "AEC", "NID", "COMPASS",
  "__Secure-1PAPISID", "__Secure-1PSID", "__Secure-1PSIDTS", "__Secure-1PSIDCC", "__Secure-1PSIDRTS",
  "__Secure-3PAPISID", "__Secure-3PSID", "__Secure-3PSIDTS", "__Secure-3PSIDCC", "__Secure-3PSIDRTS",
  "__Secure-OSID", "__Host-1PLSID", "__Host-3PLSID"
];

const LOOKUP_URLS = [
  "https://gemini.google.com/app",
  "https://accounts.google.com/",
  "https://www.google.com/"
];

function normalizeDomain(domain = "") {
  return domain.replace(/^\./, "").toLowerCase();
}

function isGoogleCookie(cookie) {
  const domain = normalizeDomain(cookie.domain);
  return domain === "google.com" || domain.endsWith(".google.com");
}

function cookieKey(cookie) {
  const partition = cookie.partitionKey ? JSON.stringify(cookie.partitionKey) : "";
  return [cookie.storeId || "", cookie.name, cookie.domain, cookie.path, partition].join("|");
}

function scoreCookie(cookie) {
  const domain = (cookie.domain || "").toLowerCase();
  let score = 0;
  if (domain === ".google.com") score += 120;
  else if (domain === "google.com") score += 110;
  else if (domain === ".gemini.google.com") score += 100;
  else if (domain === "gemini.google.com") score += 95;
  else if (domain === ".accounts.google.com") score += 80;
  else if (domain === "accounts.google.com") score += 75;
  else if (domain.endsWith(".google.com")) score += 40;
  if (cookie.path === "/") score += 10;
  if (cookie.secure) score += 3;
  if (cookie.httpOnly) score += 2;
  if (!cookie.partitionKey) score += 2;
  if (!cookie.session) score += 1;
  return score;
}

async function readGoogleCookies() {
  const stores = await chrome.cookies.getAllCookieStores();
  const deduped = new Map();
  for (const store of stores) {
    const queries = [
      chrome.cookies.getAll({ storeId: store.id }),
      ...LOOKUP_URLS.map((url) => chrome.cookies.getAll({ storeId: store.id, url }))
    ];
    const results = await Promise.allSettled(queries);
    for (const result of results) {
      if (result.status !== "fulfilled") continue;
      for (const cookie of result.value) {
        if (!isGoogleCookie(cookie) || !cookie.value) continue;
        deduped.set(cookieKey(cookie), cookie);
      }
    }
  }
  return [...deduped.values()];
}

function selectBestCookies(cookies) {
  const selected = new Map();
  for (const name of EXPORT_ORDER) {
    const candidates = cookies
      .filter((cookie) => cookie.name === name && cookie.value)
      .sort((a, b) => scoreCookie(b) - scoreCookie(a));
    if (candidates.length > 0) selected.set(name, candidates[0]);
  }
  return selected;
}

async function fetchPageMetadata() {
  try {
    // We fetch the page in the background to grab SNlM0e without needing an open tab!
    const resp = await fetch("https://gemini.google.com/app");
    const html = await resp.text();
    
    // Auth user detection from URL if it redirects, otherwise assume 0
    let authUser = "0";
    const urlMatch = resp.url.match(/\/u\/(\d+)(?:\/|$)/);
    if (urlMatch) authUser = urlMatch[1];
    
    const decode = (value) => {
        if (!value) return null;
        try { return JSON.parse(`"${value.replace(/"/g, '\\"')}"`); }
        catch { return value; }
    };
    
    const regexValue = (name) => {
        const patterns = [
            new RegExp(`"${name}"\\s*:\\s*"([^"\\n]+)"`),
            new RegExp(`\\\\"${name}\\\\"\\s*:\\s*\\\\"([^"\\n]+)\\\\"`)
        ];
        for (const pattern of patterns) {
            const match = html.match(pattern);
            if (match?.[1]) return decode(match[1]);
        }
        return null;
    };
    
    return {
        xsrfToken: regexValue("SNlM0e"),
        geminiBl: regexValue("cfb2h"),
        authUser: authUser
    };
  } catch (e) {
    return { xsrfToken: null, geminiBl: null, authUser: null };
  }
}

async function performSync(baseUrl) {
    console.log("Auto-syncing to", baseUrl);
    const cookies = await readGoogleCookies();
    const selected = selectBestCookies(cookies);
    
    const missingCore = CORE_REQUIRED.filter((name) => !selected.has(name));
    const sessionCookie = SESSION_ALTERNATIVES.find((name) => selected.has(name));
    
    if (missingCore.length > 0 || !sessionCookie) {
        console.warn("Missing required cookies for sync.");
        return;
    }
    
    const metadata = await fetchPageMetadata();
    if (!metadata.xsrfToken) {
        console.warn("Failed to extract XSRF token via background fetch.");
        return;
    }
    
    const cookieString = EXPORT_ORDER.filter((name) => selected.has(name)).map((name) => `${name}=${selected.get(name).value}`).join("; ");
    
    const payload = {
        cookie: cookieString,
        sapisid: selected.get("SAPISID").value,
        auth_user: metadata.authUser,
        xsrf_token: metadata.xsrfToken,
        gemini_bl: metadata.geminiBl
    };
    
    try {
        await fetch(`${baseUrl}/api/sync-cookies`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        console.log("Successfully synced cookies in background!");
    } catch(e) {
        console.error("Failed to post to proxy:", e);
    }
}

async function checkProxyStatus() {
    chrome.storage.local.get(["proxyUrl"], async (result) => {
        const baseUrl = (result.proxyUrl || "http://127.0.0.1:10012").replace(/\/+$/, "");
        try {
            const resp = await fetch(`${baseUrl}/api/status`);
            if (resp.ok) {
                const data = await resp.json();
                if (data.sync_requested) {
                    await performSync(baseUrl);
                }
            }
        } catch(e) {
            // Proxy might be offline, ignore silently
        }
    });
}

// Poll every 10 seconds for terminal commands
setInterval(checkProxyStatus, 10000);

// Auto-sync completely seamlessly every 30 minutes to prevent expiration
setInterval(() => {
    chrome.storage.local.get(["proxyUrl"], async (result) => {
        const baseUrl = (result.proxyUrl || "http://127.0.0.1:10012").replace(/\/+$/, "");
        performSync(baseUrl);
    });
}, 30 * 60 * 1000);
