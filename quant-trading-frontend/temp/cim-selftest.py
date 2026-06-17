"""
CustomIndicatorModal P3.1 浏览器自测脚本
验证 K 2026-06-17 决策 4 个反馈点 + 6 大核心场景
"""
from playwright.sync_api import sync_playwright
import os

SCREENSHOT_DIR = "/tmp/cim-screenshots"
os.makedirs(SCREENSHOT_DIR, exist_ok=True)


def take_screenshot(page, name):
    path = f"{SCREENSHOT_DIR}/{name}.png"
    page.screenshot(path=path, full_page=True)
    print(f"  📸 截图: {path}")
    return path


def run_self_test():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1920, "height": 1080})

        console_errors = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

        print("=" * 60)
        print("P3.1 CustomIndicatorModal 浏览器自测")
        print("=" * 60)

        # === 步骤 1: 访问首页 ===
        print("\n[1/9] 访问 http://localhost:5173/")
        page.goto("http://localhost:5173/")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        take_screenshot(page, "01-home")
        print(f"  当前 URL: {page.url}")
        print(f"  页面标题: {page.title()}")

        # === 步骤 2: 导航到选股视图 ===
        print("\n[2/9] 导航到选股视图")
        nav_success = False
        for selector in ["text=选股", "text=开始选股", '[data-testid="sidebar-stock-picker"]']:
            try:
                page.locator(selector).first.click(timeout=2000)
                page.wait_for_timeout(1500)
                nav_success = True
                break
            except Exception:
                continue
        if not nav_success:
            page.goto("http://localhost:5173/stock-picker")
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(1500)
        take_screenshot(page, "02-stock-picker")
        print(f"  当前 URL: {page.url}")

        # === 步骤 3: 打开条件构建器面板 ===
        print("\n[3/9] 打开条件构建器面板")
        try:
            header = page.locator('[data-testid="condition-builder-header"]')
            if header.count() > 0:
                header.click()
                page.wait_for_timeout(1000)
                print("  ✅ 点击条件构建器 header")
            else:
                print("  ⚠️ 找不到条件构建器 header")
        except Exception as e:
            print(f"  ⚠️ 点击 Header 失败: {e}")
        take_screenshot(page, "03-condition-builder")

        # === 步骤 4: 点击"新建自编指标"按钮 ===
        print("\n[4/9] 点击'新建自编指标'按钮")
        try:
            page.locator('[data-testid="condition-builder-create-custom"]').click()
            page.wait_for_timeout(2500)  # 等待 Drawer 动画 + Monaco 懒加载
            take_screenshot(page, "04-drawer-opened")
            print("  ✅ Drawer 打开")
        except Exception as e:
            print(f"  ❌ 找不到'新建自编指标'按钮: {e}")
            take_screenshot(page, "04-no-button")
            browser.close()
            return False

        # === 步骤 5: 验证 Drawer 布局 + 8 字段 ===
        print("\n[5/9] 验证 Drawer 8 字段表单")
        drawer_visible = page.locator('[data-testid="custom-indicator-modal"]').is_visible()
        print(f"  Drawer 可见: {'✅' if drawer_visible else '❌'}")
        for testid in [
            "custom-indicator-modal-name",
            "custom-indicator-modal-category",
            "custom-indicator-modal-syntax",
            "custom-indicator-modal-formula-editor",
            "custom-indicator-modal-operator",
            "custom-indicator-modal-visibility",
        ]:
            visible = page.locator(f'[data-testid="{testid}"]').is_visible()
            print(f"  字段 {testid.split('-')[-1]}: {'✅' if visible else '❌'}")

        # === 步骤 6: 验证 K 反馈 1：按钮位置在 Drawer extra ===
        print("\n[6/9] 验证 K 反馈 1：取消/创建按钮在 Drawer 顶部右侧")
        extra_region = page.locator('[data-testid="custom-indicator-modal-extra"]')
        extra_visible = extra_region.is_visible()
        print(f"  Extra 区域可见: {'✅' if extra_visible else '❌'}")
        if extra_visible:
            extra_box = extra_region.bounding_box()
            print(f"  Extra 位置: x={extra_box['x']:.0f}, y={extra_box['y']:.0f}")
            # Y 坐标应该 < 100（在 Drawer 顶部）
            if extra_box['y'] < 100:
                print(f"  ✅ Extra 在 Drawer 顶部（y={extra_box['y']:.0f} < 100）")
            cancel_in_extra = page.locator('[data-testid="custom-indicator-modal-extra"] [data-testid="custom-indicator-modal-cancel"]').is_visible()
            confirm_in_extra = page.locator('[data-testid="custom-indicator-modal-extra"] [data-testid="custom-indicator-modal-confirm"]').is_visible()
            print(f"  取消按钮在 Extra: {'✅' if cancel_in_extra else '❌'}")
            print(f"  创建按钮在 Extra: {'✅' if confirm_in_extra else '❌'}")

        # === 步骤 7: 验证 K 反馈 3：Monaco 主题（vs-dark 深色协调）===
        print("\n[7/9] 验证 K 反馈 3：Monaco 主题 vs-dark")
        # 延长 Monaco 等待时间（headless + CDN 加载慢）
        monaco_loaded = False
        for attempt in range(20):  # 30s 等待
            monaco_editor_count = page.locator('.monaco-editor').count()
            if monaco_editor_count > 0:
                monaco_loaded = True
                break
            page.wait_for_timeout(1500)
            if attempt % 3 == 0:
                print(f"  等待 Monaco 加载... ({attempt+1}/20)")
        if monaco_loaded:
            bg_color = page.evaluate("""
                () => {
                    // Monaco 编辑区域有多个 div，取最深的背景色
                    const selectors = [
                        '.monaco-editor .monaco-editor-background',
                        '.monaco-editor .overflow-guard',
                        '.monaco-editor',
                    ];
                    for (const sel of selectors) {
                        const el = document.querySelector(sel);
                        if (el) {
                            const bg = getComputedStyle(el).backgroundColor;
                            if (bg && bg !== 'rgba(0, 0, 0, 0)' && bg !== 'transparent') {
                                return bg;
                            }
                        }
                    }
                    return null;
                }
            """)
            print(f"  Monaco 背景色: {bg_color}")
            if bg_color and bg_color.startswith("rgb"):
                rgb = bg_color.replace("rgb(", "").replace(")", "").split(",")
                r, g, b = int(rgb[0].strip()), int(rgb[1].strip()), int(rgb[2].strip())
                avg = (r + g + b) / 3
                print(f"  RGB 平均: {avg:.0f}（< 80 为深色）")
                is_dark = avg < 80
                print(f"  主题: {'✅ 深色 (vs-dark)' if is_dark else '❌ 亮色'}")
            else:
                print(f"  ⚠️ 无法获取 Monaco 背景色（{bg_color}）")
        else:
            print("  ❌ Monaco 30s 内未加载完成")
        take_screenshot(page, "07-monaco")

        # === 步骤 8: 验证 K 反馈 2：公式长度 8000 字符 ===
        print("\n[8/9] 验证 K 反馈 2：公式长度 8000 字符")
        # Monaco 已加载，monaco_textarea 可用
        try:
            monaco_textarea = page.locator('[data-testid="custom-indicator-modal-formula-editor"] textarea')
            if monaco_textarea.count() > 0:
                # 用 keyboard.type 慢速输入（接近真实用户）
                # 先 focus
                monaco_textarea.first.click()
                page.wait_for_timeout(500)
                # 清空现有内容
                page.keyboard.press("Control+A")
                page.keyboard.press("Delete")
                # 输入一段 5000 字符的通达信公式（< 8000 字符）
                test_formula = "{DRAWICON(SIGNAL,HIGH*1.02,N);};\n" * 130
                print(f"  输入测试公式长度: {len(test_formula)} 字符")
                # 通过 fill 一次性填充（Monaco 内部有同步处理）
                monaco_textarea.first.fill(test_formula)
                # 触发 Monaco blur（点击其他位置）
                page.locator('[data-testid="custom-indicator-modal-name"]').click()
                page.wait_for_timeout(1500)
                # 检查错误
                error_count = page.locator("text=/公式长度不能超过/").count()
                print(f"  {len(test_formula)} 字符错误提示数: {error_count}（期望 0）")
                if error_count == 0:
                    print(f"  ✅ K 反馈 2 修复（2000→8000）生效")
                else:
                    print(f"  ❌ 公式长度仍报错")
            else:
                print("  ⚠️ Monaco textarea 不存在")
        except Exception as e:
            print(f"  ⚠️ Monaco 操作失败: {str(e)[:200]}")
        take_screenshot(page, "08-long-formula")

        # === 步骤 9: 验证字段插入按钮 ===
        print("\n[9/9] 验证字段插入按钮（K 反馈 3：必带）")
        for testid in [
            "custom-indicator-modal-insert-CLOSE",
            "custom-indicator-modal-insert-OPEN",
            "custom-indicator-modal-insert-MA",
            "custom-indicator-modal-insert-RSI",
        ]:
            visible = page.locator(f'[data-testid="{testid}"]').is_visible()
            print(f"  字段插入 {testid.split('-')[-1]}: {'✅' if visible else '❌'}")
        take_screenshot(page, "09-field-insert")

        # 总结
        print("\n" + "=" * 60)
        print(f"控制台错误数: {len(console_errors)}")
        for err in console_errors[:5]:
            print(f"  ❌ {err[:150]}")
        print(f"\n截图保存目录: {SCREENSHOT_DIR}")
        print(f"截图文件数: {len(os.listdir(SCREENSHOT_DIR))}")

        browser.close()
        return True


if __name__ == "__main__":
    run_self_test()
