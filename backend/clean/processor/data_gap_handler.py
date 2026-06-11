"""
data_gap_handler.py - 【已迁移】数据缺口检测和补全

【迁移说明】
- 真实实现: backend/imputer/incomplete_handler.py
- 本文件保留为向后兼容的 re-export 层
- 新代码请直接从 `from backend.imputer import DataGapDetector, DataGapFiller` 导入

【为什么迁移】
- imputer/ 是统一的数据补全模块（含复权、缺失值填充、缺口补全）
- 把"数据补全"相关的所有逻辑集中管理

【未来计划】
- v2.0: 删除此兼容层
"""

# Re-export from new location
from backend.imputer.incomplete_handler import DataGapDetector, DataGapFiller


__all__ = ['DataGapDetector', 'DataGapFiller']
