const { chromium } = require('/usr/local/Cellar/node@20/20.20.2/lib/node_modules/@playwright/test/node_modules/playwright');

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1500, height: 950 }, colorScheme: 'light' });
  const page = await ctx.newPage();

  await page.goto('http://localhost:5173/', { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('table', { timeout: 15000 });
  await page.locator('table tbody tr').first().click();
  await page.waitForTimeout(2500);

  // 检查 prefers-color-scheme
  const prefersDark = await page.evaluate(() => {
    return window.matchMedia('(prefers-color-scheme: dark)').matches;
  });
  console.log('prefers-color-scheme: dark matches?', prefersDark);

  // 检查 Tailwind dark class 是否生效
  const darkBg = await page.evaluate(() => {
    const el = document.querySelector('.bg-gray-50.dark:bg-gray-900');
    if (!el) return null;
    const styles = window.getComputedStyle(el);
    return styles.backgroundColor;
  });
  console.log('K线图外层容器背景色:', darkBg);

  await page.screenshot({ path: '/Users/zhangk/workspace/Quantitative_trading/docs/research/echarts_verify/2026-06-05_debug_theme.png', fullPage: false });
  console.log('截图已保存');

  await browser.close();
})();