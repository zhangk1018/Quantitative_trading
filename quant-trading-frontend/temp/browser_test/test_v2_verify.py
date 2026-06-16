"""
[6.4-INDICATOR-FILTER-20260615] + [6.3-MULTIBOARD-20260615] 修复后 Playwright 验证
- 6.4: 行情指标 10 字段范围筛选（重点验证市值 1.2~1.5 亿）
- 6.3: 多板块组合查询（上海主板+创业板 等）
"""
from playwright.sync_api import sync_playwright
import time
import os
import json

OUT_DIR = "/Users/zhangk/workspace/Quantitative_trading/quant-trading-frontend/temp/browser_test"
os.makedirs(OUT_DIR, exist_ok=True)

URL = "http://localhost:5173/picker"

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

        print(f"=== 访问 {URL} ===")
        page.goto(URL, wait_until="networkidle", timeout=30000)
        time.sleep(1.0)

        # ============================================
        # 6.4 验证：市值 1.2~1.5 亿元（market_cap 12000~15000 万元）
        # ============================================
        print("\n=== [6.4] 场景 A：市值 1.2~1.5 亿元 ===")

        # 展开"行情指标"折叠面板
        collapse_header = page.locator('.ant-collapse-header:has-text("行情指标")').first
        collapse_header.click()
        time.sleep(0.5)

        # 点击"市值"
        page.click('[data-testid="indicator-btn-market_cap"]')
        time.sleep(0.3)

        # 输入 min=12000, max=15000（按后端"万元"单位）
        min_input = page.locator('[data-testid="indicator-min-market_cap"]')
        min_input.click()
        min_input.fill("12000")
        time.sleep(0.2)
        max_input = page.locator('[data-testid="indicator-max-market_cap"]')
        max_input.click()
        max_input.fill("15000")
        time.sleep(0.2)

        # 点击"开始选股"
        page.click('[data-testid="start-screener"]')
        page.wait_for_timeout(2500)
        page.screenshot(path=f"{OUT_DIR}/v2_64_market_cap_1.2to1.5_yi.png", full_page=True)
        print("截图：v2_64_market_cap_1.2to1.5_yi.png")

        # 抓 total
        total_text = page.locator('span:has-text("共")').first.text_content() if page.locator('span:has-text("共")').count() > 0 else "未找到"
        # 精确匹配（避免 message.success 中的"共 N 只"）
        try:
            total_span = page.get_by_text("^共\\s*\\d+\\s*只$", exact=False).filter(has_text="只").first
            total_precise = total_span.text_content() if total_span else "(没找到)"
        except Exception:
            total_precise = "(没找到)"
        rows = page.locator('table tbody tr').all()
        print(f"  顶部 total 显示: {total_text.strip() if total_text else '无'}")
        print(f"  表格行数: {len(rows)}")
        for i, row in enumerate(rows[:5]):
            cells = row.locator('td').all_text_contents()
            print(f"  第{i+1}行: {' | '.join([c.strip() for c in cells[:5] if c.strip()])}")

        # ============================================
        # 6.4 验证：价格 10~50 元 + 换手率 2~10%
        # ============================================
        print("\n=== [6.4] 场景 B：价格 10~50 元 + 换手率 2~10% ===")
        page.click('[data-testid="reset-screener"]')
        time.sleep(0.5)

        # 展开"行情指标"（如果被折叠回去）
        if not page.locator('[data-testid="indicator-btn-market_cap"]').is_visible():
            page.locator('.ant-collapse-header:has-text("行情指标")').first.click()
            time.sleep(0.5)

        # 价格
        page.click('[data-testid="indicator-btn-price"]')
        time.sleep(0.2)
        page.locator('[data-testid="indicator-min-price"]').click()
        page.locator('[data-testid="indicator-min-price"]').fill("10")
        time.sleep(0.2)
        page.locator('[data-testid="indicator-max-price"]').click()
        page.locator('[data-testid="indicator-max-price"]').fill("50")
        time.sleep(0.2)

        # 换手率
        page.click('[data-testid="indicator-btn-turnover"]')
        time.sleep(0.2)
        page.locator('[data-testid="indicator-min-turnover"]').click()
        page.locator('[data-testid="indicator-min-turnover"]').fill("2")
        time.sleep(0.2)
        page.locator('[data-testid="indicator-max-turnover"]').click()
        page.locator('[data-testid="indicator-max-turnover"]').fill("10")
        time.sleep(0.2)

        page.screenshot(path=f"{OUT_DIR}/v2_64_price_turnover.png", full_page=True)
        print("截图：v2_64_price_turnover.png")

        page.click('[data-testid="start-screener"]')
        page.wait_for_timeout(2500)
        page.screenshot(path=f"{OUT_DIR}/v2_64_price_turnover_result.png", full_page=True)

        total_text_b = page.locator('span:has-text("共")').first.text_content() if page.locator('span:has-text("共")').count() > 0 else "未找到"
        rows_b = page.locator('table tbody tr').all()
        print(f"  顶部 total: {total_text_b.strip() if total_text_b else '无'}")
        print(f"  表格行数: {len(rows_b)}")
        for i, row in enumerate(rows_b[:5]):
            cells = row.locator('td').all_text_contents()
            print(f"  第{i+1}行: {' | '.join([c.strip() for c in cells[:6] if c.strip()])}")

        # ============================================
        # 6.4 验证：量比 >= 1.5
        # ============================================
        print("\n=== [6.4] 场景 C：量比 >= 1.5 ===")
        page.click('[data-testid="reset-screener"]')
        time.sleep(0.5)
        if not page.locator('[data-testid="indicator-btn-market_cap"]').is_visible():
            page.locator('.ant-collapse-header:has-text("行情指标")').first.click()
            time.sleep(0.5)

        page.click('[data-testid="indicator-btn-volume_ratio"]')
        time.sleep(0.2)
        page.locator('[data-testid="indicator-min-volume_ratio"]').click()
        page.locator('[data-testid="indicator-min-volume_ratio"]').fill("1.5")
        time.sleep(0.2)
        page.click('[data-testid="start-screener"]')
        page.wait_for_timeout(2500)
        page.screenshot(path=f"{OUT_DIR}/v2_64_volume_ratio_1.5.png", full_page=True)

        total_text_c = page.locator('span:has-text("共")').first.text_content() if page.locator('span:has-text("共")').count() > 0 else "未找到"
        rows_c = page.locator('table tbody tr').all()
        print(f"  顶部 total: {total_text_c.strip() if total_text_c else '无'}")
        print(f"  表格行数: {len(rows_c)}")

        # ============================================
        # 6.3 验证：多板块组合（前端选择 上海主板+创业板）
        # ============================================
        print("\n=== [6.3] 多板块：上海主板 + 创业板 ===")
        page.click('[data-testid="reset-screener"]')
        time.sleep(0.5)

        # 找上市地 Select，关闭"全部"并勾选"上海主板"和"创业板"
        # RangeSelector 中"上市地"是 Antd Select multiple
        # 我们通过选项 label 点击
        # 简化：通过 URL 模拟（直接验证 API）
        # 这里走 UI 操作

        # 点击"上市地" Select 触发器（包含"沪深"或"全部"）
        listed_board_select = page.locator('.ant-select:has(.ant-select-selection-item-content:has-text("全部"))').first
        if listed_board_select.count() == 0:
            # 尝试用 placeholder 找
            listed_board_select = page.locator('.ant-select').filter(has_text="上市地").first
        print(f"  找到上市地 Select: {listed_board_select.count() > 0}")

        # 简单做法：先取消"全部"，再勾选具体
        # 展开下拉
        if listed_board_select.count() > 0:
            listed_board_select.click()
            time.sleep(0.5)
            # 取消"全部"
            all_option = page.locator('.ant-select-item-option:has-text("全部")').first
            if all_option.count() > 0:
                all_option.click()
                time.sleep(0.3)
                # 重新打开
                listed_board_select.click()
                time.sleep(0.3)
            # 勾选"上海主板"
            sh_option = page.locator('.ant-select-item-option:has-text("上海主板")').first
            if sh_option.count() > 0:
                sh_option.click()
                time.sleep(0.3)
            # 勾选"创业板"
            cyb_option = page.locator('.ant-select-item-option:has-text("创业板")').first
            if cyb_option.count() > 0:
                cyb_option.click()
                time.sleep(0.3)
            # 关闭下拉（点击其他位置）
            page.locator('body').click(position={"x": 100, "y": 100})
            time.sleep(0.3)

        page.screenshot(path=f"{OUT_DIR}/v2_63_multi_board_selected.png", full_page=True)
        print("截图：v2_63_multi_board_selected.png")

        page.click('[data-testid="start-screener"]')
        page.wait_for_timeout(2500)
        page.screenshot(path=f"{OUT_DIR}/v2_63_multi_board_result.png", full_page=True)
        print("截图：v2_63_multi_board_result.png")

        total_text_63 = page.locator('span:has-text("共")').first.text_content() if page.locator('span:has-text("共")').count() > 0 else "未找到"
        rows_63 = page.locator('table tbody tr').all()
        print(f"  顶部 total: {total_text_63.strip() if total_text_63 else '无'}")
        print(f"  表格行数: {len(rows_63)}")
        for i, row in enumerate(rows_63[:5]):
            cells = row.locator('td').all_text_contents()
            print(f"  第{i+1}行: {' | '.join([c.strip() for c in cells[:6] if c.strip()])}")

        # ============================================
        # 汇总
        # ============================================
        print("\n=== /api/stocks/ 请求汇总 ===")
        for i, req in enumerate(api_requests):
            # 截短 URL 中过长的数字
            url = req['url']
            print(f"  [{i+1}] {url[:200]}{'...' if len(url) > 200 else ''}")

        with open(f"{OUT_DIR}/v2_api_requests.json", "w", encoding="utf-8") as f:
            json.dump(api_requests, f, ensure_ascii=False, indent=2)

        print(f"\n=== Console 错误 ({len(console_errors)} 条) ===")
        for err in console_errors[:5]:
            print(f"  {err[:200]}")

        time.sleep(2)
        browser.close()


if __name__ == "__main__":
    main()
