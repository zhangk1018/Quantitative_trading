"""
[6.5-MARKETCAP-20260615] 修复后复测：按 UI 显示的"亿元"输入正确数字
- 市场场景：用户看到"市值(亿元)"，输入 1.2-1.5，期望 total > 0
- 验证单位转换：URL 应为 market_cap_min=12000&market_cap_max=15000（万元）
"""
from playwright.sync_api import sync_playwright
import time
import os
import json

OUT_DIR = "/Users/zhangk/workspace/Quantitative_trading/quant-trading-frontend/temp/browser_test"
os.makedirs(OUT_DIR, exist_ok=True)

api_requests = []


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            locale="zh-CN",
        )
        page = context.new_page()

        page.on("request", lambda req: api_requests.append(
            {"url": req.url, "method": req.method}
        ) if "/api/stocks/" in req.url else None)

        console_errors = []
        page.on("console", lambda msg: console_errors.append(
            f"[{msg.type}] {msg.text}"
        ) if msg.type == "error" else None)

        print("=== 访问 /picker ===")
        page.goto("http://localhost:5173/picker", wait_until="networkidle", timeout=30000)
        time.sleep(1.0)

        # 展开"行情指标"
        page.locator('.ant-collapse-header:has-text("行情指标")').first.click()
        time.sleep(0.5)

        # 点击"市值"按钮
        page.click('[data-testid="indicator-btn-market_cap"]')
        time.sleep(0.3)

        # 截图：展开+选中市值
        page.screenshot(path=f"{OUT_DIR}/v3_65_market_cap_ui.png", full_page=True)
        print("截图：v3_65_market_cap_ui.png")

        # 关键修复：按"亿元"输入 1.2 和 1.5（不再输入 120000000）
        min_input = page.locator('[data-testid="indicator-min-market_cap"]')
        min_input.click()
        min_input.fill("1.2")
        time.sleep(0.2)
        max_input = page.locator('[data-testid="indicator-max-market_cap"]')
        max_input.click()
        max_input.fill("1.5")
        time.sleep(0.2)

        # 截图：已填 1.2-1.5
        page.screenshot(path=f"{OUT_DIR}/v3_65_filled_1.2_to_1.5.png", full_page=True)
        print("截图：v3_65_filled_1.2_to_1.5.png")

        # 点击开始选股
        page.click('[data-testid="start-screener"]')
        page.wait_for_timeout(3000)

        page.screenshot(path=f"{OUT_DIR}/v3_65_result.png", full_page=True)
        print("截图：v3_65_result.png")

        # 抓 total
        try:
            total_span = page.get_by_text("^共\\s*\\d+\\s*只$").first
            total = total_span.text_content() if total_span else "未找到"
        except Exception:
            total = "未找到"

        rows = page.locator('table tbody tr').all()
        print(f"\n  === [6.5] 修复后结果 ===")
        print(f"  顶部 total: {total}")
        print(f"  表格行数: {len(rows)}")
        for i, row in enumerate(rows[:8]):
            cells = row.locator('td').all_text_contents()
            print(f"  第{i+1}行: {' | '.join([c.strip() for c in cells[:6] if c.strip()])}")

        # ============================================
        # 验证：多个不同范围测试
        # ============================================
        print("\n\n=== 场景 B：市值 10~20 亿元（量量 curl 验证：total=107）===")
        page.click('[data-testid="reset-screener"]')
        time.sleep(0.5)
        if not page.locator('[data-testid="indicator-btn-market_cap"]').is_visible():
            page.locator('.ant-collapse-header:has-text("行情指标")').first.click()
            time.sleep(0.5)
        page.click('[data-testid="indicator-btn-market_cap"]')
        time.sleep(0.2)
        page.locator('[data-testid="indicator-min-market_cap"]').click()
        page.locator('[data-testid="indicator-min-market_cap"]').fill("10")
        time.sleep(0.2)
        page.locator('[data-testid="indicator-max-market_cap"]').click()
        page.locator('[data-testid="indicator-max-market_cap"]').fill("20")
        time.sleep(0.2)
        page.click('[data-testid="start-screener"]')
        page.wait_for_timeout(3000)

        try:
            total_span = page.get_by_text("^共\\s*\\d+\\s*只$").first
            total_b = total_span.text_content() if total_span else "未找到"
        except Exception:
            total_b = "未找到"
        print(f"  顶部 total: {total_b}（量量 curl 期望 107）")

        # ============================================
        # 场景 C：金额 1~5 亿元（amount 字段也按"亿"输入）
        # ============================================
        print("\n=== 场景 C：成交额 1~5 亿元 ===")
        page.click('[data-testid="reset-screener"]')
        time.sleep(0.5)
        if not page.locator('[data-testid="indicator-btn-market_cap"]').is_visible():
            page.locator('.ant-collapse-header:has-text("行情指标")').first.click()
            time.sleep(0.5)
        page.click('[data-testid="indicator-btn-amount"]')
        time.sleep(0.2)
        page.locator('[data-testid="indicator-min-amount"]').click()
        page.locator('[data-testid="indicator-min-amount"]').fill("1")
        time.sleep(0.2)
        page.locator('[data-testid="indicator-max-amount"]').click()
        page.locator('[data-testid="indicator-max-amount"]').fill("5")
        time.sleep(0.2)
        page.click('[data-testid="start-screener"]')
        page.wait_for_timeout(3000)

        try:
            total_span = page.get_by_text("^共\\s*\\d+\\s*只$").first
            total_c = total_span.text_content() if total_span else "未找到"
        except Exception:
            total_c = "未找到"
        print(f"  顶部 total: {total_c}")

        # ============================================
        # 汇总 API 请求
        # ============================================
        print("\n=== /api/stocks/ 请求汇总 ===")
        for i, req in enumerate(api_requests):
            url = req['url']
            # 截短显示
            print(f"  [{i+1}] {url[:200]}{'...' if len(url) > 200 else ''}")

        with open(f"{OUT_DIR}/v3_api_requests.json", "w", encoding="utf-8") as f:
            json.dump(api_requests, f, ensure_ascii=False, indent=2)

        if console_errors:
            print(f"\n=== Console 错误 ({len(console_errors)} 条) ===")
            for err in console_errors[:5]:
                print(f"  {err[:200]}")

        time.sleep(2)
        browser.close()


if __name__ == "__main__":
    main()
