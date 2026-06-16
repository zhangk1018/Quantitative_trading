"""
[6.5] 调试版：等数据加载完成 + 详细打印 DOM
"""
from playwright.sync_api import sync_playwright
import time
import os
import json

OUT_DIR = "/Users/zhangk/workspace/Quantitative_trading/quant-trading-frontend/temp/browser_test"

api_requests = []


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_context(
            viewport={"width": 1440, "height": 900},
            locale="zh-CN",
        ).new_page()

        page.on("request", lambda req: api_requests.append({
            "url": req.url,
        }) if "/api/stocks/" in req.url else None)

        page.on("response", lambda res: print(
            f"  📥 HTTP {res.status} {res.url[:100]}"
        ) if "/api/stocks/" in res.url else None)

        console_logs = []
        page.on("console", lambda msg: console_logs.append(
            f"[{msg.type}] {msg.text[:200]}"
        ) if msg.type in ("log", "error", "warning") else None)

        page.goto("http://localhost:5173/picker", wait_until="networkidle", timeout=30000)
        time.sleep(1.0)

        # 展开 + 选中市值
        page.locator('.ant-collapse-header:has-text("行情指标")').first.click()
        time.sleep(0.5)
        page.click('[data-testid="indicator-btn-market_cap"]')
        time.sleep(0.3)

        # 填 10-20（应有 107 只）
        page.locator('[data-testid="indicator-min-market_cap"]').click()
        page.locator('[data-testid="indicator-min-market_cap"]').fill("10")
        time.sleep(0.2)
        page.locator('[data-testid="indicator-max-market_cap"]').click()
        page.locator('[data-testid="indicator-max-market_cap"]').fill("20")
        time.sleep(0.2)

        print("=== 点击开始选股 ===")
        page.click('[data-testid="start-screener"]')

        # 关键：等 API 响应 + 表格行出现
        try:
            page.wait_for_response(
                lambda r: "/api/stocks/" in r.url,
                timeout=10000
            )
            print("  ✅ API 响应已收到")
        except Exception as e:
            print(f"  ❌ 等 API 响应超时: {e}")

        # 再等 2 秒让 React 渲染
        time.sleep(2.0)

        # 详细打印 DOM 状态
        print("\n=== DOM 状态 ===")
        print(f"  表格行数: {page.locator('table tbody tr').count()}")
        print(f"  表格总行数(无 tbody 限制): {page.locator('table tr').count()}")

        # 抓取所有"共 N 只"文字
        all_total_texts = page.locator('text=/共\\s*\\d+\\s*只/').all_text_contents()
        print(f"  '共 N 只' 出现 {len(all_total_texts)} 次: {all_total_texts}")

        # 抓取所有股票名（表格内）
        stock_names_in_table = page.locator('table tbody tr td:nth-child(3)').all_text_contents()
        print(f"  表格中股票名: {stock_names_in_table[:5]}")

        # 抓取 message 内容
        message_texts = page.locator('.ant-message-notice-content').all_text_contents()
        print(f"  message 提示: {message_texts}")

        # 抓取空状态提示
        empty_texts = page.locator('text=/暂无数据/').all_text_contents()
        print(f"  暂无数据提示: {empty_texts}")

        # 截图
        page.screenshot(path=f"{OUT_DIR}/v3_65_debug.png", full_page=True)

        # 抓取 body 部分 HTML（最后 2000 字符）
        body_html = page.locator('body').inner_html()
        # 找到 "研奥股份" 或 "暂" 关键词
        if "研奥股份" in body_html:
            idx = body_html.find("研奥股份")
            print(f"\n  ✅ DOM 含 '研奥股份' (idx={idx})")
        if "暂无数据" in body_html:
            idx = body_html.find("暂无数据")
            print(f"  ⚠️ DOM 含 '暂无数据' (idx={idx})")
        if "共 107 只" in body_html:
            print(f"  ✅ DOM 含 '共 107 只'")
        if "选股成功" in body_html:
            print(f"  ✅ DOM 含 '选股成功'")

        # 抓取所有 console 输出
        print(f"\n=== Console 日志 ({len(console_logs)} 条) ===")
        for log in console_logs[-10:]:
            print(f"  {log}")

        time.sleep(1)
        browser.close()


if __name__ == "__main__":
    main()
