const { chromium } = require('/usr/local/Cellar/node@20/20.20.2/lib/node_modules/@playwright/test/node_modules/playwright');

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1500, height: 950 }, colorScheme: 'light' });
  const page = await ctx.newPage();

  await page.goto('http://localhost:5173/', { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('table', { timeout: 15000 });
  await page.locator('table tbody tr').first().click();
  await page.waitForTimeout(2500);

  // 检查所有 div 的背景色
  const allDivs = await page.evaluate(() => {
    const divs = document.querySelectorAll('div');
    const results = [];
    divs.forEach(el => {
      const rect = el.getBoundingClientRect();
      if (rect.top < 100 && rect.height > 10) {
        const style = window.getComputedStyle(el);
        const bg = style.backgroundColor;
        // 只关注深色背景
        if (bg.includes('17') || bg.includes('31') || bg.includes('rgb(17, 24, 39)') || bg.includes('rgb(31, 41, 55)')) {
          results.push({
            className: el.className,
            bgColor: bg,
            y: rect.top.toFixed(0),
            height: rect.height.toFixed(0)
          });
        }
      }
    });
    return results;
  });
  console.log('头部区域深色背景元素:');
  allDivs.forEach(r => {
    console.log(`  class="${r.className}" y=${r.y} h=${r.height} bg=${r.bgColor}`);
  });

  await browser.close();
})();