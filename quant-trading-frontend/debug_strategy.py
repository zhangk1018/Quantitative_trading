"""Debug script: check localStorage strategies and page state"""
from playwright.sync_api import sync_playwright
import json, base64

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()
    
    page.on("console", lambda msg: print(f"[CONSOLE] {msg.text}"))
    page.on("pageerror", lambda err: print(f"[PAGE_ERROR] {err}"))
    
    page.goto('http://localhost:3000/stock-picker')
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(2000)
    
    # Check localStorage for strategies
    strategies_raw = page.evaluate("() => localStorage.getItem('screener_strategies')")
    if strategies_raw:
        try:
            decoded = base64.b64decode(strategies_raw)
            strategies = json.loads(decoded)
            print(f"\n=== STRATEGIES FOUND: {len(strategies)} ===")
            for s in strategies:
                print(f"  Strategy: {s.get('name')}")
                print(f"  Created: {s.get('createdAt')}")
                state = s.get('state', {})
                condition = state.get('condition', {})
                filter_group = condition.get('filterGroup')
                print(f"  filterGroup: {json.dumps(filter_group, ensure_ascii=False, indent=4)}")
                mi = state.get('marketIndicators', {})
                print(f"  marketIndicators.selected: {mi.get('selected')}")
                fi = state.get('financialIndicators', {})
                print(f"  financialIndicators.selected: {fi.get('selected')}")
                tech = state.get('technical', {})
                print(f"  technical.selected: {list(tech.get('selected', {}).keys())}")
                print()
        except Exception as e:
            print(f"  Error decoding: {e}")
            print(f"  Raw: {strategies_raw[:200]}")
    else:
        print("No strategies found in localStorage")
    
    page.screenshot(path='/Users/zhangk/workspace/Quantitative_trading/quant-trading-frontend/debug_screenshot.png', full_page=True)
    print("\nScreenshot saved")
    
    browser.close()