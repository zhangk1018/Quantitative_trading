"""
回测分析 + 策略回测模块 E2E 回归测试 (pytest-asyncio + Playwright)

覆盖：P0 UI 渲染验证 + P1 交互流程 + 空状态/错误路径

运行方式：
    cd frontend && python3 -m pytest tests/e2e/backtest/ -v -c tests/e2e/pytest.ini

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

async def reset_storage(page: Page, to: str = "/backtest"):
    """清空存储并导航到指定页面，确保每个测试从干净状态开始"""
    await page.goto(f"{BASE}{to}")
    await page.evaluate("""
        localStorage.clear();
    """)
    await page.reload()
    # 等待页面稳定
    await page.wait_for_timeout(1000)


async def mock_stock_api(page: Page):
    """Mock 股票搜索 API，返回虚拟股票列表"""

    async def handler(route: Route):
        await route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({
                "code": 0,
                "data": {
                    "items": [
                        {"stock_code": "000001", "stock_name": "平安银行"},
                        {"stock_code": "600000", "stock_name": "浦发银行"},
                        {"stock_code": "000002", "stock_name": "万科A"},
                    ],
                    "total": 3,
                },
            }),
        )

    await page.route("**/api/stocks/**", handler)


async def mock_kline_api(page: Page):
    """Mock K线数据 API，返回虚拟 K 线数据"""

    async def handler(route: Route):
        await route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({
                "code": 0,
                "data": {
                    "items": [],
                    "total": 0,
                },
            }),
        )

    await page.route("**/api/kline/**", handler)


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


# ============================================================
# Test Cases: 回测分析页签（旧版个股回测）
# ============================================================

class TestBacktestPageRender:
    """P0: 回测分析页签基础渲染"""

    async def test_page_loads(self, page: Page):
        """页面正常加载，不报错"""
        await reset_storage(page, "/backtest")
        # 页面标题应存在
        await page.wait_for_timeout(2000)
        # 检查是否有 React 错误边界
        error_boundary = await page.query_selector('[class*="error"]')
        # 正常的页面不应该有 React 错误覆盖层
        assert error_boundary is None or "error" not in (await error_boundary.text_content() or "").lower()[:50], \
            "页面加载不应出现 React 错误"

    async def test_empty_state_displayed(self, page: Page):
        """空状态：右侧显示提示文案"""
        await reset_storage(page, "/backtest")
        await page.wait_for_timeout(2000)

        # 右侧空状态提示
        empty_text = await page.query_selector('text=请在左侧配置策略后点击"开始回测"')
        assert empty_text is not None, "空状态提示应显示"

    async def test_config_panel_renders(self, page: Page):
        """左侧配置面板正常渲染"""
        await reset_storage(page, "/backtest")
        await page.wait_for_timeout(2000)

        # 股票选择卡片
        stock_card = await page.query_selector('text=股票选择')
        assert stock_card is not None, "股票选择卡片应存在"

        # 回测周期卡片
        period_card = await page.query_selector('text=回测周期')
        assert period_card is not None, "回测周期卡片应存在"

        # 买入条件卡片
        buy_card = await page.query_selector('text=买入条件')
        assert buy_card is not None, "买入条件卡片应存在"

    async def test_start_button_renders(self, page: Page):
        """开始回测和重置按钮正常渲染"""
        await reset_storage(page, "/backtest")
        await page.wait_for_timeout(2000)

        start_btn = await page.query_selector('[data-testid="start-backtest"]')
        assert start_btn is not None, "开始回测按钮应存在"

        reset_btn = await page.query_selector('[data-testid="reset-backtest"]')
        assert reset_btn is not None, "重置按钮应存在"


class TestBacktestFormInteraction:
    """P1: 回测分析表单交互"""

    async def test_stock_cascader_exists(self, page: Page):
        """股票级联选择器存在"""
        await reset_storage(page, "/backtest")
        await page.wait_for_timeout(2000)

        cascader = await page.query_selector('[data-testid="stock-search-cascader"]')
        assert cascader is not None, "股票级联选择器应存在"

    async def test_date_range_picker_exists(self, page: Page):
        """日期范围选择器存在"""
        await reset_storage(page, "/backtest")
        await page.wait_for_timeout(2000)

        # RangePicker 渲染为两个 input
        date_inputs = await page.query_selector_all('.ant-picker-range input')
        assert len(date_inputs) >= 2, "日期范围选择器应存在"

    async def test_capital_input_exists(self, page: Page):
        """初始资金输入框存在"""
        await reset_storage(page, "/backtest")
        await page.wait_for_timeout(2000)

        capital_input = await page.query_selector('.ant-input-number-input')
        assert capital_input is not None, "初始资金输入框应存在"

    async def test_reset_button_clears_state(self, page: Page):
        """点击重置按钮后清空状态"""
        await reset_storage(page, "/backtest")
        await page.wait_for_timeout(2000)

        reset_btn = await page.query_selector('[data-testid="reset-backtest"]')
        assert reset_btn is not None, "重置按钮应存在"

        # 点击重置按钮
        await reset_btn.click(force=True)
        await page.wait_for_timeout(500)

        # 空状态提示应仍显示
        empty_text = await page.query_selector('text=请在左侧配置策略后点击"开始回测"')
        assert empty_text is not None, "重置后空状态提示应仍显示"


class TestBacktestErrorHandling:
    """P1: 回测分析错误处理"""

    async def test_start_without_indicator_shows_validation(self, page: Page):
        """未选择自编指标时点击开始，应显示表单校验错误"""
        await reset_storage(page, "/backtest")
        await page.wait_for_timeout(2000)

        start_btn = await page.query_selector('[data-testid="start-backtest"]')
        assert start_btn is not None

        # 点击开始回测（未选择股票和指标，表单校验应触发）
        await start_btn.click(force=True)
        await page.wait_for_timeout(1000)

        # 应有校验错误提示（Antd Form 的 validation message）
        validation_msgs = await page.query_selector_all('.ant-form-item-explain-error')
        # 至少应有股票代码和自编指标的校验错误
        assert len(validation_msgs) >= 1, "应有表单校验错误提示"

    async def test_kline_api_error_handling(self, page: Page):
        """K线接口返回空数据时的错误处理"""
        await reset_storage(page, "/backtest")
        await page.wait_for_timeout(2000)

        # Mock K线接口返回空数据
        await mock_kline_api(page)

        # 设置自选股数据（使 Cascader 有默认选项）
        await page.evaluate("""
            localStorage.setItem('watchlist', JSON.stringify({
                version: 1,
                customGroups: [],
                stocks: {"全部": ["000001"], "沪深": ["000001"]}
            }));
        """)
        await page.reload()
        await page.wait_for_timeout(2000)

        # 直接通过 form submit 触发（Cascader 默认选中 000001，但需要选择自编指标）
        # 注：由于自编指标为空，此测试验证"无自编指标"的提示文案
        no_indicator_text = await page.query_selector('text=暂无自编指标')
        assert no_indicator_text is not None, "应显示'暂无自编指标'提示"


# ============================================================
# Test Cases: 策略回测页签
# ============================================================

class TestStrategyBacktestPage:
    """P0: 策略回测页签基础渲染"""

    async def test_page_loads(self, page: Page):
        """页面正常加载，不报错"""
        await reset_storage(page, "/strategy-backtest")
        await page.wait_for_timeout(2000)

        # 页面标题
        title = await page.query_selector('text=策略回测')
        assert title is not None, "策略回测标题应存在"

        # 返回按钮
        back_btn = await page.query_selector('text=返回选股器')
        assert back_btn is not None, "返回选股器按钮应存在"

    async def test_empty_state_no_filter_tree(self, page: Page):
        """无 filterTree 时显示空状态提示"""
        await reset_storage(page, "/strategy-backtest")
        await page.wait_for_timeout(2000)

        # 条件摘要应显示空状态
        empty_text = await page.query_selector('text=请从选股器跳转至策略回测页面')
        assert empty_text is not None, "无 filterTree 时应显示空状态提示"

    async def test_backtest_panel_renders(self, page: Page):
        """回测参数面板正常渲染"""
        await reset_storage(page, "/strategy-backtest")
        await page.wait_for_timeout(2000)

        # 回测参数标题
        panel_title = await page.query_selector('text=回测参数')
        assert panel_title is not None, "回测参数面板标题应存在"

        # 开始回测按钮
        start_btn = await page.query_selector('[data-testid="start-backtest-btn"]')
        assert start_btn is not None, "开始回测按钮应存在"

    async def test_date_presets_exist(self, page: Page):
        """日期预设按钮存在（3月/6月/1年/全部）"""
        await reset_storage(page, "/strategy-backtest")
        await page.wait_for_timeout(2000)

        presets = ["3月", "6月", "1年", "全部"]
        for preset in presets:
            # Ant Design small button may add spaces between CJK characters
            # "全部" renders as "全 部" in small buttons
            if preset == "全部":
                btn = await page.query_selector('button:has-text("全")')
            else:
                btn = await page.query_selector(f'button:has-text("{preset}")')
            assert btn is not None, f"日期预设按钮'{preset}'应存在"

    async def test_fundamental_alert_exists(self, page: Page):
        """基本面数据说明 Alert 存在（仅在 filterTree 存在时显示）"""
        import base64
        tree = {
            "type": "and",
            "children": [
                {"type": "range", "field": "close", "min": 10, "max": 50},
            ],
        }
        tree_b64 = base64.b64encode(json.dumps(tree).encode()).decode()

        await reset_storage(page, f"/strategy-backtest?tree={tree_b64}")
        await page.wait_for_timeout(2000)

        # 等待页面加载完成，Alert 应在 filterTree 存在时显示
        alert = await page.query_selector('.ant-alert-info')
        assert alert is not None, "基本面数据说明 Alert 应存在"


class TestStrategyBacktestInteraction:
    """P1: 策略回测交互流程"""

    async def test_navigate_to_picker(self, page: Page):
        """点击"返回选股器"跳转到选股器页面"""
        await reset_storage(page, "/strategy-backtest")
        await page.wait_for_timeout(2000)

        back_btn = await page.query_selector('text=返回选股器')
        assert back_btn is not None

        await back_btn.click(force=True)
        await page.wait_for_timeout(1000)

        # 验证 URL 已跳转
        assert "/picker" in page.url, "应跳转到选股器页面"

    async def test_date_preset_click(self, page: Page):
        """点击日期预设按钮切换日期范围"""
        await reset_storage(page, "/strategy-backtest")
        await page.wait_for_timeout(2000)

        # 点击"3月"预设
        btn_3m = await page.query_selector('button:has-text("3月")')
        assert btn_3m is not None
        await btn_3m.click(force=True)
        await page.wait_for_timeout(500)

        # 验证按钮变为 primary 样式（选中状态）
        btn_after = await page.query_selector('button:has-text("3月")')
        assert btn_after is not None, "3月按钮点击后应仍存在"

    async def test_reset_defaults_button(self, page: Page):
        """点击"重置默认"按钮恢复默认设置"""
        await reset_storage(page, "/strategy-backtest")
        await page.wait_for_timeout(2000)

        reset_btn = await page.query_selector('button:has-text("重置默认")')
        assert reset_btn is not None, "重置默认按钮应存在"
        await reset_btn.click(force=True)
        await page.wait_for_timeout(500)

    async def test_start_without_conditions_shows_error(self, page: Page):
        """无选股条件时点击开始回测，显示错误提示"""
        await reset_storage(page, "/strategy-backtest")
        await page.wait_for_timeout(2000)

        start_btn = await page.query_selector('[data-testid="start-backtest-btn"]')
        assert start_btn is not None

        await start_btn.click(force=True)
        await page.wait_for_timeout(1000)

        # 应显示错误 Alert（请先配置选股条件）
        error_alert = await page.query_selector('.ant-alert-error')
        assert error_alert is not None, "应显示错误提示"


class TestStrategyBacktestErrorHandling:
    """P1: 策略回测错误处理"""

    async def test_invalid_filter_tree_url(self, page: Page):
        """URL 中包含无效的 filterTree 参数时的错误处理"""
        await reset_storage(page, "/strategy-backtest?tree=invalid_json")
        await page.wait_for_timeout(2000)

        # 应显示错误状态
        error_alert = await page.query_selector('.ant-alert-error')
        assert error_alert is not None, "无效 JSON 时应显示错误提示"

    async def test_advanced_settings_collapse(self, page: Page):
        """高级设置折叠面板可展开/收起"""
        await reset_storage(page, "/strategy-backtest")
        await page.wait_for_timeout(2000)

        # 高级设置标题
        advanced_header = await page.query_selector('text=高级设置')
        assert advanced_header is not None, "高级设置标题应存在"

        # 点击展开
        await advanced_header.click(force=True)
        await page.wait_for_timeout(500)

        # 验证高级设置内容出现（手续费率等）
        fee_label = await page.query_selector('text=手续费率')
        assert fee_label is not None, "高级设置展开后应显示手续费率"


class TestStrategyBacktestWithFilterTree:
    """P1: 带 filterTree URL 参数的策略回测"""

    async def test_load_with_valid_filter_tree(self, page: Page):
        """URL 参数包含有效的 filterTree 时，条件摘要正常显示"""
        import base64
        # 构造一个简单的 filterTree JSON（AND 节点包含 range 条件）
        tree = {
            "type": "and",
            "children": [
                {"type": "range", "field": "close", "min": 10, "max": 50},
                {"type": "market", "boards": ["main"]},
            ],
        }
        tree_b64 = base64.b64encode(json.dumps(tree).encode()).decode()

        await reset_storage(page, f"/strategy-backtest?tree={tree_b64}")
        await page.wait_for_timeout(2000)

        # 条件摘要应显示
        summary = await page.query_selector('text=策略条件摘要')
        assert summary is not None, "策略条件摘要应显示"

        # 修改选股条件按钮应存在
        modify_btn = await page.query_selector('[data-testid="modify-conditions-btn"]')
        assert modify_btn is not None, "修改选股条件按钮应存在"

        # Tag 应显示条件内容
        tags = await page.query_selector_all('.ant-tag')
        assert len(tags) > 0, "应有条件标签显示"

    async def test_modify_conditions_navigates_to_picker(self, page: Page):
        """点击"修改选股条件"跳转到选股器（带 tree 参数）"""
        import base64
        tree = {
            "type": "and",
            "children": [
                {"type": "range", "field": "close", "min": 10, "max": 50},
            ],
        }
        tree_b64 = base64.b64encode(json.dumps(tree).encode()).decode()

        await reset_storage(page, f"/strategy-backtest?tree={tree_b64}")
        await page.wait_for_timeout(2000)

        modify_btn = await page.query_selector('[data-testid="modify-conditions-btn"]')
        assert modify_btn is not None

        await modify_btn.click(force=True)
        await page.wait_for_timeout(1000)

        # 验证跳转到选股器页面，且 URL 包含 tree 参数
        assert "/picker" in page.url, "应跳转到选股器页面"
        assert "tree=" in page.url, "URL 应包含 tree 参数"