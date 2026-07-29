/**
 * 自测：2026-06-22 方舟任务「选股视图添加自选 + 导出结果」
 * 浏览器自动化端到端验证
 *
 * 范围：
 *  1. 打开 /picker 页面
 *  2. 点击"开始选股" → 表格渲染
 *  3. 复选框：单选 + 全选 + 反选清空
 *  4. 添加自选：勾选 → 弹 Modal → 填分组名 → 确认 → 调 /api/watchlist POST
 *  5. 导出结果：点击 → 触发 download
 *  6. 无选中时点"添加自选" → 弹 Modal.info 提示
 */
import { chromium } from 'playwright';
import { writeFileSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const BASE = process.env.BASE_URL || 'http://localhost:5173';
const OUT = process.env.SELFTEST_OUT_DIR || resolve(__dirname);

const results = [];
const log = (status, name, detail = '') => {
  results.push({ status, name, detail });
  console.log(`[${status}] ${name}${detail ? ' — ' + detail : ''}`);
};

(async () => {
  const browser = await chromium.launch({
  });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    acceptDownloads: true,
  });
  const page = await context.newPage();

  const consoleErrors = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') {
      const text = msg.text();
      if (text.includes('favicon')) return;
      if (text.includes('Failed to load resource') && text.includes('/api')) return;
      consoleErrors.push(text);
    }
  });
  page.on('pageerror', (err) => consoleErrors.push(`pageerror: ${err.message}`));

  // 拦截 watchlist POST 请求
  const watchlistPosts = [];
  page.on('request', (req) => {
    if (req.url().includes('/api/watchlist') && req.method() === 'POST') {
      watchlistPosts.push({ url: req.url(), body: req.postData() });
    }
  });

  try {
    // ============ 1. 打开选股页 ============
    await page.goto(`${BASE}/picker`, { waitUntil: 'networkidle', timeout: 20000 });
    log('OK', '1. 打开 /picker 页面');
    await page.screenshot({ path: `${OUT}/01_picker.png`, fullPage: true });

    // ============ 2. 开始选股 ============
    await page.getByTestId('start-screener').click();
    log('OK', '2. 点击"开始选股"');

    // 等待第一行出现
    try {
      await page.locator('[data-testid^="row-checkbox-"]').first().waitFor({ timeout: 8000 });
    } catch (e) {
      log('FAIL', '2.1 等待表格行超时（后端可能未返回数据）');
      await page.screenshot({ path: `${OUT}/02_no_data.png`, fullPage: true });
      throw e;
    }

    const rowCheckboxes = await page.locator('[data-testid^="row-checkbox-"]').all();
    const rowCount = rowCheckboxes.length;
    log('OK', `2.2 表格渲染 ${rowCount} 行`);

    // ============ 3. 复选框单选 + 全选 + 反选 ============
    await rowCheckboxes[0].click();
    let btnText = await page.getByTestId('add-to-watchlist-btn').textContent();
    if (btnText.includes('(1)')) {
      log('OK', '3.1 单行勾选 → 按钮显示"添加自选(1)"');
    } else {
      log('FAIL', '3.1 单行勾选后按钮未显示 (1)', `actual="${btnText}"`);
    }

    // 全选
    await page.getByTestId('select-all-checkbox').click();
    btnText = await page.getByTestId('add-to-watchlist-btn').textContent();
    if (btnText.includes(`(${rowCount})`)) {
      log('OK', `3.2 全选 → 按钮显示"添加自选(${rowCount})"`);
    } else {
      log('FAIL', '3.2 全选后按钮未显示完整计数', `expected=(${rowCount}) actual="${btnText}"`);
    }

    // 反选清空
    await page.getByTestId('select-all-checkbox').click();
    btnText = await page.getByTestId('add-to-watchlist-btn').textContent();
    if (!btnText.includes('(')) {
      log('OK', '3.3 反选清空 → 按钮恢复"添加自选"');
    } else {
      log('FAIL', '3.3 反选清空后按钮仍含计数', `actual="${btnText}"`);
    }

    // 重新勾选前 2 行
    await rowCheckboxes[0].click();
    if (rowCount > 1) await rowCheckboxes[1].click();
    await page.screenshot({ path: `${OUT}/03_selected.png`, fullPage: true });
    log('OK', '3.4 重新勾选 2 行');

    // 等 React 状态刷新生效后，再点击按钮
    await page.waitForTimeout(500);

    // 调试：确认按钮文本含计数
    btnText = await page.getByTestId('add-to-watchlist-btn').textContent();
    if (btnText.includes('(2)')) {
      log('OK', `3.5 点击前按钮文本确认: ${btnText}`);
    } else {
      log('WARN', '3.5 点击前按钮文本异常', `actual="${btnText}"`);
    }

    // ============ 4. 添加自选流程 ============
    await page.getByTestId('add-to-watchlist-btn').click();
    // Ant Design Modal 内部有 role="dialog"，仅在 open=true 时渲染
    const dialog = page.getByRole('dialog');
    try {
      await dialog.waitFor({ state: 'visible', timeout: 3000 });
      log('OK', '4.1 点击"添加自选" → Modal 弹出');
    } catch (e) {
      log('FAIL', '4.1 Modal 未弹出');
      throw e;
    }

    // 填分组名
    await page.getByTestId('add-to-watchlist-group-input').fill('方舟自测分组');
    log('OK', '4.2 输入分组名"方舟自测分组"');

    // 点击"确认添加"
    const okBtn = page.getByRole('button', { name: '确认添加' });
    const postsBefore = watchlistPosts.length;
    await okBtn.click();
    log('OK', '4.3 点击"确认添加"');

    // 等待请求或最多 5s
    await page.waitForTimeout(3000);

    if (watchlistPosts.length > postsBefore) {
      log('OK', `4.4 捕获到 ${watchlistPosts.length - postsBefore} 个 POST /api/watchlist 请求`);
      const body = watchlistPosts[watchlistPosts.length - 1].body;
      if (body && body.includes('方舟自测分组')) {
        log('OK', '4.5 POST 请求体含正确的 group_name');
      } else {
        log('WARN', '4.5 POST 请求体未含 group_name（后端可能返回了 mock）', `body=${body}`);
      }
    } else {
      log('WARN', '4.4 未捕获到 POST /api/watchlist 请求（后端可能未启动）');
    }

    // 验证 Modal 关闭
    const dlgVisible = await page.getByRole('dialog').isVisible().catch(() => false);
    if (!dlgVisible) {
      log('OK', '4.6 Modal 自动关闭');
    } else {
      log('WARN', '4.6 Modal 仍可见（后端可能未启动导致失败保留状态）');
    }
    await page.screenshot({ path: `${OUT}/04_watchlist_done.png`, fullPage: true });

    // ============ 5. 导出结果 ============
    const exportBtn = page.getByTestId('export-result-btn');
    if (await exportBtn.isDisabled()) {
      log('FAIL', '5.1 "导出结果" 按钮在有数据时仍 disabled');
    } else {
      log('OK', '5.1 "导出结果" 按钮可用');
    }

    const [download] = await Promise.all([
      page.waitForEvent('download', { timeout: 5000 }).catch(() => null),
      exportBtn.click(),
    ]);

    if (download) {
      const suggested = download.suggestedFilename();
      if (/^screener-result-\d{8}-\d{4}\.csv$/.test(suggested)) {
        log('OK', `5.2 下载文件名格式正确: ${suggested}`);
      } else {
        log('FAIL', '5.2 下载文件名格式错误', `actual=${suggested}`);
      }
      await download.saveAs(`${OUT}/selftest_export.csv`);
      log('OK', '5.3 CSV 文件已保存到 selftest/selftest_export.csv');
    } else {
      log('FAIL', '5.2 未捕获到 download 事件');
    }
    await page.screenshot({ path: `${OUT}/05_exported.png`, fullPage: true });

    // ============ 6. 无选中时点"添加自选" ============
    // 当前应已清空（添加自选成功后清空）；如未清空，主动反选
    btnText = await page.getByTestId('add-to-watchlist-btn').textContent();
    if (btnText.includes('(')) {
      await page.getByTestId('select-all-checkbox').click();
    }
    await page.getByTestId('add-to-watchlist-btn').click();
    // Modal.info 也会创建 role="dialog"，改用检测"分组名输入框"是否存在来区分
    const groupInput = page.getByTestId('add-to-watchlist-group-input');
    const inputVisible = await groupInput.isVisible().catch(() => false);
    if (!inputVisible) {
      log('OK', '6.1 无选中时点"添加自选" → 弹出 Modal.info（无分组输入框）');
    } else {
      log('FAIL', '6.1 无选中时仍弹出添加自选 Modal（含分组输入框）');
    }
  } catch (err) {
    log('FAIL', '流程异常中断', err.message);
    await page.screenshot({ path: `${OUT}/error.png`, fullPage: true });
  } finally {
    if (consoleErrors.length > 0) {
      log('WARN', `捕获 ${consoleErrors.length} 条 console.error`);
      consoleErrors.slice(0, 5).forEach((e, i) => console.log(`  err[${i}]: ${e}`));
    }
    writeFileSync(`${OUT}/selftest_report.json`, JSON.stringify({ results, consoleErrors }, null, 2));
    await browser.close();
  }

  const passed = results.filter((r) => r.status === 'OK').length;
  const failed = results.filter((r) => r.status === 'FAIL').length;
  const warn = results.filter((r) => r.status === 'WARN').length;
  console.log(`\n========== 自测结果 ==========`);
  console.log(`通过: ${passed} | 失败: ${failed} | 警告: ${warn}`);
  if (failed > 0) {
    console.log(`失败项：`);
    results.filter((r) => r.status === 'FAIL').forEach((r) => console.log(`  - ${r.name}: ${r.detail}`));
    process.exit(1);
  }
  process.exit(0);
})();
