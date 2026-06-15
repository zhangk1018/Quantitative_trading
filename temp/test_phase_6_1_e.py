"""
Phase 6.1.e 实测：三个独立按钮 + 独立 op
- 点 AND + RSI超卖预设 → 验证 chip 显示 "AND RSI(6)"
- 切到 OR + 弹层加看涨吞没 → 验证新条件显示 "OR 看涨吞没"
- 验证旧条件 "AND RSI(6)" 不变成 "OR RSI(6)"
- 切到 NOT + 弹层加突破20日高点 → 验证新条件显示 "NOT 突破20日高点"
"""

import asyncio
import sys
from playwright.async_api import async_playwright

URL = "http://localhost:5173/"


async def chip_text(page) -> list[str]:
    """收集所有条件的完整文本 [op] ✓ 指标名"""
    rows = page.locator('[data-testid^="condition-row-wrap-"]')
    n = await rows.count()
    out = []
    for i in range(n):
        row = rows.nth(i)
        op = await row.locator(f'[data-testid^="condition-row-op-"]').inner_text()
        field_el = row.locator('[data-testid^="condition-row-"][data-field]')
        label = await field_el.inner_text()
        out.append(f"[{op.strip()}] {label.strip()}")
    return out


async def pending_op_active(page) -> str:
    """返回当前激活的 pendingOp"""
    for op in ("AND", "OR", "NOT"):
        btn = page.locator(f'[data-testid="pending-op-{op}"]')
        cls = await btn.get_attribute("class") or ""
        if "bg-up-green" in cls or "bg-blue-500" in cls or "bg-yellow-500" in cls:
            return op
    return "?"


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await ctx.new_page()
        # 收集控制台错误
        errors = []
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)

        print("=" * 60)
        print(f"打开 {URL}")
        await page.goto(URL, wait_until="networkidle")
        await page.wait_for_selector('[data-testid="condition-builder"]', timeout=10000)

        # 截图：初始状态
        await page.screenshot(path="/Users/zhangk/workspace/Quantitative_trading/temp/phase_6_1_e_0_initial.png", full_page=True)

        # ============ Step 1: 验证默认 pendingOp = AND ============
        print("\n[Step 1] 验证默认 pendingOp = AND")
        cur = await pending_op_active(page)
        print(f"  当前 pendingOp: {cur}")
        assert cur == "AND", f"默认 pendingOp 应为 AND，实际 {cur}"

        # ============ Step 2: 点击 RSI超卖 预设 ============
        print("\n[Step 2] 点击 'RSI超卖' 预设")
        await page.locator('[data-testid="preset-rsi_oversold"]').click()
        await page.wait_for_timeout(300)
        chips = await chip_text(page)
        print(f"  条件列表: {chips}")
        assert len(chips) == 1, f"应只有 1 个条件，实际 {len(chips)}"
        assert chips[0] == "[AND] ✓\nRSI(6)", f"条件应为 [AND] RSI(6)，实际 {chips[0]!r}"

        # ============ Step 3: 切换到 OR ============
        print("\n[Step 3] 切换 pendingOp 到 OR")
        await page.locator('[data-testid="pending-op-OR"]').click()
        await page.wait_for_timeout(200)
        cur = await pending_op_active(page)
        print(f"  当前 pendingOp: {cur}")
        assert cur == "OR", f"pendingOp 应为 OR，实际 {cur}"

        # 关键验证：旧条件不应变成 [OR]
        chips = await chip_text(page)
        print(f"  条件列表: {chips}")
        assert chips[0] == "[AND] ✓\nRSI(6)", (
            f"切到 OR 后旧条件不应改变！实际 {chips[0]!r}"
        )

        # ============ Step 4: 打开弹层 + 点击 "看涨吞没" ============
        print("\n[Step 4] 打开弹层，点击 '看涨吞没'")
        await page.locator('[data-testid="add-condition-0"]').click()
        await page.wait_for_selector('[data-testid="add-condition-panel"]', timeout=3000)
        await page.locator('[data-testid="add-condition-panel-pattern-pattern_bullish_engulfing"]').click()
        await page.wait_for_timeout(300)
        chips = await chip_text(page)
        print(f"  条件列表: {chips}")
        assert len(chips) == 2, f"应有 2 个条件，实际 {len(chips)}"
        assert chips[0] == "[AND] ✓\nRSI(6)", f"第 1 个条件应为 [AND] RSI(6)，实际 {chips[0]!r}"
        assert chips[1] == "[OR] ✓\n看涨吞没", f"第 2 个条件应为 [OR] 看涨吞没，实际 {chips[1]!r}"

        # 截图：AND + OR 状态
        await page.screenshot(path="/Users/zhangk/workspace/Quantitative_trading/temp/phase_6_1_e_1_and_or.png", full_page=True)

        # ============ Step 5: 切换到 NOT ============
        print("\n[Step 5] 切换 pendingOp 到 NOT")
        await page.locator('[data-testid="pending-op-NOT"]').click()
        await page.wait_for_timeout(200)
        cur = await pending_op_active(page)
        print(f"  当前 pendingOp: {cur}")
        assert cur == "NOT", f"pendingOp 应为 NOT，实际 {cur}"

        # 关键验证：前两个条件不应改变
        chips = await chip_text(page)
        print(f"  条件列表: {chips}")
        assert chips[0] == "[AND] ✓\nRSI(6)", f"切 NOT 后第 1 个条件不变，应为 [AND] RSI(6)，实际 {chips[0]!r}"
        assert chips[1] == "[OR] ✓\n看涨吞没", f"切 NOT 后第 2 个条件不变，应为 [OR] 看涨吞没，实际 {chips[1]!r}"

        # ============ Step 6: 打开弹层 + 点击 "突破20日高点" ============
        print("\n[Step 6] 打开弹层，点击 '突破20日高点'")
        await page.locator('[data-testid="add-condition-0"]').click()
        await page.wait_for_selector('[data-testid="add-condition-panel"]', timeout=3000)
        await page.locator('[data-testid="add-condition-panel-breakout-break_high_20"]').click()
        await page.wait_for_timeout(300)
        chips = await chip_text(page)
        print(f"  条件列表: {chips}")
        assert len(chips) == 3, f"应有 3 个条件，实际 {len(chips)}"
        assert chips[0] == "[AND] ✓\nRSI(6)", f"第 1 个条件应为 [AND] RSI(6)，实际 {chips[0]!r}"
        assert chips[1] == "[OR] ✓\n看涨吞没", f"第 2 个条件应为 [OR] 看涨吞没，实际 {chips[1]!r}"
        assert chips[2] == "[NOT] ✓\n突破20日高点", f"第 3 个条件应为 [NOT] 突破20日高点，实际 {chips[2]!r}"

        # 截图：AND + OR + NOT 状态
        await page.screenshot(path="/Users/zhangk/workspace/Quantitative_trading/temp/phase_6_1_e_2_and_or_not.png", full_page=True)

        # ============ Step 7: 点击 [AND] 标签循环切换到 OR ============
        print("\n[Step 7] 点击 [AND] 标签循环切换到 OR")
        # 找到第 1 个条件的 op 标签
        first_op = page.locator('[data-testid^="condition-row-op-"]').first
        await first_op.click()
        await page.wait_for_timeout(200)
        chips = await chip_text(page)
        print(f"  条件列表: {chips}")
        assert chips[0] == "[OR] ✓\nRSI(6)", f"点 [AND] 后应变 [OR]，实际 {chips[0]!r}"
        # 其它两个不应改变
        assert chips[1] == "[OR] ✓\n看涨吞没", f"第 2 个不变，实际 {chips[1]!r}"
        assert chips[2] == "[NOT] ✓\n突破20日高点", f"第 3 个不变，实际 {chips[2]!r}"

        # 继续点 → NOT
        await first_op.click()
        await page.wait_for_timeout(200)
        chips = await chip_text(page)
        print(f"  再点一次 → {chips[0]}")
        assert chips[0] == "[NOT] ✓\nRSI(6)", f"再点 [OR] 后应变 [NOT]，实际 {chips[0]!r}"

        # 继续点 → AND（循环回 AND）
        await first_op.click()
        await page.wait_for_timeout(200)
        chips = await chip_text(page)
        print(f"  再点一次 → {chips[0]}")
        assert chips[0] == "[AND] ✓\nRSI(6)", f"再点 [NOT] 后应变 [AND]，实际 {chips[0]!r}"

        # 截图：循环切换验证
        await page.screenshot(path="/Users/zhangk/workspace/Quantitative_trading/temp/phase_6_1_e_3_cycle.png", full_page=True)

        # ============ 报告 ============
        if errors:
            print(f"\n⚠️  页面错误 {len(errors)} 条:")
            for e in errors[:10]:
                print(f"  {e}")
        else:
            print("\n✅ 无页面错误")

        print("\n" + "=" * 60)
        print("🎉 全部测试通过！")
        print("=" * 60)
        await browser.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except AssertionError as e:
        print(f"\n❌ 断言失败: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 异常: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(2)
