const { chromium } = require('/usr/local/Cellar/node@20/20.20.2/lib/node_modules/@playwright/test/node_modules/playwright');

(async () => {
  console.log('打开K线图窗口...');
  
  const browser = await chromium.launch({
    headless: false,
    args: ['--window-size=1500,950']
  });
  
  const ctx = await browser.newContext({
    viewport: { width: 1500, height: 950 },
    colorScheme: 'light'
  });
  
  const page = await ctx.newPage();
  
  await page.goto('http://localhost:5173/', { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('table', { timeout: 15000 });
  
  // 点击第一行股票
  await page.locator('table tbody tr').first().click();
  await page.waitForSelector('canvas', { timeout: 10000 });
  await page.waitForTimeout(2000);
  
  console.log('✅ K线图已打开，窗口保持打开状态...');
  
  // 保持窗口打开（不关闭）
})();