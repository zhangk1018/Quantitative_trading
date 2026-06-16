"""
Debug 技术指标 Modal
"""
from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    page = context.new_page()

    page.on("console", lambda msg: print(f"[CONSOLE] [{msg.type}] {msg.text}") if msg.type in ("error", "warning") else None)
    page.on("pageerror", lambda err: print(f"[PAGE ERROR] {err}"))

    page.goto("http://localhost:5173/picker", wait_until="networkidle", timeout=30000)
    time.sleep(1.0)

    # 展开技术指标面板
    page.locator('[data-testid="technical-filter-header"]').click()
    time.sleep(0.5)

    # 截图
    page.screenshot(path="/tmp/debug_01_expanded.png")

    # 检查 4 个按钮的可见性
    for btn_id in ["ma", "macd", "boll", "rsi"]:
        visible = page.locator(f'[data-testid="technical-btn-{btn_id}"]').is_visible()
        print(f"  technical-btn-{btn_id}: visible={visible}")

    # 点击 MA 按钮
    page.click('[data-testid="technical-btn-ma"]')
    time.sleep(1.0)

    # 截图
    page.screenshot(path="/tmp/debug_02_after_click_ma.png")

    # 列出 body 下所有 data-testid="technical-modal-*" 的元素
    modal_count = page.evaluate("""
        () => {
            const elements = document.querySelectorAll('[data-testid^="technical-modal-"]');
            return Array.from(elements).map(el => ({
                testid: el.getAttribute('data-testid'),
                tag: el.tagName,
                visible: el.offsetParent !== null,
                innerHTML: el.innerHTML.substring(0, 100),
            }));
        }
    """)
    print(f"\n  Modal elements found: {len(modal_count)}")
    for m in modal_count:
        print(f"  {m}")

    # 检查 ant-modal-root 是否存在
    modal_root = page.evaluate("""
        () => {
            const root = document.querySelector('.ant-modal-root, [class*="ant-modal"]');
            return root ? { tag: root.tagName, class: root.className.substring(0, 100) } : null;
        }
    """)
    print(f"\n  ant-modal root: {modal_root}")

    # 检查所有 .ant-modal-wrap 元素
    wraps = page.evaluate("""
        () => Array.from(document.querySelectorAll('[class*="ant-modal"]')).map(el => ({
            tag: el.tagName,
            class: el.className.substring(0, 100),
            visible: el.offsetParent !== null,
        }))
    """)
    print(f"\n  All ant-modal elements: {len(wraps)}")
    for w in wraps:
        print(f"  {w}")

    time.sleep(3)
    browser.close()
