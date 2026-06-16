"""
验证"红涨绿跌"配置功能
1. 访问 /config 页面，确认设置项可见
2. 默认应为"中国惯例（红涨绿跌）"
3. 切换到"国际惯例（绿涨红跌）"并截图
4. 访问 /picker 页面，执行选股，确认数据行颜色已切换
5. 切回"中国惯例"并截图
"""
import asyncio
import os
import sys
from playwright.async_api import async_playwright

OUT_DIR = "/Users/zhangk/workspace/Quantitative_trading/temp/color_scheme_test"
os.makedirs(OUT_DIR, exist_ok=True)

BASE = "http://localhost:5173"


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()

        # 清空 localStorage 重新开始
        await page.goto(f"{BASE}/config")
        await page.evaluate("() => localStorage.clear()")
        await page.reload()
        await page.wait_for_load_state("networkidle")

        print("=== Test 1: 打开 /config 页面 ===")
        await page.wait_for_selector("text=涨跌颜色方案", timeout=5000)
        await page.screenshot(path=f"{OUT_DIR}/01_config_default.png", full_page=True)
        print("OK /config page loaded, 'up-down color scheme' card visible")

        # 验证默认选中"中国惯例"
        cn_radio = page.locator("[data-testid=color-scheme-cn] input[type=radio]")
        cn_checked = await cn_radio.is_checked()
        assert cn_checked, "Default should be 'cn' (China convention)"
        print(f"OK Default selected: cn (China convention) - {cn_checked}")

        # 验证当前标签显示
        current_tag = await page.locator(".ant-tag").first.text_content()
        assert "China convention" in current_tag or "中国惯例" in current_tag, f"Current tag should mention China convention, got: {current_tag}"
        print(f"OK Current tag: {current_tag}")

        # 验证 cn 方案下涨色 = #EF5350 (红)
        cn_up_bg = await page.locator("[data-testid=scheme-cn-up-block]").evaluate(
            "el => getComputedStyle(el).backgroundColor"
        )
        print(f"  cn up color: {cn_up_bg} (expected rgb(239, 83, 80))")
        assert "239, 83, 80" in cn_up_bg, f"cn up should be red, got {cn_up_bg}"

        # 验证 cn 方案下跌色 = #26A69A (绿)
        cn_down_bg = await page.locator("[data-testid=scheme-cn-down-block]").evaluate(
            "el => getComputedStyle(el).backgroundColor"
        )
        print(f"  cn down color: {cn_down_bg} (expected rgb(38, 166, 154))")
        assert "38, 166, 154" in cn_down_bg, f"cn down should be green, got {cn_down_bg}"

        # 验证 intl 方案下颜色相反
        intl_up_bg = await page.locator("[data-testid=scheme-intl-up-block]").evaluate(
            "el => getComputedStyle(el).backgroundColor"
        )
        intl_down_bg = await page.locator("[data-testid=scheme-intl-down-block]").evaluate(
            "el => getComputedStyle(el).backgroundColor"
        )
        print(f"  intl up color: {intl_up_bg} (expected rgb(38, 166, 154))")
        print(f"  intl down color: {intl_down_bg} (expected rgb(239, 83, 80))")
        assert "38, 166, 154" in intl_up_bg
        assert "239, 83, 80" in intl_down_bg

        # === 切换到国际惯例 ===
        print("\n=== Test 2: Switch to international convention ===")
        await page.click("[data-testid=color-scheme-intl]")
        await page.wait_for_timeout(300)
        await page.screenshot(path=f"{OUT_DIR}/02_config_intl.png", full_page=True)

        # 验证 localStorage 已保存
        stored = await page.evaluate("() => localStorage.getItem('app_settings_color_scheme')")
        print(f"OK localStorage saved: {stored}")
        assert stored == "intl", f"Should be 'intl', got: {stored}"

        # 验证预览色块切换
        preview_up_bg = await page.locator("[data-testid=preview-up-block]").evaluate(
            "el => getComputedStyle(el).backgroundColor"
        )
        preview_down_bg = await page.locator("[data-testid=preview-down-block]").evaluate(
            "el => getComputedStyle(el).backgroundColor"
        )
        print(f"  preview up color: {preview_up_bg} (expected 38, 166, 154)")
        print(f"  preview down color: {preview_down_bg} (expected 239, 83, 80)")
        assert "38, 166, 154" in preview_up_bg
        assert "239, 83, 80" in preview_down_bg

        # === 访问选股页验证颜色应用 ===
        print("\n=== Test 3: Visit /picker to verify color applied ===")
        await page.goto(f"{BASE}/picker")
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(500)
        await page.screenshot(path=f"{OUT_DIR}/03_picker_intl_empty.png", full_page=True)

        # 点击"开始选股"
        await page.click("[data-testid=start-screener]")
        # 等待选股结果
        await page.wait_for_selector("table tbody tr", timeout=15000)
        await page.wait_for_timeout(500)
        await page.screenshot(path=f"{OUT_DIR}/04_picker_intl_results.png", full_page=True)

        # 检查第一行第二列（代码）之外的价格列是否有颜色
        rows = page.locator("table tbody tr")
        row_count = await rows.count()
        print(f"OK Result rows: {row_count}")
        assert row_count > 0, "Should have at least 1 row"

        # 取前 3 行，检查 close 和 change_pct 颜色
        sample = []
        for i in range(min(3, row_count)):
            row = rows.nth(i)
            close_cell = row.locator("td").nth(3)  # 收盘价列
            change_cell = row.locator("td").nth(4)  # 涨跌幅列
            close_color = await close_cell.evaluate("el => getComputedStyle(el).color")
            change_color = await change_cell.evaluate("el => getComputedStyle(el).color")
            change_text = await change_cell.text_content()
            sample.append((i, close_color, change_color, change_text))
            print(f"  Row {i}: close={close_color}, change_pct={change_text!r} color={change_color}")

        # 在国际惯例下：涨的颜色应为绿色 (38, 166, 154)，跌应为红色 (239, 83, 80)
        for idx, close_color, change_color, change_text in sample:
            sign = change_text.strip()[:1]
            is_up = sign == "+"
            expected_rgb = "38, 166, 154" if is_up else "239, 83, 80"
            assert expected_rgb in close_color, (
                f"Row {idx} close color wrong: up/down={sign} actual={close_color} expected={expected_rgb}"
            )
            assert expected_rgb in change_color, (
                f"Row {idx} change_pct color wrong: up/down={sign} actual={change_color} expected={expected_rgb}"
            )
        print(f"OK All {len(sample)} sample rows match international convention (green-up red-down)")

        # === 切回中国惯例，验证颜色反过来 ===
        print("\n=== Test 4: Switch back to China convention, verify color reversed ===")
        await page.goto(f"{BASE}/config")
        await page.wait_for_load_state("networkidle")
        await page.click("[data-testid=color-scheme-cn]")
        await page.wait_for_timeout(300)

        # 回到 picker
        await page.goto(f"{BASE}/picker")
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(300)
        await page.click("[data-testid=start-screener]")
        await page.wait_for_selector("table tbody tr", timeout=15000)
        await page.wait_for_timeout(500)
        await page.screenshot(path=f"{OUT_DIR}/05_picker_cn_results.png", full_page=True)

        rows2 = page.locator("table tbody tr")
        row_count2 = await rows2.count()
        sample2 = []
        for i in range(min(3, row_count2)):
            row = rows2.nth(i)
            close_cell = row.locator("td").nth(3)
            change_cell = row.locator("td").nth(4)
            close_color = await close_cell.evaluate("el => getComputedStyle(el).color")
            change_color = await change_cell.evaluate("el => getComputedStyle(el).color")
            change_text = await change_cell.text_content()
            sample2.append((i, close_color, change_color, change_text))
            print(f"  Row {i}: close={close_color}, change_pct={change_text!r} color={change_color}")

        # 中国惯例：涨=红 (239,83,80) 跌=绿 (38,166,154)
        for idx, close_color, change_color, change_text in sample2:
            sign = change_text.strip()[:1]
            is_up = sign == "+"
            expected_rgb = "239, 83, 80" if is_up else "38, 166, 154"
            assert expected_rgb in close_color, (
                f"Row {idx} close color wrong: up/down={sign} actual={close_color} expected={expected_rgb}"
            )
            assert expected_rgb in change_color, (
                f"Row {idx} change_pct color wrong: up/down={sign} actual={change_color} expected={expected_rgb}"
            )
        print(f"OK All {len(sample2)} sample rows match China convention (red-up green-down)")

        # 验证持久化：刷新后设置仍在
        print("\n=== Test 5: Persistence (reload page) ===")
        await page.goto(f"{BASE}/config")
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(800)
        await page.reload()
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(1500)
        # 直接验证 localStorage 和已渲染的色块
        stored_after = await page.evaluate("() => localStorage.getItem('app_settings_color_scheme')")
        assert stored_after == "cn", f"After reload localStorage should still be 'cn', got: {stored_after}"
        # 验证预览色块颜色（cn 应红涨绿跌）
        preview_up = await page.locator("[data-testid=preview-up-block]").evaluate(
            "el => getComputedStyle(el).backgroundColor"
        )
        preview_down = await page.locator("[data-testid=preview-down-block]").evaluate(
            "el => getComputedStyle(el).backgroundColor"
        )
        assert "239, 83, 80" in preview_up, f"After reload preview up should be red, got: {preview_up}"
        assert "38, 166, 154" in preview_down, f"After reload preview down should be green, got: {preview_down}"
        print(f"OK After reload localStorage={stored_after}, preview up={preview_up} (red), down={preview_down} (green)")

        print("\n========== All tests passed ==========")
        print(f"Screenshots saved to: {OUT_DIR}/")
        for f in sorted(os.listdir(OUT_DIR)):
            print(f"  - {f}")

        await browser.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except AssertionError as e:
        print(f"\n[FAIL] Assertion failed: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\n[FAIL] Test failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
