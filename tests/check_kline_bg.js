const { chromium } = require('/usr/local/Cellar/node@20/20.20.2/lib/node_modules/@playwright/test/node_modules/playwright');

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1500, height: 950 }, colorScheme: 'light' });
  const page = await ctx.newPage();

  await page.goto('http://localhost:5173/', { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('table', { timeout: 15000 });
  await page.locator('table tbody tr').first().click();
  await page.waitForTimeout(2500);

  // 检查 KLineChart 组件的背景色
  const klineBg = await page.evaluate(() => {
    // 找到 KLineChart 的外层容器
    const charts = document.querySelectorAll('[style*="backgroundColor"]');
    const results = [];
    charts.forEach(el => {
      const style = window.getComputedStyle(el);
      results.push({
        tagName: el.tagName,
        className: el.className,
        bgColor: style.backgroundColor,
        y: el.getBoundingClientRect().top
      });
    });
    return results;
  });
  console.log('KLineChart 相关元素背景色:');
  klineBg.forEach(r => {
    if (r.y < 100) {
      console.log(`  ${r.tagName} (y=${r.y.toFixed(0)}): ${r.bgColor}`);
    }
  });

  await browser.close();
})();