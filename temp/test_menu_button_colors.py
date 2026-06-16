"""
验证"菜单和按钮改回中性色"功能
1. 顶部菜单激活态应为蓝色（color-accent）
2. "开始选股" 主按钮应为蓝色
3. "保存策略"/"我的策略" 应为中性灰
4. "加入回测列表" 应为蓝色
5. 数据行的红绿不受影响（受颜色方案控制）
"""
import asyncio
import os
import sys
from playwright.async_api import async_playwright

OUT_DIR = "/Users/zhangk/workspace/Quantitative_trading/temp/menu_button_test"
os.makedirs(OUT_DIR, exist_ok=True)
BASE = "http://localhost:5173"

# 期望颜色
BLUE = "41, 98, 255"  # #2962FF
PANEL_BG = "42, 46, 57"  # #2A2E39 bg-card
BORDER = "42, 46, 57"  # #2A2E39 border-color


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()

        # 默认 cn（中国惯例）方案，打开 /picker
        await page.goto(f"{BASE}/picker")
        await page.evaluate("() => localStorage.clear()")
        await page.reload()
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(800)

        print("=== Test 1: 顶部菜单激活态 (默认在 /picker) ===")
        # 当前活跃菜单是"选股视图"
        active_menu = page.locator(".ant-layout-header .cursor-pointer").filter(has_text="选股视图")
        active_color = await active_menu.evaluate("el => getComputedStyle(el).color")
        active_border = await active_menu.evaluate(
            "el => getComputedStyle(el).borderBottomColor"
        )
        print(f"  active menu color: {active_color} (expected 41, 98, 255 blue)")
        print(f"  active menu border-bottom: {active_border}")
        assert "41, 98, 255" in active_color, f"菜单激活态应为蓝色，实际: {active_color}"
        print("OK Top menu active state is blue")

        print("\n=== Test 2: 开始选股 主按钮 (蓝色) ===")
        start_btn = page.locator("[data-testid=start-screener]")
        btn_bg = await start_btn.evaluate("el => getComputedStyle(el).backgroundColor")
        btn_border = await start_btn.evaluate("el => getComputedStyle(el).borderColor")
        print(f"  start-screener bg: {btn_bg} (expected 41, 98, 255)")
        print(f"  start-screener border: {btn_border}")
        assert "41, 98, 255" in btn_bg, f"开始选股主按钮应为蓝色，实际: {btn_bg}"
        print("OK Start-screener button is blue")

        # 触发选股以显示工具栏按钮
        print("\n=== Test 3: 触发选股后验证工具栏按钮 ===")
        await start_btn.click()
        await page.wait_for_selector("table tbody tr", timeout=15000)
        await page.wait_for_timeout(500)
        await page.screenshot(path=f"{OUT_DIR}/01_picker_cn_with_buttons.png", full_page=True)

        # 验证"保存策略"和"我的策略"为中性色
        save_btn = page.locator("button").filter(has_text="保存策略")
        my_btn = page.locator("button").filter(has_text="我的策略")
        save_bg = await save_btn.evaluate("el => getComputedStyle(el).backgroundColor")
        my_bg = await my_btn.evaluate("el => getComputedStyle(el).backgroundColor")
        save_color = await save_btn.evaluate("el => getComputedStyle(el).color")
        print(f"  保存策略 bg: {save_bg}")
        print(f"  保存策略 text color: {save_color}")
        print(f"  我的策略 bg: {my_bg}")
        # 中性色：bg 应该是 bg-card #2A2E39 = 42, 46, 57
        assert "42, 46, 57" in save_bg, f"保存策略应为中性色（bg-card），实际: {save_bg}"
        assert "42, 46, 57" in my_bg, f"我的策略应为中性色（bg-card），实际: {my_bg}"
        # 文字色应该是 text-primary（白色）
        assert "234, 236, 239" in save_color, f"保存策略文字色应为 text-primary，实际: {save_color}"
        print("OK 保存策略/我的策略 are neutral gray")

        # 验证底部"加入回测列表"为蓝色
        add_test_btn = page.locator("button").filter(has_text="加入回测列表")
        add_test_bg = await add_test_btn.evaluate("el => getComputedStyle(el).backgroundColor")
        add_test_color = await add_test_btn.evaluate("el => getComputedStyle(el).color")
        print(f"  加入回测列表 bg: {add_test_bg}")
        print(f"  加入回测列表 text color: {add_test_color}")
        # bg-color-accent/20 = 蓝色 20% 透明
        # text-color-accent = 蓝色
        assert "41, 98, 255" in add_test_color, f"加入回测列表文字色应为蓝色，实际: {add_test_color}"
        print("OK 加入回测列表 is blue accent")

        # 验证数据行颜色仍是红色（cn 红涨绿跌）
        print("\n=== Test 4: 数据行仍按 cn 方案红涨绿跌 ===")
        rows = page.locator("table tbody tr")
        row_count = await rows.count()
        print(f"  row count: {row_count}")
        for i in range(min(3, row_count)):
            row = rows.nth(i)
            change_cell = row.locator("td").nth(4)
            change_text = await change_cell.text_content()
            change_color = await change_cell.evaluate("el => getComputedStyle(el).color")
            sign = change_text.strip()[:1]
            is_up = sign == "+"
            expected = "239, 83, 80" if is_up else "38, 166, 154"  # 红涨绿跌
            assert expected in change_color, (
                f"行 {i} 数据行颜色不符: up/down={sign} 实际={change_color} 期望含 {expected}"
            )
            print(f"  Row {i}: {change_text!r} color={change_color} (cn 红涨绿跌 OK)")

        # 切换到国际惯例
        print("\n=== Test 5: 切换到国际惯例，数据行变绿涨红跌，按钮颜色不变 ===")
        await page.goto(f"{BASE}/config")
        await page.wait_for_load_state("networkidle")
        await page.click("[data-testid=color-scheme-intl]")
        await page.wait_for_timeout(300)

        await page.goto(f"{BASE}/picker")
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(500)
        await page.click("[data-testid=start-screener]")
        await page.wait_for_selector("table tbody tr", timeout=15000)
        await page.wait_for_timeout(500)
        await page.screenshot(path=f"{OUT_DIR}/02_picker_intl_with_buttons.png", full_page=True)

        # 验证菜单激活态仍然是蓝色
        active_menu2 = page.locator(".ant-layout-header .cursor-pointer").filter(has_text="选股视图")
        active_color2 = await active_menu2.evaluate("el => getComputedStyle(el).color")
        assert "41, 98, 255" in active_color2, f"菜单激活态应保持蓝色，实际: {active_color2}"
        print(f"  菜单激活态仍蓝色: {active_color2}")

        # 验证"开始选股"按钮仍然是蓝色（即使在 intl 方案下）
        start_btn2 = page.locator("[data-testid=start-screener]")
        btn_bg2 = await start_btn2.evaluate("el => getComputedStyle(el).backgroundColor")
        assert "41, 98, 255" in btn_bg2, f"开始选股按钮应保持蓝色，实际: {btn_bg2}"
        print(f"  开始选股按钮仍蓝色: {btn_bg2}")

        # 验证"加入回测列表"仍是蓝色
        add_test_btn2 = page.locator("button").filter(has_text="加入回测列表")
        add_test_color2 = await add_test_btn2.evaluate("el => getComputedStyle(el).color")
        assert "41, 98, 255" in add_test_color2
        print(f"  加入回测列表仍蓝色: {add_test_color2}")

        # 验证数据行现在是绿涨红跌
        rows2 = page.locator("table tbody tr")
        for i in range(min(3, await rows2.count())):
            row = rows2.nth(i)
            change_cell = row.locator("td").nth(4)
            change_text = await change_cell.text_content()
            change_color = await change_cell.evaluate("el => getComputedStyle(el).color")
            sign = change_text.strip()[:1]
            is_up = sign == "+"
            expected = "38, 166, 154" if is_up else "239, 83, 80"  # intl 绿涨红跌
            assert expected in change_color, (
                f"行 {i} 数据行颜色不符: up/down={sign} 实际={change_color} 期望含 {expected}"
            )
            print(f"  Row {i}: {change_text!r} color={change_color} (intl 绿涨红跌 OK)")

        # 完整页面截图
        await page.screenshot(path=f"{OUT_DIR}/03_full_view_intl.png", full_page=True)

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
