import asyncio
import json
import os
import argparse
from playwright.async_api import async_playwright

async def extract_gemini_cookies(headless=False):
    print("Launching Chromium browser...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context()
        page = await context.new_page()
        
        print("Navigating to https://gemini.google.com/ ...")
        await page.goto("https://gemini.google.com/")
        
        if headless:
            print("Running in headless mode. If you are not already authenticated, this will fail.")
            print("Please run without --headless first to log in.")
        else:
            print("---------------------------------------------------------")
            print("Please log into your Google Account in the opened browser window.")
            print("Once you are fully logged in and can see the Gemini chat interface,")
            print("press ENTER here in the terminal to extract the cookies.")
            print("---------------------------------------------------------")
            input("Press ENTER when ready...")
        
        cookies = await context.cookies()
        
        # We need __Secure-1PSID and __Secure-1PSIDTS
        sid = None
        sidts = None
        
        for c in cookies:
            if c['name'] == '__Secure-1PSID':
                sid = c['value']
            elif c['name'] == '__Secure-1PSIDTS':
                sidts = c['value']
                
        if not sid:
            print("ERROR: Could not find __Secure-1PSID cookie. Are you sure you are logged in?")
            await browser.close()
            return
            
        cookie_string = f"__Secure-1PSID={sid}; "
        if sidts:
            cookie_string += f"__Secure-1PSIDTS={sidts}; "
            
        # Get user ID from URL if possible, or just default to 0
        auth_user = "0"
        if "/u/" in page.url:
            parts = page.url.split("/u/")
            if len(parts) > 1:
                auth_user = parts[1].split("/")[0]
                
        # Attempt to grab xsrf_token (SNlM0e) from the page
        xsrf_token = ""
        try:
            content = await page.content()
            if "SNlM0e" in content:
                # Basic string search for the token array
                import re
                match = re.search(r'\["SNlM0e","([^"]+)"\]', content)
                if match:
                    xsrf_token = match.group(1)
        except:
            pass
            
        print(f"Extraction successful! Found cookies for auth_user: {auth_user}")
        
        payload = {
            "cookie": cookie_string,
            "auth_user": auth_user,
            "xsrf_token": xsrf_token,
            "sapisid": "" # Not strictly needed if we have SID
        }
        
        os.makedirs("cookies", exist_ok=True)
        filename = f"cookies/playwright_acc_{auth_user}.json"
        with open(filename, "w") as f:
            json.dump(payload, f, indent=4)
            
        print(f"Saved cookies to {filename}")
        print("You can now run 'python -m gemini_web2api --import-cookies cookies' to load them.")
        
        await browser.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract Gemini Cookies via Playwright")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    args = parser.parse_args()
    
    asyncio.run(extract_gemini_cookies(args.headless))
