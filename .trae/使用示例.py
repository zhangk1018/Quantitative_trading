#!/usr/bin/env python3
"""
对话管理系统使用示例
展示如何在量化交易项目中集成三层对话管理系统
"""

import sys
import os
from datetime import datetime

# 添加.trae目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from conversation_manager import ConversationManager

def example_usage():
    """示例：在量化交易项目中使用对话管理系统"""
    
    print("=" * 70)
    print("📊 量化交易项目 - 对话管理系统使用示例")
    print("=" * 70)
    
    # 1. 初始化对话管理器
    print("\n1️⃣ 初始化对话管理器...")
    manager = ConversationManager()
    print("✅ 对话管理器初始化完成")
    
    # 2. 模拟当前上下文使用情况
    print("\n2️⃣ 模拟上下文使用情况...")
    current_tokens = 7500  # 当前已使用token数
    max_tokens = 10000     # 总上下文窗口
    
    print(f"   当前token使用: {current_tokens}/{max_tokens} ({current_tokens/max_tokens*100:.1f}%)")
    
    # 3. 检查是否达到阈值
    print("\n3️⃣ 检查上下文阈值...")
    if manager.check_context_threshold(current_tokens):
        print("   ⚠️  上下文使用率超过80%，建议进行总结")
    else:
        print("   ✅ 上下文使用率正常")
    
    # 4. 模拟对话内容
    print("\n4️⃣ 模拟当前对话内容...")
    conversation_content = """
    当前正在开发量化交易系统的Phase 2：
    - 已完成：后端目录结构搭建
    - 进行中：数据加载层开发
    - 待完成：Adapter隔离层
    - 问题：361只股票数据导入失败
    
    下一步计划：
    1. 创建adapter目录结构
    2. 完善data_loader.py的缓存机制
    3. 解决数据导入网络问题
    """
    
    print("   对话内容摘要：")
    for line in conversation_content.strip().split('\n'):
        if line.strip():
            print(f"     {line.strip()}")
    
    # 5. 自动管理对话（如果达到阈值）
    print("\n5️⃣ 执行自动对话管理...")
    summary = manager.auto_manage_conversation(current_tokens, conversation_content)
    
    if summary:
        print("\n📋 生成的总结摘要：")
        print(f"   项目阶段: {summary['项目阶段']}")
        print(f"   总结时间: {summary['对话时间']}")
        print(f"   待办事项: {len(summary['待办事项'])}项")
        print(f"   接续关键词: {', '.join(summary['上下文接续关键词'][:3])}")
    else:
        print("   ℹ️ 上下文未达到阈值，无需总结")
    
    # 6. 加载最新上下文（模拟新对话开始）
    print("\n6️⃣ 模拟新对话开始，加载历史上下文...")
    latest_context = manager.load_latest_summary()
    
    if latest_context:
        print("\n✅ 成功加载历史上下文")
        print(f"   最新总结时间: {latest_context['对话时间']}")
        print(f"   项目状态: {latest_context['项目阶段']}")
        
        print("\n📝 待办事项列表：")
        for i, task in enumerate(latest_context['待办事项'], 1):
            print(f"   {i}. {task}")
    else:
        print("   ℹ️ 无历史上下文")
    
    # 7. 集成到PDCA循环的示例
    print("\n" + "=" * 70)
    print("🔄 PDCA循环集成示例")
    print("=" * 70)
    
    pdca_example = """
    Plan阶段：
      - 规划Phase 2的Adapter层开发
      - 设计缓存机制架构
    
    Do阶段：
      - 创建adapter目录结构
      - 实现字段映射逻辑
    
    Check阶段：
      - 上下文达到80%时自动总结
      - 检查开发进度和问题
    
    Act阶段：
      - 新对话自动加载上下文
      - 继续未完成的任务
      - 优化开发流程
    """
    
    print(pdca_example)
    
    # 8. 实际项目集成建议
    print("\n" + "=" * 70)
    print("💡 实际项目集成建议")
    print("=" * 70)
    
    suggestions = """
    建议集成点：
    1. 在每次重要里程碑后手动调用总结
    2. 在长时间对话中定期检查上下文使用率
    3. 每次新对话开始时运行reload_context.py
    4. 将对话历史纳入Git版本管理
    
    配置文件调整：
    - 根据实际模型调整CONTEXT_WINDOW_LIMIT
    - 根据项目阶段更新summary_template.md
    - 根据团队习惯调整触发阈值
    
    自动化建议：
    - 可以设置定时任务检查上下文
    - 可以集成到CI/CD流程中
    - 可以添加邮件/消息通知
    """
    
    print(suggestions)
    
    print("\n" + "=" * 70)
    print("🎯 对话管理系统已就绪，开始高效开发吧！")
    print("=" * 70)

def main():
    """主函数"""
    try:
        example_usage()
        return 0
    except Exception as e:
        print(f"\n❌ 示例运行出错: {str(e)}")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)