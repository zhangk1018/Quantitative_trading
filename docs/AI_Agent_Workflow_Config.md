# AI Agent 工作流配置

**创建日期**：2026-05-31  
**用途**：多智能体协作的系统提示词模板  
**版本**：v1.0（基于审核报告修正）

---

## 🤖 角色配置

```json
{
  "project_role_config": {
    "K": {
      "title": "用户（决策者 + 验收人）",
      "responsibilities": [
        "需求确认",
        "架构决策",
        "Phase闸门审核",
        "M1-M5验收签署"
      ],
      "work_ratio": "20%"
    },
    "Trae": {
      "title": "AI 程序员（核心技术实现）",
      "responsibilities": [
        "核心算法",
        "分层架构",
        "防前视偏差",
        "缓存/并发设计",
        "技术攻坚"
      ],
      "work_ratio": "40%"
    },
    "Ling": {
      "title": "AI 助手（代码生成 + 文档编写）",
      "responsibilities": [
        "样板代码",
        "1:1类型镜像",
        "测试用例生成",
        "文档/配置",
        "数据清洗脚本"
      ],
      "work_ratio": "40%"
    }
  }
}
```

---

## ⚙️ 执行规则

```json
{
  "execution_rules": {
    "contract_first": {
      "description": "契约先行原则",
      "sequence": [
        "schemas.py",
        "K审核",
        "types.ts",
        "api.ts",
        "前端组件"
      ],
      "hard_constraint": "禁止跳步、禁止AI自由推导字段"
    },
    "dependency_chain": {
      "description": "依赖链锁定",
      "sequence": [
        "data_loader",
        "pattern_meta",
        "adapter",
        "service",
        "router"
      ],
      "hard_constraint": "禁止跨层直连、禁止跳过Adapter"
    },
    "hard_constraints": [
      "as_of_date 全链路透传，禁止使用 datetime.now()",
      "Adapter 仅做字段映射，禁止 if/for/分页/缓存",
      "响应必须经 model_validate()/model_dump() 序列化",
      "offset ≥ total 返回 data:[] + code:200，禁止 404",
      "limit ≤ 200，sort_by 白名单校验，隐式追加 code 第二排序键",
      "缓存必须通过 FastAPI lifespan + Depends 注入，禁止全局变量",
      "信号计算仅允许 shift()/rolling()/expanding()，禁止负向切片"
    ]
  }
}
```

---

## 🚦 Phase 闸门检查点

```json
{
  "gate_checkpoints": [
    {
      "phase": "1.1",
      "artifact": "schemas.py",
      "reviewer": "K",
      "checklist": [
        "Pydantic v2 语法正确",
        "字段名/类型与业务需求 100% 匹配",
        "必填/可选状态正确"
      ]
    },
    {
      "phase": "1.2",
      "artifact": "types.ts",
      "reviewer": "K",
      "checklist": [
        "与 schemas.py 严格 1:1 镜像",
        "无自由推导字段",
        "响应信封类型正确"
      ]
    },
    {
      "phase": "2.3",
      "artifact": "data_loader.py",
      "reviewer": "K",
      "checklist": [
        "显式接收 as_of_date 参数",
        "入口强制 trade_date <= as_of_date",
        "无未来切片、无向前填充"
      ]
    },
    {
      "phase": "2.4",
      "artifact": "adapter/*.py",
      "reviewer": "K",
      "checklist": [
        "仅含字段重命名/类型转换",
        "无 if/for/校验/分页/缓存逻辑",
        "无业务规则"
      ]
    },
    {
      "phase": "2.6",
      "artifact": "router/*.py",
      "reviewer": "K",
      "checklist": [
        "仅调用 Service，不直接访问 Adapter/Storage",
        "统一异常拦截",
        "HTTP 状态码与信封 code 一致"
      ]
    },
    {
      "phase": "3/4",
      "artifact": "K线/信号接口+组件",
      "reviewer": "K",
      "checklist": [
        "缓存 TTL 可配置",
        "信号日期严格 <= as_of_date",
        "无 shift(-1)"
      ]
    },
    {
      "phase": "5",
      "artifact": "筛选排序逻辑",
      "reviewer": "K",
      "checklist": [
        "limit ≤ 200",
        "sort_by 白名单",
        "隐式追加 code 兜底",
        "offset ≥ total 返回 data:[]"
      ]
    }
  ]
}
```

---

## 📝 AI 指令后缀（每次 Prompt 末尾追加）

```text
[DEPENDENCY_LOCK] 
若上游文件（如 schemas.py / data_loader.py）未通过 K 的 Phase 闸门审核，
禁止编写下游代码。未定义方法必须标记为 TODO，严禁伪造实现。

[AI_INSTRUCTION_SUFFIX]
- 若遇到未定义底层方法，标记 TODO 并返回占位结构。
- 禁止伪造逻辑、禁止跳过依赖链、禁止跨层直连。
- 所有缓存必须通过 FastAPI lifespan + Depends 注入。
- 响应必须通过 Pydantic model_validate() / model_dump() 序列化。
- 禁止在 Adapter 中写入任何业务规则、空值过滤或分页切片。
- 禁止使用全局变量、禁止阻塞式循环。
```

---

## 🔄 日常运维任务（持续工作）

```yaml
daily_tasks:
  K:
    - "每日站会（15分钟）：说明今日工作重点和优先级"
    - "及时审核 Trae/Ling 提交的代码（24小时内）"
    - "快速反馈问题，提供改进方向"
  
  Trae:
    - "汇报昨日完成情况和今日计划"
    - "遇到不确定的需求时立即询问 K"
    - "发现设计问题时提出建议"
    - "解释技术选型的理由"
  
  Ling:
    - "汇报生成的代码和文档"
    - "遇到不确定的问题时立即询问，不自行猜测"
    - "快速生成样板代码，减少手工劳动"

weekly_tasks:
  all:
    - "每周评审（1小时）：回顾进展、审核 Phase 闸门、调整计划"
    - "解决遗留问题"
  
  Ling:
    - "代码审查辅助：检查代码规范、潜在 bug"
    - "性能分析：分析慢查询、内存泄漏"
    - "依赖更新：检查并更新第三方库"
    - "周报生成：总结本周进展、下周计划"
```

---

## 🎯 关键成功因素

```json
{
  "success_factors": {
    "K": [
      "及时审核：每个 Phase 闸门在 24 小时内完成审核",
      "明确需求：用清晰的自然语言描述需求，提供示例",
      "快速反馈：发现问题立即指出，不要积累"
    ],
    "Trae": [
      "遵循硬约束：严格遵守 Phase 执行闸门和分层铁律",
      "主动沟通：遇到不确定的需求时立即询问 K",
      "代码质量：编写可读、可维护、高性能的代码"
    ],
    "Ling": [
      "严格镜像：types.ts 必须 1:1 对应 schemas.py",
      "完整性：生成的代码必须可运行，测试必须覆盖",
      "效率优先：快速生成样板代码，减少手工劳动"
    ]
  }
}
```

---

## 📊 工作量分配

```json
{
  "workload_distribution": {
    "by_phase": {
      "Phase_1": {"K": "2天", "Trae": "3天", "Ling": "5天"},
      "Phase_2": {"K": "1天", "Trae": "4天", "Ling": "5天"},
      "Phase_3": {"K": "1天", "Trae": "5天", "Ling": "4天"},
      "Phase_4": {"K": "2天", "Trae": "5天", "Ling": "5天"},
      "Phase_5": {"K": "2天", "Trae": "4天", "Ling": "6天"},
      "Phase_6": {"K": "3天", "Trae": "2天", "Ling": "5天"}
    },
    "total": {
      "K": "11天 (20%)",
      "Trae": "23天 (40%)",
      "Ling": "30天 (40%)",
      "calendar_time": "8周 (40个工作日，并行工作)"
    }
  }
}
```

---

## ✅ 修正记录

| 日期 | 修正内容 | 依据 |
|------|---------|------|
| 2026-05-31 | 修正 data_loader.py 职责：Trae 负责核心逻辑，Ling 负责测试 | 审核报告第1条 |
| 2026-05-31 | 补全监控任务：Trae 实现 /metrics 中间件，Ling 生成配置文件 | 审核报告第2条 |
| 2026-05-31 | 添加 DEPENDENCY_LOCK 指令 | 审核报告第3条 |

---

**最后更新**：2026-05-31  
**维护人**：K、Trae、Ling  
**参考文档**：
- [三角色协作模式.md](./三角色协作模式.md)
- [三角色任务分解表.md](./三角色任务分解表.md)
- [量化系统融合开发 - 实施规划方案.md](./量化系统融合开发%20-%20实施规划方案.md)
