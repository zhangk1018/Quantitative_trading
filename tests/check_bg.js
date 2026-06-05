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

  // 检查 K线图外层容器的背景色
  const bgColor = await page.evaluate(() => {
    const el = document.querySelector('[class*="bg-gray-50"]');
    if (!el) return null;
    const styles = window.getComputedStyle(el);
    return { bgColor: styles.backgroundColor, className: el.className };
  });
  console.log('K线图外层容器:', bgColor);

  await browser.close();
})();