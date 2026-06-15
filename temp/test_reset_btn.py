"""
验证：
1. 底部有「▶开始选股」和「重置」两个按钮并排
2. 先选「RSI超卖」预设 → 条件出现 → 点「重置」→ 条件清空
"""
import asyncio, sys
from playwright.async_api import async_playwright

URL = "http://localhost:5173/"

async def chip_text(page) -> list[str]:
    rows = page.locator('[data-testid^="condition-row-wrap-"]')
    n = await rows.count()
    out = []
    for i in range(n):
        row = rows.nth(i)
        op = await row.locator('[data-testid^="condition-row-op-"]').inner_text()
        field_el = row.locator('[data-testid^="condition-row-"][data-field]')
        label = await field_el.inner_text()
        out.append(f"{op.strip()} {label.strip()}")
    return out

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)

        print("=" * 60)
        print(f"打开 {URL}")
        await page.goto(URL, wait_until="networkidle")
        await page.wait_for_selector('[data-testid="condition-builder"]', timeout=10000)

        # Step 1: 验证底部按钮
        print("\n[Step 1] 验证底部有「开始选股」和「重置」按钮并排")
        start_btn = page.locator('[data-testid="start-screener"]')
        reset_btn = page.locator('[data-testid="reset-screener"]')
        assert await start_btn.is_visible(), "开始选股按钮不可见"
        assert await reset_btn.is_visible(), "重置按钮不可见"
        start_text = await start_btn.inner_text()
        reset_text = await reset_btn.inner_text()
        print(f"  开始选股: {start_text.strip()}")
        print(f"  重置: {reset_text.strip()}")
        assert "开始选股" in start_text, f"开始选股按钮文本不对: {start_text}"
        assert "重置" in reset_text, f"重置按钮文本不对: {reset_text}"

        # Step 2: 点击预设添加条件
        print("\n[Step 2] 点击 RSI超卖 预设")
        await page.locator('[data-testid="preset-rsi_oversold"]').click()
        await page.wait_for_timeout(300)
        chips = await chip_text(page)
        print(f"  条件列表: {chips}")
        assert len(chips) == 1, f"应有 1 个条件，实际 {len(chips)}"

        # Step 3: 点击重置
        print("\n[Step 3] 点击底部「重置」按钮")
        await page.locator('[data-testid="reset-screener"]').click()
        await page.wait_for_timeout(300)
        chips = await chip_text(page)
        print(f"  条件列表: {chips}")
        assert len(chips) == 0, f"重置后应有 0 个条件，实际 {len(chips)}"

        # 截图
        await page.screenshot(path="/Users/zhangk/workspace/Quantitative_trading/temp/test_reset_result.png", full_page=True)

        if errors:
            print(f"\n⚠️  页面错误 {len(errors)} 条:")
            for e in errors[:5]: print(f"  {e}")
        else:
            print("\n✅ 无页面错误")

        print("\n" + "=" * 60)
        print("🎉 全部测试通过！")
        await browser.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except AssertionError as e:
        print(f"\n❌ 失败: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 异常: {e}")
        import traceback; traceback.print_exc()
        sys.exit(2)