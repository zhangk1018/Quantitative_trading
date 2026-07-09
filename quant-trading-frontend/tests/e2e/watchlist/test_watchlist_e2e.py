"""
自选股模块 E2E 回归测试 (pytest-asyncio + Playwright)

覆盖：P0 核心修复验证 + P1 边界场景 + 竞态/性能/错误路径

运行方式：
    cd quant-trading-frontend && python3 -m pytest tests/e2e/watchlist/ -v -c tests/e2e/pytest.ini

依赖：需先启动前端开发服务器 (npm run dev)
"""

import pytest
import pytest_asyncio
import json
from playwright.async_api import async_playwright, Page, Browser, Route

BASE = "http://localhost:5173"

# ============================================================
# 辅助函数
# ============================================================

async def get_storage(page: Page) -> dict:
    """读取 localStorage 中的 watchlist 数据"""
    return await page.evaluate("""
        (() => { const r = localStorage.getItem('watchlist'); return r ? JSON.parse(r) : {}; })()
    """)


async def mock_picker_api(page: Page):
    """为选股器 API 注入 mock 数据，返回 10 只虚拟股票，消除对外部后端的依赖"""

    async def handler(route: Route):
        url = route.request.url
        if "stock_codes" in url:
            # 行情请求（watchlist 页面），放行到真实后端
            await route.continue_()
            return
        # 选股器请求，返回 mock 数据
        items = [
            {"stock_code": f"600{i:03d}", "stock_name": f"测试股{i:03d}",
             "close": 10.0 + i, "change_pct": 1.0, "pe": 15.0, "pe_ttm": 14.0,
             "pb": 2.0, "market_cap": 100000, "amount": 50000, "turnover_rate": 2.0,
             "listed_board": "主板"}
            for i in range(10)
        ]
        await route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"code": 0, "data": {"items": items, "total": len(items)}}),
        )

    await page.route("**/api/stocks/**", handler)


async def add_stock_via_search(page: Page, code: str):
    """通过搜索弹窗添加股票到默认分组（沪深）
    
    force=True 原因：Antd Modal 关闭后 ant-modal-wrap div 残留拦截 pointer events
    """
    await page.locator('[data-testid="watchlist-add-btn"]').click(force=True)
    await page.wait_for_selector('[data-testid="watchlist-search-input"]', state="visible", timeout=5000)
    await page.fill('[data-testid="watchlist-search-input"]', code)
    await page.locator('[data-testid="watchlist-search-modal-ok"]').click(force=True)
    # handleAdd 不自动关闭 modal，手动点取消
    await page.locator('[data-testid="watchlist-search-modal-cancel"]').click(force=True)
    await page.wait_for_selector('[data-testid="watchlist-search-input"]', state="hidden", timeout=5000)


async def add_stock_to_group(page: Page, code: str, group: str):
    """通过搜索弹窗添加股票到指定分组"""
    await page.locator('[data-testid="watchlist-add-btn"]').click(force=True)
    await page.wait_for_selector('[data-testid="watchlist-search-input"]', state="visible", timeout=5000)
    await page.fill('[data-testid="watchlist-search-input"]', code)
    # 模拟人工点击 Select 下拉
    await page.locator('[data-testid="watchlist-search-group-select"]').click()
    await page.wait_for_timeout(300)  # Select 下拉展开动画需要固定延时
    option = page.locator(f'.ant-select-item-option-content:text-is("{group}")')
    await option.wait_for(state="visible", timeout=5000)
    await option.click(force=True)
    await page.locator('[data-testid="watchlist-search-modal-ok"]').click(force=True)
    await page.locator('[data-testid="watchlist-search-modal-cancel"]').click(force=True)
    await page.wait_for_selector('[data-testid="watchlist-search-input"]', state="hidden", timeout=5000)


async def create_custom_group(page: Page, name: str):
    """创建自定义分组（使用 Enter 键提交，handleCreateGroup 自动关闭 modal）"""
    await page.locator('[data-testid="watchlist-create-group-btn"]').click(force=True)
    await page.wait_for_selector('[data-testid="watchlist-create-group-input"]', state="visible", timeout=5000)
    await page.fill('[data-testid="watchlist-create-group-input"]', name)
    await page.press('[data-testid="watchlist-create-group-input"]', 'Enter')
    await page.wait_for_selector('[data-testid="watchlist-create-group-input"]', state="hidden", timeout=5000)


async def delete_stock_from_table(page: Page, code: str):
    """从表格中删除股票：切换到"全部" → 点击删除 → 确认"""
    await page.locator('[data-testid="watchlist-filter-all"]').click(force=True)
    await page.wait_for_selector(f'[data-testid="watchlist-delete-{code}"]', state="visible", timeout=5000)
    await page.locator(f'[data-testid="watchlist-delete-{code}"]').click(force=True)
    await page.wait_for_selector(f'[data-testid="watchlist-popconfirm-ok-{code}"]', state="visible", timeout=5000)
    await page.evaluate(f"""
        document.querySelector('[data-testid="watchlist-popconfirm-ok-{code}"]').click();
    """)
    await page.wait_for_selector(f'[data-testid="watchlist-row-{code}"]', state="hidden", timeout=5000)


async def wait_for_table(page: Page):
    await page.wait_for_selector('[data-testid="watchlist-table"]', state="visible", timeout=10000)


async def wait_for_row(page: Page, code: str):
    await page.wait_for_selector(f'[data-testid="watchlist-row-{code}"]', state="visible", timeout=10000)


async def wait_for_page_ready(page: Page):
    """等待页面稳定（空状态或表格出现）"""
    try:
        await page.wait_for_selector(
            '[data-testid="watchlist-empty"], [data-testid="watchlist-table"]',
            state="visible", timeout=10000,
        )
    except Exception:
        pass

# ============================================================
# Fixtures
# ============================================================

@pytest_asyncio.fixture
async def browser():
    """浏览器实例（整个模块共享）"""
    async with async_playwright() as p:
        b = await p.chromium.launch(headless=True)
        yield b
        await b.close()


@pytest_asyncio.fixture
async def page(browser: Browser):
    """每个测试独立的页面上下文"""
    ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
    pg = await ctx.new_page()
    yield pg
    await ctx.close()


async def reset_storage(page: Page, to: str = "/watchlist"):
    """清空存储并导航到指定页面，确保每个测试从干净状态开始"""
    await page.goto(f"{BASE}{to}")
    await page.evaluate("""
        localStorage.setItem('watchlist', JSON.stringify({version: 1, customGroups: [], stocks: {"全部": []}}));
    """)
    await page.reload()
    await wait_for_page_ready(page)

# ============================================================
# Test Cases
# ============================================================

class TestWatchlistEmptyState:
    """P1: 空状态验证"""

    async def test_empty_state_ui(self, page: Page):
        await reset_storage(page)
        empty = await page.wait_for_selector('[data-testid="watchlist-empty"]', state="visible", timeout=5000)
        assert empty is not None, "空状态元素应存在"
        s = await get_storage(page)
        assert s.get("version") == 1
        assert len(s.get("customGroups", [])) == 0


class TestWatchlistBatchAdd:
    """P0: BATCH_ADD_STOCKS 批量添加（使用 page.route mock 选股器接口）"""

    async def test_batch_add_from_picker(self, page: Page):
        """从选股页批量添加：UI 和 localStorage 一致性"""
        await reset_storage(page, "/picker")
        # 注：使用真实后端 API 数据，未 mock
        # 选股器数据来自后端 /api/stocks/ 接口，需要后端服务正常运行

        # 等待选股器加载完成
        start_btn = await page.query_selector('[data-testid="start-screener"]')
        if start_btn:
            await start_btn.click()
        await page.wait_for_selector('[data-testid^="row-checkbox-"]', state="visible", timeout=10000)

        checkboxes = await page.query_selector_all('[data-testid^="row-checkbox-"]')
        codes = []
        for i in range(min(5, len(checkboxes))):
            testid = await checkboxes[i].get_attribute("data-testid")
            code = testid.replace("row-checkbox-", "")
            codes.append(code)
            await checkboxes[i].click()

        assert len(codes) >= 3, f"至少选中 3 只，实际 {len(codes)}"

        # 等待 selectedCount > 0：按钮文字出现 "(N)" 表示已有选中
        await page.wait_for_function(
            """() => {
                const btn = document.querySelector('[data-testid="add-to-watchlist-btn"]');
                return btn && btn.textContent && /\\(\\d+\\)/.test(btn.textContent);
            }""",
            timeout=5000,
        )
        # 等待 React 事件处理器完成更新（selectedCount 变化后 useCallback 重建 onClick）
        await page.wait_for_timeout(200)

        # 使用 page.evaluate 在确认 selectedCount>0 后立即触发点击
        result = await page.evaluate("""
            () => {
                const btn = document.querySelector('[data-testid="add-to-watchlist-btn"]');
                if (!btn) return 'no-btn';
                const text = btn.textContent || '';
                const match = text.match(/\\((\\d+)\\)/);
                if (!match) return 'no-count';
                btn.click();
                return 'clicked';
            }
        """)
        assert result == 'clicked', f"按钮点击失败: {result}"

        # ant-modal-root 的 bounding box 高度为 0，Playwright 判定为 hidden
        # 改用 .ant-modal-wrap 检查可见性（该元素为全屏 overlay，bounding box 正常）
        await page.wait_for_selector('[data-testid="add-to-watchlist-modal"] .ant-modal-wrap', state="visible", timeout=5000)
        await page.locator('[data-testid="add-to-watchlist-modal"]').last.locator('.ant-btn-primary').click(force=True)
        await page.wait_for_selector('[data-testid="add-to-watchlist-modal"]', state="hidden", timeout=5000)

        await page.goto(f"{BASE}/watchlist")
        await wait_for_table(page)

        for code in codes:
            row = await page.query_selector(f'[data-testid="watchlist-row-{code}"]')
            assert row is not None, f"股票 {code} 应在表格中"

        s = await get_storage(page)
        all_codes = set()
        for c_list in s.get("stocks", {}).values():
            for c in c_list:
                all_codes.add(c)
        assert len(all_codes) >= len(codes)

    async def test_batch_add_dedup(self, page: Page):
        """批量添加去重：重复股票在每组内最多出现 1 次"""
        await reset_storage(page, "/picker")

        start_btn = await page.query_selector('[data-testid="start-screener"]')
        if start_btn:
            await start_btn.click()
        await page.wait_for_selector('[data-testid^="row-checkbox-"]', state="visible", timeout=10000)

        checkboxes = await page.query_selector_all('[data-testid^="row-checkbox-"]')
        for i in range(min(5, len(checkboxes))):
            await checkboxes[i].click()

        # 等待 selectedCount > 0
        await page.wait_for_function(
            """() => {
                const btn = document.querySelector('[data-testid="add-to-watchlist-btn"]');
                return btn && btn.textContent && /\\(\\d+\\)/.test(btn.textContent);
            }""",
            timeout=5000,
        )
        await page.wait_for_timeout(200)
        result = await page.evaluate("""
            () => {
                const btn = document.querySelector('[data-testid="add-to-watchlist-btn"]');
                if (!btn) return 'no-btn';
                const text = btn.textContent || '';
                const match = text.match(/\\((\\d+)\\)/);
                if (!match) return 'no-count';
                btn.click();
                return 'clicked';
            }
        """)
        assert result == 'clicked', f"按钮点击失败: {result}"
        await page.wait_for_selector('[data-testid="add-to-watchlist-modal"] .ant-modal-wrap', state="visible", timeout=5000)
        await page.locator('[data-testid="add-to-watchlist-modal"]').last.locator('.ant-btn-primary').click(force=True)
        await page.wait_for_selector('[data-testid="add-to-watchlist-modal"]', state="hidden", timeout=5000)

        await page.goto(f"{BASE}/watchlist")
        await wait_for_table(page)

        s = await get_storage(page)
        for group, c_list in s.get("stocks", {}).items():
            if not isinstance(c_list, list):
                continue
            # 验证每组内无重复股票
            unique = set(c_list)
            assert len(c_list) == len(unique), f"{group} 存在重复: {len(c_list)} 条记录, {len(unique)} 只唯一股票"


class TestWatchlistDelete:
    """P0: 删除逻辑验证"""

    async def test_system_group_delete_cascading(self, page: Page):
        """从系统分组删除 → 所有分组连锁清除"""
        await reset_storage(page)
        await add_stock_via_search(page, "000001")

        s = await get_storage(page)
        assert "000001" in str(s.get("stocks", {}))

        await delete_stock_from_table(page, "000001")

        s = await get_storage(page)
        for group, codes in s.get("stocks", {}).items():
            assert "000001" not in codes, f"{group} 不应含 000001"

    async def test_custom_group_delete_retain_system(self, page: Page):
        """自建分组删除时跨分组保留：股票仍在其他自建分组时，系统分组应保留"""
        await reset_storage(page)

        await create_custom_group(page, "A组")
        await create_custom_group(page, "B组")

        await add_stock_to_group(page, "000001", "A组")
        await wait_for_row(page, "000001")
        await add_stock_to_group(page, "000001", "B组")

        s = await get_storage(page)
        stocks = s.get("stocks", {})
        for g in ["全部", "沪深", "A组", "B组"]:
            assert "000001" in (stocks.get(g) or []), f"{g} 应含 000001"

        # 从 A组 删除
        await page.locator('[data-testid="watchlist-filter-A组"]').click(force=True)
        await page.wait_for_selector('[data-testid="watchlist-delete-000001"]', state="visible", timeout=5000)
        await page.locator('[data-testid="watchlist-delete-000001"]').click(force=True)
        await page.wait_for_selector('[data-testid="watchlist-popconfirm-ok-000001"]', state="visible", timeout=5000)
        await page.evaluate("""
            document.querySelector('[data-testid="watchlist-popconfirm-ok-000001"]').click();
        """)
        await page.wait_for_selector('[data-testid="watchlist-row-000001"]', state="hidden", timeout=5000)

        s = await get_storage(page)
        stocks = s.get("stocks", {})
        assert "000001" not in (stocks.get("A组") or []), "A组 不应含 000001"
        for g in ["全部", "沪深", "B组"]:
            assert "000001" in (stocks.get(g) or []), f"{g} 应仍含 000001（跨分组保留）"

    async def test_custom_group_delete_remove_all(self, page: Page):
        """自建分组删除时：股票不再属于任何自建分组时，系统分组也应清除"""
        await reset_storage(page)

        await create_custom_group(page, "C组")
        await add_stock_to_group(page, "000001", "C组")
        await wait_for_row(page, "000001")

        s = await get_storage(page)
        stocks = s.get("stocks", {})
        for g in ["全部", "沪深", "C组"]:
            assert "000001" in (stocks.get(g) or []), f"{g} 应含 000001"

        # 从 C组 删除
        await page.locator('[data-testid="watchlist-filter-C组"]').click(force=True)
        await page.wait_for_selector('[data-testid="watchlist-delete-000001"]', state="visible", timeout=5000)
        await page.locator('[data-testid="watchlist-delete-000001"]').click(force=True)
        await page.wait_for_selector('[data-testid="watchlist-popconfirm-ok-000001"]', state="visible", timeout=5000)
        await page.evaluate("""
            document.querySelector('[data-testid="watchlist-popconfirm-ok-000001"]').click();
        """)
        await page.wait_for_selector('[data-testid="watchlist-row-000001"]', state="hidden", timeout=5000)

        s = await get_storage(page)
        for group, codes in s.get("stocks", {}).items():
            assert "000001" not in codes, f"{group} 不应含 000001"


class TestWatchlistInteractions:
    """P1: 交互与一致性"""

    async def test_sort_interaction(self, page: Page):
        """排序交互：点击表头排序后表格仍存在"""
        await reset_storage(page)
        await add_stock_via_search(page, "000001")
        await add_stock_via_search(page, "600000")
        await wait_for_table(page)

        header = await page.query_selector('[data-testid="watchlist-table"] th:has-text("代码")')
        if not header:
            header = await page.query_selector('[data-testid="watchlist-table"] th:has-text("股票")')
        if header:
            await header.click(force=True)
            # 排序后表格容器不变，仅行顺序变化，直接断言即可
            await page.wait_for_selector('[data-testid="watchlist-table"]', state="visible", timeout=5000)

        table = await page.query_selector('[data-testid="watchlist-table"]')
        assert table is not None, "排序后表格应仍存在"

    async def test_storage_ui_consistency(self, page: Page):
        """localStorage 与 UI 一致性：添加/删除双向同步"""
        await reset_storage(page)
        await add_stock_via_search(page, "000001")

        s = await get_storage(page)
        row = await page.query_selector('[data-testid="watchlist-row-000001"]')
        assert row is not None, "UI 应显示 000001"
        assert "000001" in str(s.get("stocks", {}))

        await delete_stock_from_table(page, "000001")

        s = await get_storage(page)
        row = await page.query_selector('[data-testid="watchlist-row-000001"]')
        assert row is None, "UI 不应含 000001"
        for group, codes in s.get("stocks", {}).items():
            assert "000001" not in codes

    async def test_schema_version(self, page: Page):
        """Schema 版本号：初始和操作后 version 始终为 1"""
        await reset_storage(page)
        s = await get_storage(page)
        assert s.get("version") == 1

        await add_stock_via_search(page, "000001")
        s = await get_storage(page)
        assert s.get("version") == 1


class TestWatchlistRaceCondition:
    """P1: 竞态条件验证（AbortController + finally 匹配检查）"""

    @pytest.mark.slow
    async def test_rapid_group_switch(self, page: Page):
        """快速连续切换分组：旧请求被取消，最终状态与最后选中分组一致"""
        await reset_storage(page)
        await add_stock_via_search(page, "000001")
        await add_stock_via_search(page, "600000")
        await wait_for_table(page)

        # 快速连续切换分组（50ms 间隔模拟连续点击，不等待响应）
        await page.locator('[data-testid="watchlist-filter-沪深"]').click(force=True, no_wait_after=True)
        await page.wait_for_timeout(50)
        await page.locator('[data-testid="watchlist-filter-all"]').click(force=True, no_wait_after=True)
        await page.wait_for_timeout(50)
        await page.locator('[data-testid="watchlist-filter-沪深"]').click(force=True, no_wait_after=True)
        await page.wait_for_timeout(50)
        await page.locator('[data-testid="watchlist-filter-all"]').click(force=True, no_wait_after=True)

        # 等待 refreshing spinner 消失（最终请求完成）
        await page.wait_for_selector('[data-testid="watchlist-refreshing-spinner"]', state="hidden", timeout=10000)

        # 验证表格有数据，且页面不处于 loading 状态
        rows = await page.query_selector_all('[data-testid^="watchlist-row-"]')
        assert len(rows) > 0, "快速切换后表格应有数据"
        loading = await page.query_selector('[data-testid="watchlist-quotes-loading"]')
        assert loading is None, "loading 状态不应卡死"


class TestWatchlistPerformance:
    """P1: 性能基准测试（批量添加渲染耗时 + localStorage 写入次数）"""

    @pytest.mark.slow
    async def test_batch_add_many_performance(self, page: Page):
        """通过 addMany 批量添加 50 只股票，渲染耗时 < 800ms，localStorage 写入 ≤ 1 次"""
        await reset_storage(page)
        # 等待页面稳定（空状态出现），确保组件已挂载
        await page.wait_for_selector('[data-testid="watchlist-empty"]', state="visible", timeout=5000)

        # 确认 helper 已就绪（WatchlistPage 挂载后通过 useEffect 注册）
        await page.wait_for_function(
            "() => window.__watchlistHelpers__ && typeof window.__watchlistHelpers__.addMany === 'function'",
            timeout=5000,
        )

        # 注入 localStorage.setItem 调用计数器
        await page.evaluate("""
            let setItemCount = 0;
            const originalSetItem = localStorage.setItem.bind(localStorage);
            localStorage.setItem = (key, value) => {
                if (key === 'watchlist') setItemCount++;
                originalSetItem(key, value);
            };
            window.__setItemCount = () => setItemCount;
        """)

        # 生成 50 个虚拟股票代码
        codes = [f"600{i:03d}" for i in range(50)]

        # 调用 addMany 并测量耗时
        result = await page.evaluate(f"""
            (() => {{
                const start = performance.now();
                const r = window.__watchlistHelpers__.addMany({codes}, '全部');
                const end = performance.now();
                return {{ ...r, duration: end - start }};
            }})()
        """)

        added = result.get("added", 0)
        duration = result.get("duration", 0)
        assert added >= 45, f"应添加 ≥45 只（跳过已在分组中的），实际 {added}"
        # 阈值 800ms 含环境容差，通过时记录实际值供优化参考
        assert duration < 800, f"渲染耗时 {duration:.0f}ms > 800ms"

        # 等待 React 渲染完成，UI 出现新股票行
        await wait_for_row(page, "600000")

        # 验证 localStorage 写入次数（BATCH_ADD_STOCKS 应只触发一次 dispatch → 一次 persist）
        write_count = await page.evaluate("window.__setItemCount()")
        assert write_count <= 1, f"localStorage 写入 {write_count} 次，预期 ≤1 次"


class TestWatchlistErrorHandling:
    """P1: 错误路径测试（page.route 拦截行情接口）"""

    @pytest.mark.slow
    async def test_api_error_with_cache(self, page: Page):
        """行情接口失败时显示错误横幅，已缓存数据仍显示，重试后恢复"""
        await reset_storage(page)
        await add_stock_via_search(page, "000001")
        await wait_for_row(page, "000001")

        # 等待初始行情加载完成
        await page.wait_for_selector('[data-testid="watchlist-quotes-loading"]', state="hidden", timeout=10000)

        # 确认缓存数据已存在
        rows_before = await page.query_selector_all('[data-testid^="watchlist-row-"]')
        assert len(rows_before) > 0, "缓存数据应存在"

        # 拦截行情接口，返回 500 错误
        await page.route("**/api/stocks/**", lambda route: route.fulfill(
            status=500,
            body='{"code":500,"message":"Server Error"}',
        ))

        # 点击刷新按钮触发行情请求
        await page.locator('[data-testid="watchlist-refresh-btn"]').click(force=True)

        # 等待错误横幅出现
        await page.wait_for_selector('[data-testid="watchlist-error-banner"]', state="visible", timeout=10000)

        # 验证表格仍显示已缓存的股票
        rows_after = await page.query_selector_all('[data-testid^="watchlist-row-"]')
        assert len(rows_after) > 0, "缓存数据不应丢失"

        # 取消拦截，点击重试
        await page.unroute("**/api/stocks/**")
        await page.locator('[data-testid="watchlist-error-banner"] button').click(force=True)

        # 等待错误横幅消失
        await page.wait_for_selector('[data-testid="watchlist-error-banner"]', state="hidden", timeout=10000)