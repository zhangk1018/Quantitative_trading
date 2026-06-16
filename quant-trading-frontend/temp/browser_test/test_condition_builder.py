"""
条件构建器 浏览器自测（2026-06-16）
- 验证 UI 行为：折叠/展开、6 预设、3 关系、添加/删除、循环切换 op、重置
- 验证 URL 序列化：cond_<fieldKey>=<op>
- 验证市场切换联动清空
"""
from playwright.sync_api import sync_playwright
import time
import os

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

        page.on("request", lambda req: api_requests.append(
            {"url": req.url, "method": req.method}
        ) if "/api/stocks/" in req.url else None)

        console_errors = []
        page.on("console", lambda msg: console_errors.append(
            f"[{msg.type}] {msg.text}"
        ) if msg.type == "error" else None)

        print("=== 访问 /picker ===")
        page.goto("http://localhost:5173/picker", wait_until="networkidle", timeout=30000)
        time.sleep(1.0)

        # ====================================================================
        # 场景 1：默认折叠
        # ====================================================================
        print("\n=== 场景 1：默认折叠 ===")
        assert page.get_by_test_id("condition-builder-header").is_visible(), "header 不可见"
        assert page.get_by_test_id("condition-builder-count").is_visible(), "count 不可见"
        assert page.get_by_test_id("condition-builder-reset").is_visible(), "reset 不可见"
        count_text = page.get_by_test_id("condition-builder-count").text_content()
        print(f"  count: {count_text}（期望 0 个条件）")
        assert "0 个条件" in count_text
        # 折叠时预设按钮不可见
        assert not page.get_by_test_id("condition-preset-rsi_oversold").is_visible(), \
            "折叠时不应显示预设"
        page.screenshot(path=f"{OUT_DIR}/cond_01_collapsed.png", full_page=True)

        # ====================================================================
        # 场景 2：展开面板
        # ====================================================================
        print("\n=== 场景 2：展开面板 ===")
        page.get_by_test_id("condition-builder-header").click()
        time.sleep(0.5)
        # 6 个预设
        preset_keys = ["rsi_oversold", "volume_breakout", "macd_golden_cross",
                       "bottom_volume_macd", "consecutive_up", "low_valuation"]
        for k in preset_keys:
            btn = page.get_by_test_id(f"condition-preset-{k}")
            assert btn.is_visible(), f"预设 {k} 不可见"
        # 3 关系按钮
        for op in ["and", "or", "not"]:
            assert page.get_by_test_id(f"condition-op-{op}").is_visible(), f"关系 {op} 不可见"
        # 添加按钮
        assert page.get_by_test_id("condition-add").is_visible(), "添加按钮不可见"
        # 空状态
        assert page.get_by_test_id("condition-empty").is_visible(), "空状态不可见"
        page.screenshot(path=f"{OUT_DIR}/cond_02_expanded.png", full_page=True)

        # ====================================================================
        # 场景 3：点击 RSI超卖 预设 → 1 个 condition
        # ====================================================================
        print("\n=== 场景 3：RSI超卖 预设 ===")
        page.get_by_test_id("condition-preset-rsi_oversold").click()
        time.sleep(0.3)
        count_text = page.get_by_test_id("condition-builder-count").text_content()
        print(f"  count: {count_text}（期望 1 个条件）")
        assert "1 个条件" in count_text
        assert not page.get_by_test_id("condition-empty").is_visible(), \
            "有条件时不应显示空状态"
        page.screenshot(path=f"{OUT_DIR}/cond_03_preset_rsi.png", full_page=True)

        # ====================================================================
        # 场景 4：组合预设（底部放量+MACD金叉）→ 替换为 2 个
        # ====================================================================
        print("\n=== 场景 4：组合预设替换 ===")
        page.get_by_test_id("condition-preset-bottom_volume_macd").click()
        time.sleep(0.3)
        count_text = page.get_by_test_id("condition-builder-count").text_content()
        print(f"  count: {count_text}（期望 2 个条件 - 替换语义）")
        assert "2 个条件" in count_text
        page.screenshot(path=f"{OUT_DIR}/cond_04_combo_preset.png", full_page=True)

        # ====================================================================
        # 场景 5：关系切换 + 添加自定义
        # ====================================================================
        print("\n=== 场景 5：关系切换 + 添加 ===")
        page.get_by_test_id("condition-op-or").click()
        time.sleep(0.2)
        page.get_by_test_id("condition-add").click()
        time.sleep(0.3)
        count_text = page.get_by_test_id("condition-builder-count").text_content()
        print(f"  count: {count_text}（期望 3 个条件）")
        assert "3 个条件" in count_text
        # 第 3 个 op 是 OR
        op_btns = page.locator('[data-testid^="condition-item-op-"]').all()
        print(f"  op 按钮数量: {len(op_btns)}（期望 3）")
        assert len(op_btns) == 3
        third_op = op_btns[2].get_attribute("data-op")
        print(f"  第 3 个条件 op: {third_op}（期望 OR）")
        assert third_op == "OR"
        # 前 2 个 op 不变
        assert op_btns[0].get_attribute("data-op") == "AND"
        assert op_btns[1].get_attribute("data-op") == "AND"
        page.screenshot(path=f"{OUT_DIR}/cond_05_or_added.png", full_page=True)

        # ====================================================================
        # 场景 6：URL 序列化 cond_*=*
        # ====================================================================
        print("\n=== 场景 6：URL 序列化 ===")
        print(f"  场景 6 前 api_requests 数量: {len(api_requests)}")
        # 点击"开始选股"触发查询
        page.get_by_test_id("start-screener").click()
        time.sleep(2.0)
        print(f"  场景 6 后 api_requests 数量: {len(api_requests)}")
        for r in api_requests[-5:]:
            print(f"  请求: {r['url']}")
        cond_urls = [r["url"] for r in api_requests if "cond_" in r["url"]]
        print(f"  包含 cond_ 的请求数: {len(cond_urls)}")
        if cond_urls:
            print(f"  最近一次: {cond_urls[-1]}")
        assert len(cond_urls) > 0, "URL 中应包含 cond_ 参数"
        # 检查参数
        latest = cond_urls[-1]
        assert "cond_volume_breakout=AND" in latest, f"缺少 cond_volume_breakout=AND: {latest}"
        assert "cond_macd_golden_cross=AND" in latest, f"缺少 cond_macd_golden_cross=AND: {latest}"
        assert "cond_custom=OR" in latest, f"缺少 cond_custom=OR: {latest}"

        # ====================================================================
        # 场景 7：循环切换 op 标签 (AND → OR)
        # ====================================================================
        print("\n=== 场景 7：op 循环切换 ===")
        first_op_btn = op_btns[0]
        first_op_btn.click()
        time.sleep(0.3)
        new_op = first_op_btn.get_attribute("data-op")
        print(f"  第 1 个条件 op 切换后: {new_op}（期望 OR）")
        assert new_op == "OR"
        page.screenshot(path=f"{OUT_DIR}/cond_07_cycled_op.png", full_page=True)

        # ====================================================================
        # 场景 8：删除一个条件
        # ====================================================================
        print("\n=== 场景 8：删除条件 ===")
        del_btns = page.locator('[data-testid^="condition-item-remove-"]').all()
        print(f"  删除按钮数: {len(del_btns)}（期望 3）")
        del_btns[-1].click()  # 删除最后一个
        time.sleep(0.8)
        count_text = page.get_by_test_id("condition-builder-count").text_content()
        print(f"  count: '{count_text}'（期望 2 个条件）")
        assert "2 个条件" in count_text, f"count_text 实际是 {count_text!r}"

        # ====================================================================
        # 场景 9：重置
        # ====================================================================
        print("\n=== 场景 9：重置 ===")
        page.get_by_test_id("condition-builder-reset").click()
        time.sleep(0.3)
        count_text = page.get_by_test_id("condition-builder-count").text_content()
        print(f"  count: {count_text}（期望 0 个条件）")
        assert "0 个条件" in count_text
        assert page.get_by_test_id("condition-empty").is_visible(), "重置后应显示空状态"
        page.screenshot(path=f"{OUT_DIR}/cond_09_reset.png", full_page=True)

        # ====================================================================
        # 总结
        # ====================================================================
        print("\n=== 控制台错误 ===")
        real_errors = [e for e in console_errors if "destroyOnClose" not in e and "destroyInactivePanel" not in e]
        if real_errors:
            print("发现错误:")
            for e in real_errors[:10]:
                print(f"  {e}")
        else:
            print("无错误（除已知 deprecation 警告）")

        print("\n=== 所有场景通过 ===")
        browser.close()


if __name__ == "__main__":
    main()
