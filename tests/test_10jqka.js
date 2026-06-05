const { chromium } = require('/usr/local/Cellar/node@20/20.20.2/lib/node_modules/@playwright/test/node_modules/playwright');

(async () => {
  console.log('尝试连接 10jqka 网站...');
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1500, height: 950 }, colorScheme: 'light' });
  const page = await ctx.newPage();
  page.on('pageerror', e => console.log('PAGEERROR:', e.message));
  page.on('console', msg => { if (msg.type() === 'error') console.log('CONSOLE ERR:', msg.text()); });

  try {
    console.log('正在访问: https://stockpage.10jqka.com.cn/000767/');
    const response = await page.goto('https://stockpage.10jqka.com.cn/000767/', { 
      waitUntil: 'domcontentloaded',
      timeout: 30000
    });
    
    if (response) {
      console.log('HTTP 状态:', response.status());
      if (response.ok()) {
        console.log('✅ 网站连接成功');
        
        // 等待页面加载完成
        await page.waitForTimeout(3000);
        
        // 尝试点击操作 - 找到K线图区域
        const klineArea = page.locator('div[class*="chart"]').first();
        if (await klineArea.count() > 0) {
          console.log('✅ 找到 K线图区域');
          await klineArea.click({ position: { x: 500, y: 200 } });
          console.log('✅ 点击成功');
        }
        
        // 截取页面截图
        await page.screenshot({ path: '/tmp/10jqka_000767.png', fullPage: true });
        console.log('✅ 截图已保存: /tmp/10jqka_000767.png');
        
        // 提取页面标题
        const title = await page.title();
        console.log('页面标题:', title);
      } else {
        console.log('❌ 网站访问失败，状态码:', response.status());
      }
    }
  } catch (e) {
    console.log('❌ 连接失败:', e.message);
  }

  await browser.close();
  console.log('测试完成');
})();