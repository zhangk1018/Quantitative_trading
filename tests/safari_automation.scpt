#!/usr/bin/osascript
-- Safari 浏览器自动化脚本

tell application "Safari"
    activate
    
    -- 检查是否有打开的窗口
    if (count of windows) = 0 then
        make new document
    end if
    
    -- 设置窗口大小
    set bounds of front window to {100, 100, 1200, 800}
    
    -- 打开本地 K线图页面
    set URL of document 1 to "http://localhost:5173/"
    
    -- 等待页面加载
    delay 5
    
    -- 尝试点击表格第一行（需要 JavaScript）
    do JavaScript "
        setTimeout(() => {
            const table = document.querySelector('table');
            if (table) {
                const firstRow = table.querySelector('tbody tr');
                if (firstRow) {
                    firstRow.click();
                }
            }
        }, 2000);
    " in document 1
    
    display dialog "K线图已打开，点击确定继续" buttons {"确定"} default button 1
    
    -- 关闭 Safari
    -- quit
end tell