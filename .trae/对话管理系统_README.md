# 量化交易项目 - 三层对话管理系统

## 🎯 系统概述

基于**三层机制 + Git版本化**的对话管理系统，专门为解决量化交易项目开发中的上下文窗口限制问题而设计。系统完美适配PDCA工作流，支持自动化上下文监控、高质量总结生成和新对话自动恢复。

## 📁 文件结构

```
.trae/
├── conversation_manager.py      # 核心管理模块
├── summary_template.md          # 标准化摘要模板
├── reload_context.py            # 新对话自动加载脚本
├── 使用示例.py                   # 完整使用示例
├── conversation_history/        # 对话历史存储目录
│   └── summary_20260602_181048.json  # 自动生成的总结文件
└── 对话管理系统_README.md        # 本文档
```

## 🏗️ 三层对话管理机制

### 1. 实时摘要层
- **功能**: 对话过程中轻量化摘要，不占用算力
- **触发**: 重要里程碑后手动调用
- **输出**: 结构化数据，便于后续处理

### 2. 智能压缩层
- **功能**: 上下文达到80%时生成高质量总结
- **触发**: 自动监控，阈值触发
- **输出**: 标准化JSON总结文件 + Git提交

### 3. 重启恢复层
- **功能**: 新对话自动加载最新上下文
- **触发**: 每次新对话开始时运行
- **输出**: 完整项目状态恢复

## 🚀 快速开始

### 第一步：初始化系统
```bash
# 确保目录结构完整
mkdir -p .trae/conversation_history
```

### 第二步：新对话开始
```bash
# 每次开启新对话时运行
python3 .trae/reload_context.py
```

### 第三步：监控上下文
```python
from conversation_manager import ConversationManager

# 初始化管理器
manager = ConversationManager()

# 模拟当前token使用情况
current_tokens = 7500  # 当前已使用token数
conversation_content = "当前开发内容..."

# 自动管理对话（达到阈值时自动总结）
summary = manager.auto_manage_conversation(current_tokens, conversation_content)
```

## 🔧 核心配置

### 配置文件参数
```python
# 在 conversation_manager.py 中调整
CONTEXT_WINDOW_LIMIT = 10000  # 模型总上下文窗口大小
TRIGGER_THRESHOLD = 0.8       # 触发阈值（80%）
SAVE_DIR = ".trae/conversation_history"  # 存储目录
```

### 标准化模板
- 位置: `.trae/summary_template.md`
- 作用: 保证总结质量，避免模糊描述
- 更新: 根据项目阶段调整模板内容

## 📊 使用场景示例

### 场景1：日常开发监控
```python
# 在开发过程中定期检查
def check_context_usage():
    manager = ConversationManager()
    current_tokens = estimate_current_tokens()  # 估算当前token数
    
    if manager.check_context_threshold(current_tokens):
        print("⚠️  建议进行对话总结")
        # 可以手动触发总结
        summary = manager.generate_structured_summary(get_current_conversation())
        manager.save_summary_to_file(summary)
```

### 场景2：里程碑总结
```python
# 完成重要功能后手动总结
def milestone_summary(milestone_name, completed_tasks, next_steps):
    manager = ConversationManager()
    
    summary = {
        "项目阶段": f"量化交易 {milestone_name}",
        "对话时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "核心工作内容": completed_tasks,
        "待办事项": next_steps,
        "上下文接续关键词": [milestone_name, "下一步开发", "问题解决"]
    }
    
    file_path = manager.save_summary_to_file(summary)
    manager.git_commit_summary(file_path)
```

### 场景3：团队协作交接
```bash
# 新成员加入或任务交接时
# 1. 查看最新总结
cat .trae/conversation_history/latest_summary.json

# 2. 加载项目上下文
python3 .trae/reload_context.py

# 3. 查看历史记录
ls -la .trae/conversation_history/
```

## 🔄 PDCA循环集成

### Plan阶段
- 在总结中记录规划内容
- 设置开发目标和里程碑

### Do阶段
- 记录执行的开发工作
- 跟踪代码变更和配置调整

### Check阶段
- 上下文达到80%时自动检查
- 生成结构化总结报告

### Act阶段
- 新对话自动加载上下文
- 持续迭代优化开发流程

## 💾 Git版本化管理

### 自动提交
系统自动将总结文件提交到Git，实现：
- ✅ 历史版本可回溯
- ✅ 意外丢失可恢复
- ✅ 团队协作可共享

### 查看历史
```bash
# 查看对话历史提交
git log --oneline --grep="对话上下文"

# 查看具体总结内容
git show HEAD:.trae/conversation_history/summary_*.json
```

## 🛠️ 高级功能

### 自定义总结模板
```python
# 创建自定义模板
custom_template = {
    "项目信息": "",
    "技术架构": "",
    "数据状态": "",
    "性能指标": "",
    "风险问题": ""
}

# 使用自定义模板
manager.summary_template = custom_template
```

### 批量处理历史
```python
# 分析所有历史总结
def analyze_conversation_history():
    manager = ConversationManager()
    history_dir = manager.SAVE_DIR
    
    summaries = []
    for file in os.listdir(history_dir):
        if file.endswith(".json"):
            with open(os.path.join(history_dir, file), 'r') as f:
                summaries.append(json.load(f))
    
    # 分析趋势、识别模式、生成报告
    return analyze_summaries(summaries)
```

## 📈 性能优化建议

### 1. 阈值调整
- 根据模型特性调整`TRIGGER_THRESHOLD`
- 高复杂度任务：降低阈值（如70%）
- 简单任务：提高阈值（如85%）

### 2. 存储优化
- 定期清理旧总结文件
- 压缩历史数据
- 使用增量存储策略

### 3. 监控增强
- 添加实时token估算
- 设置预警机制
- 集成性能分析

## 🚨 故障排除

### 常见问题

| 问题 | 解决方案 |
|------|----------|
| Git提交失败 | 检查Git配置，确保有提交权限 |
| 文件保存失败 | 检查目录权限，确保可写 |
| 模板加载失败 | 检查summary_template.md文件格式 |
| 上下文加载失败 | 检查conversation_history目录文件 |

### 调试模式
```python
# 启用详细日志
import logging
logging.basicConfig(level=logging.DEBUG)

manager = ConversationManager()
# 执行操作查看详细日志
```

## 📚 最佳实践

### 开发流程
1. **开始新对话**: 运行`reload_context.py`
2. **定期检查**: 开发过程中监控上下文使用率
3. **里程碑总结**: 完成重要功能后手动总结
4. **问题记录**: 将遇到的问题记录在总结中
5. **计划更新**: 根据总结调整下一步计划

### 团队协作
1. **统一模板**: 团队使用相同的总结模板
2. **定期同步**: 定期分享对话总结
3. **版本控制**: 所有总结纳入Git管理
4. **知识传承**: 新成员通过历史总结快速上手

## 🔗 相关资源

### 项目文档
- [工作分工方案.md](../docs/工作分工方案.md)
- [三角色任务分解表.md](../docs/三角色任务分解表.md)
- [项目工作规则.md](./project_rules.md)

### 技术参考
- Python官方文档
- Git使用指南
- JSON数据格式规范

## 🎉 开始使用

现在您已经拥有了完整的对话管理系统，可以：

1. **立即使用**: 运行`python3 .trae/reload_context.py`开始新对话
2. **集成到项目**: 在关键节点调用对话管理功能
3. **自定义扩展**: 根据项目需求调整系统配置
4. **团队推广**: 与团队成员分享使用经验

**祝您在量化交易项目开发中高效、有序、无中断！**