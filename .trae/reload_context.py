#!/usr/bin/env python3
"""
新对话自动加载脚本
每次开启新对话时运行此脚本，自动加载最新的项目上下文
"""

import sys
import os
from datetime import datetime

# 添加.trae目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from conversation_manager import ConversationManager

def reload_project_context():
    """新对话初始化：自动加载最新上下文"""
    print("=" * 60)
    print("🚀 启动新对话 - 量化交易项目上下文加载")
    print("=" * 60)
    
    manager = ConversationManager()
    latest_summary = manager.load_latest_summary()
    
    if latest_summary:
        print("\n📊 已加载历史上下文摘要")
        print("-" * 40)
        
        # 显示关键信息
        print(f"📅 总结时间: {latest_summary.get('对话时间', '未知')}")
        print(f"🎯 项目阶段: {latest_summary.get('项目阶段', '未知')}")
        
        print("\n✅ 已完成工作:")
        for item in latest_summary.get("核心工作内容", []):
            print(f"  • {item}")
        
        print("\n📋 待办事项:")
        for item in latest_summary.get("待办事项", []):
            print(f"  • {item}")
        
        print("\n🔑 接续关键词:")
        keywords = latest_summary.get("上下文接续关键词", [])
        print("  " + ", ".join(keywords[:5]) + ("..." if len(keywords) > 5 else ""))
        
        print("\n" + "=" * 60)
        print("✅ 上下文加载完成，可以继续开发！")
        print("=" * 60)
        
        # 返回摘要供进一步使用
        return latest_summary
    else:
        print("\nℹ️ 无历史上下文，全新对话开始")
        print("\n📁 项目基本信息:")
        print(f"  项目路径: {os.path.dirname(os.path.dirname(os.path.abspath(__file__)))}")
        print(f"  当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        print("\n" + "=" * 60)
        print("🚀 全新对话启动，开始量化交易项目开发！")
        print("=" * 60)
        return None

def display_project_status():
    """显示项目当前状态"""
    print("\n📈 项目状态概览")
    print("-" * 40)
    
    # 检查关键目录
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    status_items = [
        ("📁 项目结构", os.path.exists(os.path.join(project_root, "src"))),
        ("🔧 后端API", os.path.exists(os.path.join(project_root, "src/backend"))),
        ("🎨 前端组件", os.path.exists(os.path.join(project_root, "src/frontend"))),
        ("📊 数据导入", os.path.exists(os.path.join(project_root, "scripts/import_daily_data.py"))),
        ("📝 文档管理", os.path.exists(os.path.join(project_root, "docs"))),
    ]
    
    for name, exists in status_items:
        status = "✅" if exists else "❌"
        print(f"{status} {name}")
    
    return all(exists for _, exists in status_items)

def main():
    """主函数"""
    try:
        # 1. 加载最新上下文
        context = reload_project_context()
        
        # 2. 显示项目状态
        display_project_status()
        
        # 3. 提供使用提示
        print("\n💡 使用提示:")
        print("  1. 监控上下文: manager.auto_manage_conversation(token数, 对话内容)")
        print("  2. 查看历史: .trae/conversation_history/ 目录")
        print("  3. 编辑模板: .trae/summary_template.md")
        
        return 0
        
    except Exception as e:
        print(f"\n❌ 加载上下文时出错: {str(e)}")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)