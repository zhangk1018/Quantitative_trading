"""市场分类工具模块 — 统一管理股票代码到板块的映射逻辑。

所有需要根据股票代码判断所属板块的代码，统一使用此模块的函数，
避免多处理自维护分类逻辑导致不一致。
"""

from typing import List


def classify_market(code: str) -> str:
    """根据股票代码前缀返回所属板块名称。

    Args:
        code: 6位股票代码（如 '600000', '000001', '688001'）

    Returns:
        板块名称: '上海主板' / '深圳主板' / '创业板' / '科创板' / '北交所' / '其他'
    """
    prefix_3 = code[:3]
    prefix_2 = code[:2]

    if prefix_2 == '60':
        return '上海主板'
    if prefix_3 in ('688', '689'):
        return '科创板'
    if prefix_3 in ('000', '001', '002', '003'):
        return '深圳主板'
    if prefix_3 in ('300', '301', '302'):
        return '创业板'
    if prefix_3 == '920' or code[0] == '8':
        return '北交所'
    return '其他'


def build_listed_board_sql_case(col_expr: str = "q.code") -> str:
    """生成 SQL CASE 表达式，用于在查询中计算 listed_board 列。

    Args:
        col_expr: 股票代码列的 SQL 表达式，默认 "q.code"

    Returns:
        完整的 SQL CASE WHEN ... END 表达式
    """
    return f"""
        CASE
            WHEN {col_expr} LIKE '60%' THEN '上海主板'
            WHEN {col_expr} LIKE '000%' OR {col_expr} LIKE '001%' OR {col_expr} LIKE '002%' OR {col_expr} LIKE '003%' THEN '深圳主板'
            WHEN {col_expr} LIKE '300%' OR {col_expr} LIKE '301%' OR {col_expr} LIKE '302%' THEN '创业板'
            WHEN {col_expr} LIKE '688%' OR {col_expr} LIKE '689%' THEN '科创板'
            WHEN {col_expr} LIKE '92%' OR {col_expr} LIKE '8%' OR {col_expr} LIKE '43%' THEN '北交所'
            ELSE '其他'
        END
    """


def build_exclude_bse_filter(table_alias: str = "sb") -> List[str]:
    """构建排除北交所和退市股票的 SQL WHERE 条件。

    Args:
        table_alias: 表别名，默认 "sb"

    Returns:
        WHERE 条件字符串列表
    """
    return [
        f"{table_alias}.code NOT LIKE '8%'",
        f"{table_alias}.code NOT LIKE '43%'",
        f"{table_alias}.code NOT LIKE '92%'",
        f"{table_alias}.delist_date IS NULL",
    ]