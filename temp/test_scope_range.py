"""
测试「范围」模块两条规则
- R-001 沪深+上海主板+全部：结果应只有上海 A 股
- R-002 沪深+上海主板+仅看自选：结果只有自选股（且属于上海主板）
"""
import asyncio, sys, re
from playwright.async_api import async_playwright

URL = "http://localhost:5173/"


async def get_table_data(page):
    rows = page.locator("tbody tr")
    n = await rows.count()
    items = []
    for i in range(n):
        cells = rows.nth(i).locator("td")
        if await cells.count() >= 4:
            code = (await cells.nth(2).inner_text()).strip()
            name = (await cells.nth(3).inner_text()).strip()
            items.append((code, name))
    return items


async def is_6_shanghai(code: str) -> bool:
    """判断股票代码是否属于上海主板（600/601/603/605 开头）"""
    return code.startswith(("600", "601", "603", "605"))


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await ctx.new_page()
        console_errors = []
        page.on("pageerror", lambda e: console_errors.append(f"pageerror: {e}"))
        page.on("console", lambda m: console_errors.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)

        # 监听 /api/stocks/ 请求
        api_calls = []
        def on_request(req):
            if "/api/stocks/" in req.url:
                api_calls.append(req.url)
        page.on("request", on_request)

        print("=" * 70)
        print("范围模块规则测试 R-001 / R-002")
        print("=" * 70)

        await page.goto(URL, wait_until="networkidle")
        await page.wait_for_selector('[data-testid="condition-builder"]', timeout=10000)
        await page.wait_for_timeout(2000)

        # ============= R-001: 沪深 + 上海主板 + 全部 =============
        print("\n[R-001] 沪深 + 上海主板 + 全部")
        # 1. 选中"沪深"市场
        await page.locator('input[name="market"]').nth(2).click()
        await page.wait_for_timeout(200)
        # 2. 打开上市地下拉
        listing_label = page.locator("label", has_text="上市地")
        listing_btn = listing_label.locator("..").locator("button").first
        await listing_btn.click()
        await page.wait_for_timeout(300)
        dropdown = page.locator("div.absolute.z-\\[60\\]")
        # 取消"全部"（如果选中了）
        all_checkbox = dropdown.locator("label").first.locator("input[type=checkbox]")
        if await all_checkbox.is_checked():
            await all_checkbox.click()
            await page.wait_for_timeout(200)
        # 只勾选"上海主板"
        sh_checkbox = dropdown.locator("label", has_text="上海主板").locator("input[type=checkbox]")
        await sh_checkbox.click()
        await page.wait_for_timeout(300)
        # 关闭下拉（点击外部）
        await page.locator("h4", has_text="范围").first.click()
        await page.wait_for_timeout(300)
        # 3. 确认"股票范围=全部"（默认）
        await page.locator('input[name="stockScope"]').first.click()
        await page.wait_for_timeout(200)
        # 4. 点击"开始选股"
        await page.locator('[data-testid="start-screener"]').click()
        await page.wait_for_timeout(3000)

        items = await get_table_data(page)
        print(f"  返回 {len(items)} 行，样例: {items[:5]}")
        # 全部应该是上海主板（6xxxxx）
        sh_count = 0
        non_sh = []
        for code, name in items:
            if await is_6_shanghai(code):
                sh_count += 1
            else:
                non_sh.append((code, name))
        # 看 API 是否带了 listed_board 参数
        last_api = api_calls[-1] if api_calls else "（无）"
        print(f"  最后一次 API: {last_api}")
        print(f"  上海主板: {sh_count} / {len(items)}")
        if non_sh:
            print(f"  ❌ 非上海主板股票: {non_sh[:5]}")
        r001_pass = (sh_count == len(items)) and len(items) > 0
        print(f"  R-001 结果: {'✅ 全部为上海主板' if r001_pass else '❌ 含其他市场股票'}")

        # ============= R-002: 沪深 + 上海主板 + 仅看自选 =============
        print("\n[R-002] 沪深 + 上海主板 + 仅看自选")
        # 先确保有自选股 — 选一只股票加入自选
        if items:
            # 选前 3 只加入自选
            for code, _ in items[:3]:
                pass
            # 用第一只
            first_code = items[0][0]
            # 找这一行
            first_row = page.locator("tbody tr").first
            await first_row.locator("input[type=checkbox]").click()
            await page.wait_for_timeout(200)
            # 点击"添加自选"
            add_wl = page.locator('[data-testid="add-to-watchlist"]')
            if await add_wl.is_enabled():
                await add_wl.click()
                await page.wait_for_timeout(500)
                print(f"  已添加 {first_code} 到自选")
            # 取消勾选
            await first_row.locator("input[type=checkbox]").click()
            await page.wait_for_timeout(200)
        # 切换"股票范围=仅看自选"
        await page.locator('input[name="stockScope"]').nth(1).click()
        await page.wait_for_timeout(300)
        # 重新选股
        api_calls.clear()
        await page.locator('[data-testid="start-screener"]').click()
        await page.wait_for_timeout(3000)

        items2 = await get_table_data(page)
        last_api2 = api_calls[-1] if api_calls else "（无）"
        print(f"  返回 {len(items2)} 行，样例: {items2[:5]}")
        print(f"  最后一次 API: {last_api2}")
        if len(items2) == 0:
            print("  ⚠️ 列表为空（用户可能没有自选股）")
            r002_pass = None  # 无法判断
        else:
            sh_count2 = 0
            non_sh2 = []
            for c, n in items2:
                if await is_6_shanghai(c):
                    sh_count2 += 1
                else:
                    non_sh2.append((c, n))
            print(f"  上海主板: {sh_count2} / {len(items2)}")
            if non_sh2:
                print(f"  ❌ 非上海主板: {non_sh2[:5]}")
            r002_pass = (sh_count2 == len(items2))
            print(f"  R-002 结果: {'✅ 仅含上海主板自选股' if r002_pass else '❌ 含其他股票'}")

        # ============= 总结 =============
        print("\n" + "=" * 70)
        print("测 试 结 论")
        print("=" * 70)
        # 看 API URL 是否包含 listed_board
        all_apis = "\n  ".join(api_calls[-3:]) if api_calls else "（无）"
        print(f"最近 3 次 API 请求:\n  {all_apis}")
        has_listed_board = any("listed_board" in url for url in api_calls)
        print(f"\n  API 是否带 listed_board 参数: {'✅ 是' if has_listed_board else '❌ 否'}")
        print(f"  R-001 通过: {'✅' if r001_pass else '❌'}")
        if r002_pass is not None:
            print(f"  R-002 通过: {'✅' if r002_pass else '❌'}")
        else:
            print(f"  R-002 无法判断（无自选股）")
        print(f"  页面错误: {len(console_errors)}")
        for e in console_errors[:5]:
            print(f"    {e}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())