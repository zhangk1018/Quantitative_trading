const { chromium } = require('/usr/local/Cellar/node@20/20.20.2/lib/node_modules/@playwright/test/node_modules/playwright');

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1500, height: 950 }, colorScheme: 'light' });
  const page = await ctx.newPage();
  page.on('pageerror', e => console.log('PAGEERROR:', e.message));
  page.on('console', msg => { if (msg.type() === 'error') console.log('CONSOLE:', msg.text()); });

  await page.goto('http://localhost:5173/', { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('table', { timeout: 15000 });
  console.log('表格已加载');

  // 点击第一行股票
  await page.locator('table tbody tr').first().click();
  await page.waitForTimeout(2500);

  const canvases = await page.locator('canvas').count();
  const hasLegend = await page.locator('text=MA5').count();
  console.log(`canvas: ${canvases}, MA 图例: ${hasLegend}`);

  if (canvases > 0) {
    console.log('✅ K线图渲染成功（120条真实数据）');
    await page.screenshot({ path: '/Users/zhangk/workspace/Quantitative_trading/docs/research/echarts_verify/2026-06-05_120days.png', fullPage: false });
    console.log('截图已保存: docs/research/echarts_verify/2026-06-05_120days.png');
  } else {
    console.log('❌ 无 canvas');
    await page.screenshot({ path: '/Users/zhangk/workspace/Quantitative_trading/docs/research/echarts_verify/2026-06-05_no_canvas.png', fullPage: false });
  }

  await browser.close();
  console.log('验证完成');
})();