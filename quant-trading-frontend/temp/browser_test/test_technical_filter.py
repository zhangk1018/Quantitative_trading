"""
技术指标 浏览器自测（2026-06-16）
- 验证 4 个技术指标弹窗（MA/MACD/BOLL/RSI）的 UI 行为
- 验证点击指标 → 弹窗 → 选 Radio → 确定 → 写入 state → URL 序列化
- 验证取消、清除、回显等边界
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

        # 跟踪 /api/stocks/ 请求
        page.on("request", lambda req: api_requests.append(
            {"url": req.url, "method": req.method}
        ) if "/api/stocks/" in req.url else None)

        # 跟踪 console 错误
        console_errors = []
        page.on("console", lambda msg: console_errors.append(
            f"[{msg.type}] {msg.text}"
        ) if msg.type == "error" else None)

        print("=== 访问 /picker ===")
        page.goto("http://localhost:5173/picker", wait_until="networkidle", timeout=30000)
        time.sleep(1.0)

        # ====================================================================
        # 场景 1：技术指标面板默认折叠，徽标 0
        # ====================================================================
        print("\n=== 场景 1：技术指标面板默认折叠 ===")
        assert page.get_by_text("技术指标").is_visible(), "技术指标 header 不可见"
        assert not page.locator('[data-testid="technical-btn-ma"]').is_visible(), "折叠态下不应显示技术按钮"
        badge_text = page.locator('[data-testid="technical-filter-badge"]').text_content()
        print(f"  徽标: {badge_text}（期望 0）")
        assert badge_text == "0", f"徽标应为 0，实际 {badge_text}"
        page.screenshot(path=f"{OUT_DIR}/technical_01_collapsed.png", full_page=True)

        # ====================================================================
        # 场景 2：点击 header 展开，4 个指标按钮（MA/MACD/BOLL/RSI）都可见
        # ====================================================================
        print("\n=== 场景 2：展开技术指标面板 ===")
        page.locator('[data-testid="technical-filter-header"]').click()
        time.sleep(0.5)
        for btn_id in ["ma", "macd", "boll", "rsi"]:
            btn = page.locator(f'[data-testid="technical-btn-{btn_id}"]')
            assert btn.is_visible(), f"technical-btn-{btn_id} 不可见"
        page.screenshot(path=f"{OUT_DIR}/technical_02_expanded.png", full_page=True)

        # ====================================================================
        # 场景 3：MA 弹窗 — 选 "多头排列" + 确定
        # ====================================================================
        print("\n=== 场景 3：MA 弹窗 → 多头排列 ===")
        page.click('[data-testid="technical-btn-ma"]')
        time.sleep(0.5)
        # 用文本判断 Modal 是否打开（Antd Modal portal 用 is_visible() 不可靠）
        assert page.get_by_text("MA·日K").is_visible(), "MA 弹窗未打开（标题 'MA·日K' 不可见）"
        # 弹窗应展示 2 个选项（多头排列 / 空头排列）
        assert page.locator('[data-testid="technical-modal-ma-option-long_align"]').is_visible(), "多头排列不可见"
        assert page.locator('[data-testid="technical-modal-ma-option-short_align"]').is_visible(), "空头排列不可见"
        page.screenshot(path=f"{OUT_DIR}/technical_03_ma_modal.png", full_page=True)
        # 选"多头排列"
        page.click('[data-testid="technical-modal-ma-option-long_align"]')
        time.sleep(0.3)
        # 点击确定
        page.click('[data-testid="technical-modal-ma-confirm"]')
        time.sleep(0.5)
        # 弹窗应关闭（MA·日K 标题消失）
        assert not page.get_by_text("MA·日K").is_visible(), "MA 弹窗应关闭"
        # MA 按钮应变红且 data-selected=true
        ma_btn = page.locator('[data-testid="technical-btn-ma"]')
        assert ma_btn.get_attribute("data-selected") == "true", "MA 按钮应被选中"
        assert ma_btn.get_attribute("data-option") == "long_align", "data-option 应为 long_align"
        # 徽标=1
        badge_text = page.locator('[data-testid="technical-filter-badge"]').text_content()
        assert badge_text == "1", f"徽标应为 1，实际 {badge_text}"
        page.screenshot(path=f"{OUT_DIR}/technical_03_ma_confirmed.png", full_page=True)

        # ====================================================================
        # 场景 4：RSI 弹窗 — 选 "低位金叉" + 确定
        # ====================================================================
        print("\n=== 场景 4：RSI 弹窗 → 低位金叉 ===")
        page.click('[data-testid="technical-btn-rsi"]')
        time.sleep(0.5)
        assert page.get_by_text("RSI·日K").is_visible(), "RSI 弹窗未打开"
        # RSI 应有 4 个选项
        for opt in ["low_golden_cross", "high_death_cross", "top_divergence", "bottom_divergence"]:
            assert page.locator(f'[data-testid="technical-modal-rsi-option-{opt}"]').is_visible(), f"RSI {opt} 不可见"
        page.screenshot(path=f"{OUT_DIR}/technical_04_rsi_modal.png", full_page=True)
        page.click('[data-testid="technical-modal-rsi-option-low_golden_cross"]')
        time.sleep(0.3)
        page.click('[data-testid="technical-modal-rsi-confirm"]')
        time.sleep(0.5)
        # 验证 RSI 按钮变红
        rsi_btn = page.locator('[data-testid="technical-btn-rsi"]')
        assert rsi_btn.get_attribute("data-selected") == "true", "RSI 按钮应被选中"
        assert rsi_btn.get_attribute("data-option") == "low_golden_cross"
        # 徽标=2
        badge_text = page.locator('[data-testid="technical-filter-badge"]').text_content()
        assert badge_text == "2", f"徽标应为 2，实际 {badge_text}"

        # ====================================================================
        # 场景 5：MACD 弹窗 — 验证 Radio 列表
        # ====================================================================
        print("\n=== 场景 5：MACD 弹窗验证 ===")
        page.click('[data-testid="technical-btn-macd"]')
        time.sleep(0.5)
        assert page.get_by_text("MACD·日K").is_visible(), "MACD 弹窗未打开"
        # MACD 应有 4 个选项
        for opt in ["low_golden_cross", "bottom_divergence", "high_death_cross", "top_divergence"]:
            assert page.locator(f'[data-testid="technical-modal-macd-option-{opt}"]').is_visible(), f"MACD {opt} 不可见"
        # 取消
        page.click('[data-testid="technical-modal-macd-cancel"]')
        time.sleep(0.3)
        assert not page.get_by_text("MACD·日K").is_visible(), "MACD 弹窗应关闭"
        # 徽标仍为 2
        badge_text = page.locator('[data-testid="technical-filter-badge"]').text_content()
        assert badge_text == "2", f"取消后徽标应仍为 2，实际 {badge_text}"
        page.screenshot(path=f"{OUT_DIR}/technical_05_macd_cancelled.png", full_page=True)

        # ====================================================================
        # 场景 6：BOLL 弹窗 — 验证 Radio 列表
        # ====================================================================
        print("\n=== 场景 6：BOLL 弹窗验证 ===")
        page.click('[data-testid="technical-btn-boll"]')
        time.sleep(0.5)
        assert page.get_by_text("BOLL·日K").is_visible(), "BOLL 弹窗未打开"
        for opt in ["break_upper", "break_middle_up", "break_middle_down", "break_lower"]:
            assert page.locator(f'[data-testid="technical-modal-boll-option-{opt}"]').is_visible(), f"BOLL {opt} 不可见"
        page.click('[data-testid="technical-modal-boll-option-break_upper"]')
        time.sleep(0.3)
        page.click('[data-testid="technical-modal-boll-confirm"]')
        time.sleep(0.5)
        # 徽标=3
        badge_text = page.locator('[data-testid="technical-filter-badge"]').text_content()
        assert badge_text == "3", f"徽标应为 3，实际 {badge_text}"
        page.screenshot(path=f"{OUT_DIR}/technical_06_boll_confirmed.png", full_page=True)

        # ====================================================================
        # 场景 7：URL 序列化（点击"开始选股"）
        # ====================================================================
        print("\n=== 场景 7：URL 序列化 ===")
        page.click('[data-testid="start-screener"]')
        time.sleep(2.0)
        # 抓取最近的 /api/stocks/ 请求
        tech_requests = [r for r in api_requests if "tech_" in r["url"]]
        if tech_requests:
            print(f"  捕获到 {len(tech_requests)} 个含 tech_ 的请求")
            for req in tech_requests[-2:]:
                print(f"  URL: {req['url'][:300]}")
            # 验证最近一个请求包含 tech_ma=long_align, tech_rsi=low_golden_cross, tech_boll=break_upper
            latest = tech_requests[-1]["url"]
            assert "tech_ma=long_align" in latest, "URL 应包含 tech_ma=long_align"
            assert "tech_rsi=low_golden_cross" in latest, "URL 应包含 tech_rsi=low_golden_cross"
            assert "tech_boll=break_upper" in latest, "URL 应包含 tech_boll=break_upper"
            print("  ✓ URL 序列化正确")
        else:
            print("  ✗ 未捕获到 tech_ 参数请求")
        page.screenshot(path=f"{OUT_DIR}/technical_07_url_serialized.png", full_page=True)

        # ====================================================================
        # 场景 8：再次打开 MA 弹窗验证回显
        # ====================================================================
        print("\n=== 场景 8：MA 弹窗回显已选项 ===")
        page.click('[data-testid="technical-btn-ma"]')
        time.sleep(0.5)
        # 验证回显"多头排列"
        checked = page.evaluate("""
            () => {
                const radio = document.querySelector('input[type="radio"][value="long_align"]');
                return radio ? radio.checked : false;
            }
        """)
        assert checked, "回显 long_align radio 应为 checked 状态"
        # 关闭
        page.click('[data-testid="technical-modal-ma-cancel"]')
        time.sleep(0.3)
        page.screenshot(path=f"{OUT_DIR}/technical_08_echo.png", full_page=True)

        # ====================================================================
        # 场景 9：清除已选
        # ====================================================================
        print("\n=== 场景 9：清除已选 ===")
        # 再次打开 MA 弹窗
        page.click('[data-testid="technical-btn-ma"]')
        time.sleep(0.5)
        # 点击"清除已选"按钮
        clear_btn = page.locator('[data-testid="technical-modal-ma-clear"]')
        assert clear_btn.is_visible(), "清除已选按钮应可见"
        clear_btn.click()
        time.sleep(0.3)
        # MA 按钮应变未选中
        ma_btn = page.locator('[data-testid="technical-btn-ma"]')
        assert ma_btn.get_attribute("data-selected") == "false", "清除后 MA 按钮应未选中"
        # 徽标=2
        badge_text = page.locator('[data-testid="technical-filter-badge"]').text_content()
        assert badge_text == "2", f"清除后徽标应为 2，实际 {badge_text}"
        page.screenshot(path=f"{OUT_DIR}/technical_09_cleared.png", full_page=True)

        # ====================================================================
        # 汇总
        # ====================================================================
        print("\n=== /api/stocks/ 请求汇总 ===")
        for i, req in enumerate(api_requests):
            url = req['url']
            print(f"  [{i+1}] {url[:250]}{'...' if len(url) > 250 else ''}")

        with open(f"{OUT_DIR}/technical_api_requests.json", "w", encoding="utf-8") as f:
            json.dump(api_requests, f, ensure_ascii=False, indent=2)

        if console_errors:
            print(f"\n=== Console 错误 ({len(console_errors)} 条) ===")
            for err in console_errors[:5]:
                print(f"  {err[:200]}")
        else:
            print("\n✓ 无 console 错误")

        print("\n=== 全部 9 个技术指标场景验证完成 ===")
        time.sleep(2)
        browser.close()


if __name__ == "__main__":
    main()
