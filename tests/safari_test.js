const { webkit } = require('/usr/local/Cellar/node@20/20.20.2/lib/node_modules/@playwright/test/node_modules/playwright');

(async () => {
  console.log('尝试使用 WebKit（Safari 引擎）...');
  const browser = await webkit.launch({ 
    headless: false,  // 显示浏览器窗口
    slowMo: 1000     // 慢动作，方便观察
  });
  
  const ctx = await browser.newContext({ 
    viewport: { width: 1200, height: 800 },
    colorScheme: 'light'
  });
  
  const page = await ctx.newPage();
  page.on('pageerror', e => console.log('页面错误:', e.message));
  
  try {
    console.log('正在打开本地 K线图页面...');
    await page.goto('http://localhost:5173/', { waitUntil: 'domcontentloaded' });
    console.log('✅ 页面已加载');
    
    // 等待表格出现
    await page.waitForSelector('table', { timeout: 15000 });
    console.log('✅ 股票表格已加载');
    
    // 点击第一行股票
    await page.locator('table tbody tr').first().click();
    console.log('✅ 点击了第一行股票');
    
    // 等待 K线图渲染
    await page.waitForSelector('canvas', { timeout: 10000 });
    await page.waitForTimeout(2000);
    console.log('✅ K线图已渲染');
    
    // 等待用户观察
    console.log('请观察浏览器窗口，按任意键继续...');
    await new Promise(resolve => setTimeout(resolve, 10000));
    
    // 关闭浏览器
    await browser.close();
    console.log('浏览器已关闭');
    
  } catch (e) {
    console.log('❌ 操作失败:', e.message);
    await browser.close();
  }
})();