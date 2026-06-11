"""
frontend/utils - 前台工具

【设计目标】
- 与后台无关的纯工具（数学计算、文件 IO）
- API 客户端（不直接访问数据库）
"""

from .api_client import BackendClient


__all__ = ['BackendClient']
