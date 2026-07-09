import { test, expect } from '@playwright/test';

test('选股页面基础测试', async ({ page }) => {
  await page.goto('/picker');
  
  // 验证页面标题
  await expect(page.getByText('因子综合排名')).toBeVisible();
  
  // 验证核心组件
  await expect(page.getByRole('button', { name: '开始选股' })).toBeEnabled();
  await expect(page.getByTestId('sort-change_pct')).toBeVisible();
  
  // 执行选股操作
  await page.getByRole('button', { name: '开始选股' }).click();
  await expect(page.getByText(/选股成功|未筛选到符合条件的股票/)).toBeVisible({
    timeout: 10000
  });
});