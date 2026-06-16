"""
行情指标浏览器自测脚本
验证场景：
  1) 全部股票（默认"沪深+全部板块"，不勾选任何行情指标）
  2) 市值 1.2~1.5 亿元（market_cap_min=120000000, market_cap_max=150000000）

输出：截图保存到 temp/browser_test/ 目录
"""
from playwright.sync_api import sync_playwright
import time
import os
import json

OUT_DIR = "/Users/zhangk/workspace/Quantitative_trading/quant-trading-frontend/temp/browser_test"
os.makedirs(OUT_DIR, exist_ok=True)

URL = "http://localhost:5173/picker"

# 记录所有 /api/stocks/ 请求的 URL（用于验证后端参数）
api_requests = []


def main():
    with sync_playwright() as p:
        # headless=False 让操作过程可被 K 看到（如果 K 关注 IDE 浏览器）
        # headless=True 也行，截图即可
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            locale="zh-CN",
        )
        page = context.new_page()

        # 拦截 /api/stocks/ 请求
        def handle_request(request):
            if "/api/stocks/" in request.url:
                api_requests.append({
                    "url": request.url,
                    "method": request.method,
                })

        page.on("request", handle_request)

        # 收集 console 错误
        console_errors = []
        page.on("console", lambda msg: console_errors.append(
            f"[{msg.type}] {msg.text}"
        ) if msg.type == "error" else None)

        print(f"=== 访问 {URL} ===")
        page.goto(URL, wait_until="networkidle", timeout=30000)
        time.sleep(1.0)

        # 截图：初始页面
        page.screenshot(path=f"{OUT_DIR}/00_initial.png", full_page=True)
        print("截图：00_initial.png")

        # ============================================
        # 场景 1：全部股票
        # ============================================
        print("\n=== 场景 1：全部股票 ===")
        # 验证默认状态：板块=沪深，"全部"勾选
        # 直接点击"开始选股"
        page.click('[data-testid="start-screener"]')

        # 等待表格行出现
        page.wait_for_selector('table tbody tr', timeout=15000)
        time.sleep(0.5)
        page.screenshot(path=f"{OUT_DIR}/01_all_stocks.png", full_page=True)
        print("截图：01_all_stocks.png")

        # 抓取顶部"共 N 只"和表格前几行
        total_text = page.text_content('span:has-text("共")') if page.locator('span:has-text("共")').count() > 0 else "未找到"
        rows_1 = page.locator('table tbody tr').all()
        print(f"  total_count 显示: {total_text}")
        print(f"  表格行数: {len(rows_1)}")
        # 抓前 3 行数据
        for i, row in enumerate(rows_1[:3]):
            cells = row.locator('td').all_text_contents()
            print(f"  第{i+1}行: {' | '.join([c.strip() for c in cells if c.strip()])}")

        # ============================================
        # 场景 2：市值 1.2~1.5 亿（即 120000000~150000000 元）
        # ============================================
        print("\n=== 场景 2：市值 1.2~1.5 亿 ===")
        # 重置
        page.click('[data-testid="reset-screener"]')
        time.sleep(0.5)

        # 展开"行情指标"折叠面板
        # data-testid="indicator-filter-collapse"
        collapse_header = page.locator('.ant-collapse-header:has-text("行情指标")').first
        collapse_header.click()
        time.sleep(0.5)

        # 点击"市值"指标按钮
        page.click('[data-testid="indicator-btn-market_cap"]')
        time.sleep(0.3)

        # 截图：展开并选中市值
        page.screenshot(path=f"{OUT_DIR}/02_market_cap_selected.png", full_page=True)
        print("截图：02_market_cap_selected.png")

        # 在 min 输入框输入 120000000
        min_input = page.locator('[data-testid="indicator-min-market_cap"]')
        min_input.click()
        min_input.fill("120000000")
        time.sleep(0.3)

        # 在 max 输入框输入 150000000
        max_input = page.locator('[data-testid="indicator-max-market_cap"]')
        max_input.click()
        max_input.fill("150000000")
        time.sleep(0.3)

        # 截图：已输入 min/max
        page.screenshot(path=f"{OUT_DIR}/03_market_cap_filled.png", full_page=True)
        print("截图：03_market_cap_filled.png")

        # 点击"开始选股"
        page.click('[data-testid="start-screener"]')

        # 等待表格
        page.wait_for_selector('table tbody tr', timeout=15000)
        time.sleep(1.0)
        page.screenshot(path=f"{OUT_DIR}/04_market_cap_result.png", full_page=True)
        print("截图：04_market_cap_result.png")

        # 抓取顶部"共 N 只"和表格前几行
        total_text_2 = page.text_content('span:has-text("共")') if page.locator('span:has-text("共")').count() > 0 else "未找到"
        rows_2 = page.locator('table tbody tr').all()
        print(f"  total_count 显示: {total_text_2}")
        print(f"  表格行数: {len(rows_2)}")
        for i, row in enumerate(rows_2[:5]):
            cells = row.locator('td').all_text_contents()
            print(f"  第{i+1}行: {' | '.join([c.strip() for c in cells if c.strip()])}")

        # ============================================
        # 汇总：API 请求日志
        # ============================================
        print("\n=== /api/stocks/ 请求日志 ===")
        for i, req in enumerate(api_requests):
            print(f"  [{i+1}] {req['method']} {req['url']}")

        # ============================================
        # Console 错误
        # ============================================
        print(f"\n=== Console 错误 ({len(console_errors)} 条) ===")
        for err in console_errors:
            print(f"  {err}")

        # 保存请求日志
        with open(f"{OUT_DIR}/api_requests.json", "w", encoding="utf-8") as f:
            json.dump(api_requests, f, ensure_ascii=False, indent=2)
        print(f"\n请求日志已保存到 {OUT_DIR}/api_requests.json")

        # 最后停留 2 秒让 K 看最终页面
        time.sleep(2)
        browser.close()


if __name__ == "__main__":
    main()
