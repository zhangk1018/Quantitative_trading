"""
弹窗缩小后效果验证（2026-06-16）
对比 4 个弹窗的新尺寸
"""
from playwright.sync_api import sync_playwright
import time
import os

OUT_DIR = "/Users/zhangk/workspace/Quantitative_trading/quant-trading-frontend/temp/browser_test"
os.makedirs(OUT_DIR, exist_ok=True)


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            locale="zh-CN",
        )
        page = context.new_page()

        page.goto("http://localhost:5173/picker", wait_until="networkidle", timeout=30000)
        time.sleep(1.0)

        # 展开技术指标面板
        page.locator('[data-testid="technical-filter-header"]').click()
        time.sleep(0.5)

        for indicator_id, label in [
            ("ma", "MA·日K"),
            ("macd", "MACD·日K"),
            ("boll", "BOLL·日K"),
            ("rsi", "RSI·日K"),
        ]:
            print(f"\n=== 打开 {label} 弹窗 ===")
            page.click(f'[data-testid="technical-btn-{indicator_id}"]')
            time.sleep(0.5)
            # 用 .ant-modal-content 测量实际弹窗内容尺寸
            box = page.evaluate("""
                () => {
                    const el = document.querySelector('.ant-modal-content');
                    if (!el) return null;
                    const r = el.getBoundingClientRect();
                    return { w: r.width, h: r.height };
                }
            """)
            if box:
                print(f"  弹窗内容尺寸: {box['w']:.0f} × {box['h']:.0f}")
            page.screenshot(path=f"{OUT_DIR}/compact_{indicator_id}_modal.png", full_page=False)
            # 关闭弹窗
            page.click(f'[data-testid="technical-modal-{indicator_id}-cancel"]')
            time.sleep(0.3)

        time.sleep(1)
        browser.close()


if __name__ == "__main__":
    main()
