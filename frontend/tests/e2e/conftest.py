"""E2E 测试全局配置：失败截图"""

import pytest
import pytest_asyncio
from pathlib import Path

ARTIFACTS_DIR = Path(__file__).resolve().parent.parent.parent / "test-artifacts"


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """将测试结果报告挂载到 item 上，供 fixture 读取"""
    outcome = yield
    report = outcome.get_result()
    setattr(item, "rep_" + report.when, report)


@pytest_asyncio.fixture(autouse=True)
async def _screenshot_on_failure(request, page):
    """测试失败时自动截图，保存至 test-artifacts/ 目录"""
    yield
    report = getattr(request.node, "rep_call", None)
    if report and report.failed:
        try:
            ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
            test_name = request.node.nodeid.replace("::", "_").replace("/", "_")
            filepath = ARTIFACTS_DIR / f"{test_name}.png"
            await page.screenshot(path=str(filepath), full_page=True, timeout=3000)
        except Exception:
            pass  # 截图失败不应影响测试结果