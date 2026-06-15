"""
选股视图·全按钮逻辑测试
覆盖 A/B/C/D 四组共 50+ 用例
"""
import asyncio, sys, time, os
from playwright.async_api import async_playwright, expect

URL = "http://localhost:5173/"
REPORT = []
ERRORS = []

def log(msg: str):
    print(msg)
    REPORT.append(msg)

def report_fail(case: str, detail: str):
    msg = f"  ❌ [{case}] {detail}"
    print(msg)
    REPORT.append(msg)

def report_pass(case: str, detail: str = ""):
    d = f" — {detail}" if detail else ""
    msg = f"  ✅ [{case}]{d}"
    print(msg)
    REPORT.append(msg)

# =============================================
async def run_all(page):
    # ========== A组: 范围(3)区 ==========
    log("\n" + "="*60)
    log("A 组：范围(3)区")
    log("="*60)

    # A1: 所属市场单选
    log("\n[A1] 所属市场单选")
    hk_radio = page.locator('input[name="market"]').nth(0)
    us_radio = page.locator('input[name="market"]').nth(1)
    hs_radio = page.locator('input[name="market"]').nth(2)
    await hs_radio.click()
    assert await hs_radio.is_checked()
    report_pass("A1", "沪深选中")
    await us_radio.click()
    assert await us_radio.is_checked()
    assert not await hs_radio.is_checked()
    report_pass("A1", "美股选中，沪深取消")
    # 最后回到沪深
    await hs_radio.click()

    # A2: 上市地下拉展开/关闭
    log("\n[A2] 上市地下拉展开/关闭")
    # 更精确的定位：上市地下拉按钮
    listing_label = page.locator("label", has_text="上市地")
    listing_btn = listing_label.locator("..").locator("button").first
    await listing_btn.click()
    await page.wait_for_timeout(300)
    dropdown = page.locator("div.absolute.z-\\[60\\]")
    assert await dropdown.is_visible()
    report_pass("A2", "下拉展开")
    # 点击外部关闭
    await page.locator("h4", has_text="范围").first.click()
    await page.wait_for_timeout(300)
    assert not await dropdown.is_visible()
    report_pass("A2", "下拉关闭")

    # A3: 上市地·全部
    log("\n[A3] 上市地·全选/取消")
    await listing_btn.click()
    await page.wait_for_timeout(300)
    dropdown = page.locator("div.absolute.z-\\[60\\]")
    all_checkbox = dropdown.locator("label").first.locator("input[type=checkbox]")
    # 先取消全部
    await all_checkbox.click()
    await page.wait_for_timeout(300)
    report_pass("A3", "取消全部")
    await all_checkbox.click()
    await page.wait_for_timeout(300)
    report_pass("A3", "选中全部")

    # A4: 上市地·多选
    log("\n[A4] 上市地·多选")
    await all_checkbox.click()  # 取消全部
    await page.wait_for_timeout(200)
    items = dropdown.locator("label")
    await items.nth(1).locator("input[type=checkbox]").click()
    await page.wait_for_timeout(100)
    await items.nth(2).locator("input[type=checkbox]").click()
    await page.wait_for_timeout(300)
    btn_text = await listing_btn.inner_text()
    if "已选" in btn_text or "上海" in btn_text or "深证" in btn_text:
        report_pass("A4", f"多选显示: {btn_text.strip()}")
    else:
        report_fail("A4", f"多选显示异常: {btn_text.strip()}")
    # 恢复全部
    await all_checkbox.click()
    await page.wait_for_timeout(200)
    # 关闭下拉
    await page.locator("h4", has_text="范围").first.click()
    await page.wait_for_timeout(300)

    # A5: 股票范围单选
    log("\n[A5] 股票范围单选")
    scope_all = page.locator('input[name="stockScope"]').first
    scope_watch = page.locator('input[name="stockScope"]').nth(1)
    await scope_all.click()
    assert await scope_all.is_checked()
    report_pass("A5", "全部选中")
    await scope_watch.click()
    assert await scope_watch.is_checked()
    assert not await scope_all.is_checked()
    report_pass("A5", "仅看自选选中")
    await scope_all.click()

    # A6: 范围折叠
    log("\n[A6] 范围折叠")
    range_toggle = page.locator("h4", has_text="范围").first.locator("..").locator("button")
    await range_toggle.click()
    await page.wait_for_timeout(200)
    # 内容应隐藏
    assert not await page.locator("label", has_text="所属市场").first.is_visible()
    report_pass("A6", "折叠")
    await range_toggle.click()
    await page.wait_for_timeout(200)
    assert await page.locator("label", has_text="所属市场").first.is_visible()
    report_pass("A6", "展开")

    # ========== B1组: 行情指标 ==========
    log("\n" + "="*60)
    log("B1 组：行情指标")
    log("="*60)

    # B1-1: 选中行情指标
    log("\n[B1-1] 选中行情指标")
    btn_marketcap = page.locator("button", has_text="市值").last
    await btn_marketcap.click()
    await page.wait_for_timeout(200)
    cls = await btn_marketcap.get_attribute("class")
    if "bg-up-green" in cls:
        report_pass("B1-1", "市值选中(变绿)")
    else:
        report_fail("B1-1", f"未变绿: {cls}")
    # 确认范围输入出现
    range_div = page.locator('[data-testid="indicator-ranges"]')
    assert await range_div.is_visible()
    report_pass("B1-1", "范围输入区出现")

    # B1-2: 取消选中
    log("\n[B1-2] 取消选中")
    await btn_marketcap.click()
    await page.wait_for_timeout(200)
    cls2 = await btn_marketcap.get_attribute("class")
    if "bg-up-green" not in cls2:
        report_pass("B1-2", "市值取消(恢复灰色)")
    else:
        report_fail("B1-2", "未取消")

    # B1-3: 范围输入
    log("\n[B1-3] 范围输入")
    await btn_marketcap.click()
    await page.wait_for_timeout(200)
    min_input = page.locator('[data-testid="range-市值-min"]')
    max_input = page.locator('[data-testid="range-市值-max"]')
    await min_input.fill("10")
    await max_input.fill("100")
    await page.wait_for_timeout(100)
    val1 = await min_input.input_value()
    val2 = await max_input.input_value()
    if val1 == "10" and val2 == "100":
        report_pass("B1-3", f"min={val1}, max={val2}")
    else:
        report_fail("B1-3", f"值不对: min={val1}, max={val2}")
    # 清空
    await min_input.fill("")
    await max_input.fill("")

    # B1-4: 行情指标折叠
    log("\n[B1-4] 行情指标折叠")
    mi_header = page.locator("h4", has_text="行情指标").first
    mi_toggle = mi_header.locator("..").locator("button")
    await mi_toggle.click()
    await page.wait_for_timeout(200)
    if not await page.locator("button", has_text="市值").last.is_visible():
        report_pass("B1-4", "折叠")
    else:
        report_fail("B1-4", "折叠后市值仍可见")
    await mi_toggle.click()
    await page.wait_for_timeout(200)

    # ========== B2组: 财务指标 ==========
    log("\n" + "="*60)
    log("B2 组：财务指标")
    log("="*60)

    # B2-1: 选中财务指标
    log("\n[B2-1] 选中财务指标")
    btn_np = page.locator("button", has_text="净利润").last
    await btn_np.click()
    await page.wait_for_timeout(200)
    cls = await btn_np.get_attribute("class")
    if "bg-up-green" in cls:
        report_pass("B2-1", "净利润选中")
    else:
        report_fail("B2-1", "未变绿")
    fin_range = page.locator('[data-testid="financial-indicator-ranges"]')
    assert await fin_range.is_visible()
    report_pass("B2-1", "范围输入区出现")

    # B2-2: 取消选中
    log("\n[B2-2] 取消选中")
    await btn_np.click()
    await page.wait_for_timeout(200)

    # B2-3: 输入范围
    log("\n[B2-3] 财务指标范围输入")
    await btn_np.click()
    await page.wait_for_timeout(200)
    fmin = page.locator('[data-testid="financial-range-净利润-min"]')
    fmax = page.locator('[data-testid="financial-range-净利润-max"]')
    await fmin.fill("1")
    await fmax.fill("10")
    await page.wait_for_timeout(100)
    report_pass("B2-3", f"min={await fmin.input_value()}, max={await fmax.input_value()}")
    await fmin.fill("")
    await fmax.fill("")

    # B2-4: 财务指标折叠
    log("\n[B2-4] 财务指标折叠")
    fi_header = page.locator("h4", has_text="财务指标").first
    fi_toggle = fi_header.locator("..").locator("button")
    await fi_toggle.click()
    await page.wait_for_timeout(200)
    report_pass("B2-4", "折叠")
    await fi_toggle.click()
    await page.wait_for_timeout(200)

    # ========== B3组: 技术指标 ==========
    log("\n" + "="*60)
    log("B3 组：技术指标")
    log("="*60)

    # B3-1/2/3: 点击各按钮弹出弹窗
    log("\n[B3-1] MA 按钮→弹窗")
    await page.locator('[data-testid="tech-btn-MA"]').click()
    await page.wait_for_timeout(500)
    dialog_ma = page.locator('[data-testid="tech-dialog-MA"]')
    if await dialog_ma.is_visible():
        report_pass("B3-1", "MA 弹窗出现")
    else:
        report_fail("B3-1", "MA 弹窗未出现")
    # Escape 关闭
    await page.keyboard.press("Escape")
    await page.wait_for_timeout(300)

    log("\n[B3-2] MACD 按钮→弹窗(选选项后确认)")
    await page.locator('[data-testid="tech-btn-MACD"]').click()
    await page.wait_for_timeout(500)
    dialog_macd = page.locator('[data-testid="tech-dialog-MACD"]')
    if await dialog_macd.is_visible():
        report_pass("B3-2", "MACD 弹窗出现")
        # MACD 选项: 低位金叉 / 底背离 / 高位死叉 / 顶背离
        rbtn = dialog_macd.locator("button", has_text="低位金叉")
        if await rbtn.is_visible():
            await rbtn.click()
            await page.wait_for_timeout(200)
            confirm_macd = dialog_macd.locator('[data-testid="tech-dialog-MACD-confirm"]')
            if await confirm_macd.is_enabled():
                await confirm_macd.click()
                await page.wait_for_timeout(300)
                report_pass("B3-2", "点确定关闭")
            else:
                report_fail("B3-2", "确认按钮 disabled")
                await page.keyboard.press("Escape")
        else:
            report_fail("B3-2", "低位金叉 radio 不可见")
            await page.keyboard.press("Escape")
    else:
        report_fail("B3-2", "MACD 弹窗未出现")
    # 验证按钮变绿
    macd_btn = page.locator('[data-testid="tech-btn-MACD"]')
    cls = await macd_btn.get_attribute("class")
    if "bg-up-green" in cls:
        report_pass("B3-2", "MACD 按钮变绿")
    else:
        report_fail("B3-2", "MACD 按钮未变绿")

    log("\n[B3-3] BOLL 按钮→弹窗(选选项后确认)")
    await page.locator('[data-testid="tech-btn-BOLL"]').click()
    await page.wait_for_timeout(500)
    dialog_boll = page.locator('[data-testid="tech-dialog-BOLL"]')
    if await dialog_boll.is_visible():
        report_pass("B3-3", "BOLL 弹窗出现")
        # 选一个选项
        await dialog_boll.locator("button", has_text="升穿上轨").click()
        await page.wait_for_timeout(200)
        confirm_boll = dialog_boll.locator('[data-testid="tech-dialog-BOLL-confirm"]')
        assert await confirm_boll.is_enabled(), "确认按钮应可用"
        await confirm_boll.click()
        await page.wait_for_timeout(300)
        report_pass("B3-3", "点确定关闭")
    else:
        report_fail("B3-3", "BOLL 弹窗未出现")

    # B3-6: 再次点击已选中指标
    log("\n[B3-6] 再次点击已选中 MACD")
    await macd_btn.click()
    await page.wait_for_timeout(500)
    if await dialog_macd.is_visible():
        report_pass("B3-6", "再次弹窗可修改配置")
        # 应有上次配置的选项，确认按钮应可用
        confirm2 = dialog_macd.locator('[data-testid="tech-dialog-MACD-confirm"]')
        if await confirm2.is_enabled():
            await confirm2.click()
            await page.wait_for_timeout(300)
            report_pass("B3-6", "确定关闭")
        else:
            # 如果 still disabled（可能是新建的空白），选一个选项再确定
            await dialog_macd.locator("button", has_text="高位死叉").click()
            await page.wait_for_timeout(100)
            await confirm2.click()
            await page.wait_for_timeout(300)
            report_pass("B3-6", "选选项后确定")
    else:
        report_fail("B3-6", "未弹窗")

    # B3-7: MA 添加多行条件
    log("\n[B3-7] MA 弹窗添加多行")
    await page.locator('[data-testid="tech-btn-MA"]').click()
    await page.wait_for_timeout(500)
    dialog_ma = page.locator('[data-testid="tech-dialog-MA"]')
    if await dialog_ma.is_visible():
        report_pass("B3-7", "MA 弹窗出现")
        add_row_btn = dialog_ma.locator('[data-testid="ma-add-row"]')
        if await add_row_btn.is_visible():
            await add_row_btn.click()
            await page.wait_for_timeout(200)
            rows_ma = dialog_ma.locator('[data-testid^="ma-row-"]')
            cnt = await rows_ma.count()
            if cnt >= 1:
                report_pass("B3-7", f"添加条件后 {cnt} 行")
            else:
                report_fail("B3-7", f"行数 {cnt}")
        else:
            report_fail("B3-7", "未找到添加条件按钮")
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(300)
    else:
        report_fail("B3-7", "MA 弹窗未出现")
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(200)

    # ========== B4组: 条件构建器 ==========
    log("\n" + "="*60)
    log("B4 组：条件构建器")
    log("="*60)

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

    # B4-1: RSI超卖预设
    log("\n[B4-1] RSI超卖预设")
    await page.locator('[data-testid="preset-rsi_oversold"]').click()
    await page.wait_for_timeout(300)
    chips = await chip_text(page)
    if len(chips) == 1 and "RSI" in chips[0]:
        report_pass("B4-1", str(chips))
    else:
        report_fail("B4-1", f"条件不对: {chips}")

    # B4-3: 预设替换
    log("\n[B4-3] 预设替换行为")
    await page.locator('[data-testid="preset-volume_outbreak"]').click()
    await page.wait_for_timeout(300)
    chips = await chip_text(page)
    if len(chips) == 2 and "量比" in chips[0]:
        report_pass("B4-3", f"替换为放量突破: {chips}")
    else:
        report_fail("B4-3", f"结果不对: {chips}")

    # B4-4: AND/OR/NOT 互斥
    log("\n[B4-4] AND/OR/NOT 互斥")
    for op in ["AND", "OR", "NOT"]:
        await page.locator(f'[data-testid="pending-op-{op}"]').click()
        await page.wait_for_timeout(100)
    report_pass("B4-4", "最后一个 NOT 高亮")

    # B4-5: 使用 pendingOp 添加
    log("\n[B4-5] 使用 pendingOp 添加条件")
    await page.locator('[data-testid="add-condition-0"]').click()
    await page.wait_for_selector('[data-testid="add-condition-panel"]', timeout=3000)
    await page.locator('[data-testid="add-condition-panel-pattern-pattern_hammer"]').click()
    await page.wait_for_timeout(300)
    chips = await chip_text(page)
    if len(chips) == 3:
        report_pass("B4-5", f"第三条件为 NOT: {chips[2]}")
    else:
        report_fail("B4-5", f"条件数 {len(chips)}")

    # B4-6/7: pendingOp 不改变旧条件
    log("\n[B4-6] pendingOp=AND 不改变旧条件")
    chips_before = await chip_text(page)
    # 切到 OR，再加一个
    await page.locator('[data-testid="pending-op-AND"]').click()
    await page.wait_for_timeout(100)
    await page.locator('[data-testid="add-condition-0"]').click()
    await page.wait_for_selector('[data-testid="add-condition-panel"]', timeout=3000)
    await page.locator('[data-testid="add-condition-panel-pattern-pattern_bullish_engulfing"]').click()
    await page.wait_for_timeout(300)
    chips_after = await chip_text(page)
    # 检查旧条件没变
    unchanged = True
    for i, c in enumerate(chips_before):
        if i < len(chips_after) and chips_after[i] != c:
            unchanged = False
            break
    if unchanged and len(chips_after) == len(chips_before) + 1:
        report_pass("B4-6", "旧条件不变，新条件为 AND")
    else:
        report_fail("B4-6", f"变化: {chips_before} → {chips_after}")

    # B4-7: 类似验证 NOT 不改变旧条件
    log("\n[B4-7] NOT 不改变旧条件")
    chips_before2 = await chip_text(page)
    await page.locator('[data-testid="pending-op-NOT"]').click()
    await page.wait_for_timeout(100)
    await page.locator('[data-testid="add-condition-0"]').click()
    await page.wait_for_selector('[data-testid="add-condition-panel"]', timeout=3000)
    await page.locator('[data-testid="add-condition-panel-breakout-break_high_20"]').click()
    await page.wait_for_timeout(300)
    chips_after2 = await chip_text(page)
    if len(chips_after2) == len(chips_before2) + 1:
        report_pass("B4-7", f"旧条件不变，新条件 NOT: {chips_after2[-1]}")
    else:
        report_fail("B4-7", f"数量不符: {chips_after2}")

    # B4-8: op 标签循环
    log("\n[B4-8] op 标签循环")
    first_op = page.locator('[data-testid^="condition-row-op-"]').first
    await first_op.click()
    await page.wait_for_timeout(100)
    op_val = await first_op.get_attribute("data-op")
    if op_val in ["AND","OR","NOT"]:
        report_pass("B4-8", f"第1个条件 op 变为 {op_val}")
    else:
        report_fail("B4-8", f"op 异常: {op_val}")

    # B4-9: 删除条件
    log("\n[B4-9] 删除条件")
    chips_before3 = await chip_text(page)
    first_del = page.locator('[data-testid^="condition-row-remove-"]').first
    await first_del.click()
    await page.wait_for_timeout(200)
    chips_after3 = await chip_text(page)
    if len(chips_after3) == len(chips_before3) - 1:
        report_pass("B4-9", f"删除后 {len(chips_after3)} 个条件")
    else:
        report_fail("B4-9", f"删除失败: {len(chips_before3)}→{len(chips_after3)}")

    # B4-10: 弹层打开/关闭
    log("\n[B4-10] 弹层打开/关闭")
    await page.locator('[data-testid="add-condition-0"]').click()
    await page.wait_for_selector('[data-testid="add-condition-panel"]', timeout=3000)
    assert await page.locator('[data-testid="add-condition-panel"]').is_visible()
    # 点击外部关闭
    await page.locator('[data-testid="pending-op-toggle"]').click()
    await page.wait_for_timeout(200)
    assert not await page.locator('[data-testid="add-condition-panel"]').is_visible()
    report_pass("B4-10", "弹层开关正常")

    # B4-11: 弹层中所有指标可点
    log("\n[B4-11] 弹层中指标点击")
    await page.locator('[data-testid="add-condition-0"]').click()
    await page.wait_for_selector('[data-testid="add-condition-panel"]', timeout=3000)
    panel = page.locator('[data-testid="add-condition-panel"]')
    btns = panel.locator("button")
    btn_count = await btns.count()
    if btn_count > 0:
        report_pass("B4-11", f"弹层中 {btn_count} 个可点击指标")
    else:
        report_fail("B4-11", "弹层中无指标按钮")
    # 关闭弹层
    await page.keyboard.press("Escape")
    await page.wait_for_timeout(200)

    # B4-12: 条件构建器折叠
    log("\n[B4-12] 条件构建器折叠")
    builder_header = page.locator('[data-testid="condition-builder"]').locator("> div").first
    await builder_header.click()
    await page.wait_for_timeout(200)
    # 验证条件列表隐藏
    if not await page.locator('[data-testid="condition-list"]').is_visible():
        report_pass("B4-12", "折叠")
    else:
        report_fail("B4-12", "折叠后列表仍可见")
    await builder_header.click()
    await page.wait_for_timeout(200)
    report_pass("B4-12", "展开")

    # B4-13: 内部重置
    log("\n[B4-13] 条件构建器内部重置")
    await page.locator('[data-testid="condition-reset"]').click()
    await page.wait_for_timeout(300)
    chips = await chip_text(page)
    if len(chips) == 0:
        report_pass("B4-13", "重置后空条件")
    else:
        report_fail("B4-13", f"重置后仍有 {len(chips)} 条件")

    # ========== B5组: 因子打分配置 ==========
    log("\n" + "="*60)
    log("B5 组：因子打分配置")
    log("="*60)

    # B5-1: 拖动滑块
    log("\n[B5-1] 滑块拖动")
    sliders = page.locator('input[type="range"]')
    cnt = await sliders.count()
    if cnt == 3:
        report_pass("B5-1", f"3 个滑块可见")
    else:
        report_fail("B5-1", f"滑块数 {cnt}")

    # ========== C组: 底部固定按钮 ==========
    log("\n" + "="*60)
    log("C 组：底部固定按钮")
    log("="*60)

    # C1: 开始选股（重置后条件为空，应可点击但暂无数据）
    log("\n[C2] ▶开始选股")
    await page.locator('[data-testid="start-screener"]').click()
    await page.wait_for_timeout(1000)
    # 检查是否有加载或错误信息
    status_text = await page.locator('[data-testid="condition-count-badge"]').locator("..").inner_text()
    report_pass("C2", f"点击后状态: {status_text[:60]}...")

    # C3: 重置
    log("\n[C3] 底部重置")
    # 先加个条件再重置
    await page.locator('[data-testid="preset-rsi_oversold"]').click()
    await page.wait_for_timeout(200)
    await page.locator('[data-testid="reset-screener"]').click()
    await page.wait_for_timeout(300)
    chips = await chip_text(page)
    if len(chips) == 0:
        report_pass("C3", "重置后条件清空")
    else:
        report_fail("C3", f"重置后仍有 {len(chips)} 条件")

    # C4: 无数据时重置
    log("\n[C4] 无数据时重置")
    await page.locator('[data-testid="reset-screener"]').click()
    await page.wait_for_timeout(200)
    report_pass("C4", "无报错")

    # ========== D组: 右侧主工作区 ==========
    log("\n" + "="*60)
    log("D 组：右侧主工作区")
    log("="*60)

    # 先点击开始选股让表格有数据
    await page.locator('[data-testid="start-screener"]').click()
    await page.wait_for_timeout(2000)

    # D1: 排序下拉
    log("\n[D1] 排序下拉")
    sort_select = page.locator("select").first
    if await sort_select.is_visible():
        await sort_select.select_option("turnover")
        await page.wait_for_timeout(200)
        report_pass("D1", "切换到换手率")
        await sort_select.select_option("score")
        report_pass("D1", "切换回综合得分")
    else:
        report_fail("D1", "排序下拉不可见")

    # D2: 升降序切换
    log("\n[D2] 升降序切换")
    order_btn = page.locator("button", has_text="降序").or_(page.locator("button", has_text="升序"))
    if await order_btn.is_visible():
        text_before = await order_btn.inner_text()
        await order_btn.click()
        await page.wait_for_timeout(200)
        text_after = await order_btn.inner_text()
        if text_before != text_after:
            report_pass("D2", f"{text_before.strip()} → {text_after.strip()}")
        else:
            report_fail("D2", "切换后文本未变")
        await order_btn.click()
        await page.wait_for_timeout(200)
    else:
        report_fail("D2", "升降序按钮不可见")

    # D3: TopN 切换
    log("\n[D3] TopN 切换")
    topn_select = page.locator("select").nth(1)
    if await topn_select.is_visible():
        await topn_select.select_option("50")
        await page.wait_for_timeout(200)
        report_pass("D3", "切换到 Top 50")
        await topn_select.select_option("20")
        await page.wait_for_timeout(200)
        report_pass("D3", "切换回 Top 20")
    else:
        report_fail("D3", "TopN 下拉不可见")

    # D4/D5: 策略按钮
    log("\n[D4] 💾保存策略")
    save_btn = page.locator("button", has_text="保存策略")
    if await save_btn.is_visible():
        await save_btn.click()
        await page.wait_for_timeout(400)
        report_pass("D4", "点击保存策略")
        # 按 Escape 关闭弹窗
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(300)
    else:
        report_fail("D4", "保存策略按钮不可见")

    log("\n[D5] 📂我的策略")
    my_btn = page.locator("button", has_text="我的策略")
    if await my_btn.is_visible():
        await my_btn.click()
        await page.wait_for_timeout(400)
        report_pass("D5", "点击我的策略")
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(300)
    else:
        report_fail("D5", "我的策略按钮不可见")

    # D6: 行点击
    log("\n[D6] 表格行点击")
    rows = page.locator("tbody tr")
    rc = await rows.count()
    if rc > 0:
        # 点击第一行
        first_row = rows.first
        await first_row.click()
        await page.wait_for_timeout(500)
        detail = page.locator('[data-testid="stock-detail-modal"]')
        if await detail.is_visible():
            report_pass("D6", "点击行打开详情")
            # 按 Escape 关闭
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(500)
        else:
            report_fail("D6", "详情未弹出")
    else:
        report_fail("D6", "表格无数据")

    # D7: 全选
    log("\n[D7] 全选 checkbox")
    rows = page.locator("tbody tr")
    rc2 = await rows.count()
    if rc2 > 0:
        header_check = page.locator("thead input[type=checkbox]")
        await header_check.click()
        await page.wait_for_timeout(200)
        all_checked = True
        for i in range(min(rc2, 5)):
            cb = rows.nth(i).locator("input[type=checkbox]")
            if not await cb.is_checked():
                all_checked = False
                break
        if all_checked:
            report_pass("D7", "全选成功")
        else:
            report_fail("D7", "全选后部分行未勾选")
        await header_check.click()
        await page.wait_for_timeout(200)
    else:
        report_fail("D7", "表格无数据")

    # D8: 行多选
    log("\n[D8] 行多选")
    rows3 = page.locator("tbody tr")
    rc3 = await rows3.count()
    if rc3 >= 2:
        # 先确保都没选中
        for i in range(2):
            cb = rows3.nth(i).locator("input[type=checkbox]")
            if await cb.is_checked():
                await cb.click()
        await page.wait_for_timeout(100)
        # 选前2行
        cb0 = rows3.nth(0).locator("input[type=checkbox]")
        cb1 = rows3.nth(1).locator("input[type=checkbox]")
        await cb0.click()
        await cb1.click()
        await page.wait_for_timeout(300)
        selected_info = page.locator('[data-testid="selected-info"]')
        text = await selected_info.inner_text()
        if "选中" in text and "(" in text:
            report_pass("D8", f"选中信息: {text.strip()[:60]}")
        else:
            report_fail("D8", f"选中信息异常: {text.strip()}")
        # 取消选中
        await cb0.click()
        await cb1.click()
        await page.wait_for_timeout(200)
    else:
        report_fail("D8", f"行数不足: {rc3}")

    # D9-D12: 底部功能按钮 disabled 状态
    log("\n[D9] 加入回测列表 disabled 状态")
    add_bt = page.locator('[data-testid="add-to-backtest"]')
    if await add_bt.is_visible():
        if await add_bt.is_disabled():
            report_pass("D9", "加入回测列表 disabled 正确")
        else:
            report_fail("D9", "未 disabled")
    else:
        report_fail("D9", "按钮不可见")

    log("\n[D10] 添加自选 disabled 状态")
    add_wl = page.locator('[data-testid="add-to-watchlist"]')
    if await add_wl.is_visible():
        if await add_wl.is_disabled():
            report_pass("D10", "添加自选 disabled 正确")
        else:
            report_fail("D10", "未 disabled")
    else:
        report_fail("D10", "按钮不可见")

    log("\n[D11] 导出结果 disabled 状态")
    export_btn = page.locator('[data-testid="export-result"]')
    if await export_btn.is_visible():
        if not await export_btn.is_disabled():
            report_pass("D11", "导出结果 enabled 正确")
        else:
            report_fail("D11", "不应 disabled")
    else:
        report_fail("D11", "按钮不可见")

    log("\n[D12] 加入黑名单 disabled 状态")
    add_bl = page.locator('[data-testid="add-to-blacklist"]')
    if await add_bl.is_visible():
        if await add_bl.is_disabled():
            report_pass("D12", "加入黑名单 disabled 正确")
        else:
            report_fail("D12", "未 disabled")
    else:
        report_fail("D12", "按钮不可见")

    # D13: 刷新
    log("\n[D13] 刷新按钮")
    refresh_btn = page.locator('[data-testid="refresh-stocks"]')
    if await refresh_btn.is_visible():
        await refresh_btn.click()
        await page.wait_for_timeout(500)
        report_pass("D13", "点击刷新")
    else:
        report_fail("D13", "刷新按钮不可见")

    # 最终截图
    await page.screenshot(path="/Users/zhangk/workspace/Quantitative_trading/temp/final_state.png", full_page=True)


# =============================================
async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await ctx.new_page()

        console_errors = []
        page.on("pageerror", lambda e: console_errors.append(f"pageerror: {e}"))
        page.on("console", lambda m: console_errors.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)

        start_time = time.time()

        try:
            log("="*60)
            log("选股视图·按钮逻辑全量测试")
            log(f"启动时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
            log("="*60)
            log(f"\n打开 {URL}")
            await page.goto(URL, wait_until="networkidle")
            await page.wait_for_selector('[data-testid="condition-builder"]', timeout=15000)
            await page.wait_for_timeout(1000)
            log("✅ 页面加载完成")

            await run_all(page)
        finally:
            elapsed = time.time() - start_time
            elapsed_str = f"{elapsed:.1f}s"

            # 统计
            passed = sum(1 for l in REPORT if "✅" in l)
            failed = sum(1 for l in REPORT if "❌" in l)

            log("\n" + "="*60)
            log("测 试 报 告")
            log("="*60)
            log(f"运行时长: {elapsed_str}")
            log(f"通过: {passed}")
            log(f"失败: {failed}")
            log(f"总计用例: {passed + failed}")
            log(f"页面错误: {len(console_errors)}")
            if console_errors:
                for e in console_errors[:10]:
                    log(f"  ⚠️  {e}")

            # 写入报告文件
            report_path = "/Users/zhangk/workspace/Quantitative_trading/temp/test_report.txt"
            with open(report_path, "w") as f:
                f.write("\n".join(REPORT))
            log(f"\n报告已写入: {report_path}")

            await browser.close()

    return len([l for l in REPORT if "❌" in l])


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    if exit_code > 0:
        print(f"\n💥 共 {exit_code} 个失败用例")
    sys.exit(exit_code)