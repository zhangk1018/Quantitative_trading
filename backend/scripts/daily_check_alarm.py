#!/usr/bin/env python3
"""
晨检告警脚本 - 当 daily_check.py 退出码为 2 时触发告警

功能：
1. 解析 daily_check.py 的 JSON 报告
2. 提取失败项和异常项详细信息
3. 输出结构化告警信息（终端 + 可选日志）
4. 提供恢复建议

使用方式：
    # 链式调用，自动检测退出码
    venv/bin/python backend/scripts/daily_check.py --quiet --output /tmp/report.json && \
    venv/bin/python backend/scripts/daily_check_alarm.py /tmp/report.json

    # 或直接检查报告
    venv/bin/python backend/scripts/daily_check_alarm.py /tmp/report.json

退出码：
    0 - 无告警
    1 - 有警告项
    2 - 有失败项（触发告警）
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime


def load_report(report_path: str) -> dict:
    """加载 JSON 报告"""
    if not os.path.isfile(report_path):
        print(f"❌ 报告文件不存在: {report_path}")
        sys.exit(2)
    try:
        with open(report_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"❌ 报告格式错误: {e}")
        sys.exit(2)


def check_report(report: dict) -> int:
    """检查报告，输出告警信息"""
    summary = report.get("summary", {})

    # 获取失败项和异常项
    failed_items = [r for r in report.get("results", []) if r["status"] in ("fail", "error")]
    warn_items = [r for r in report.get("results", []) if r["status"] == "warn"]

    # 告警级别
    has_fail = len(failed_items) > 0
    has_warn = len(warn_items) > 0

    # 输出告警信息
    alarm_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{'=' * 60}")
    print(f"  晨检告警 - {alarm_time}")
    print(f"{'=' * 60}")

    if has_fail:
        print(f"\n  🚨 级别: FAIL (需立即处理)")
        print(f"\n  {'=' * 50}")
        print(f"  失败/异常项 ({len(failed_items)} 个)")
        print(f"  {'=' * 50}")
        for item in failed_items:
            print(f"    [{item['item_id']}] {item['message']}")
            details = item.get("details", {})
            if details:
                print(f"    详情: {json.dumps(details, ensure_ascii=False, default=str)[:200]}")

    if has_warn:
        print(f"\n  ⚠️ 级别: WARN (需关注)")
        print(f"\n  {'=' * 50}")
        print(f"  警告项 ({len(warn_items)} 个)")
        print(f"  {'=' * 50}")
        for item in warn_items:
            print(f"    [{item['item_id']}] {item['message']}")

    # 恢复建议
    if has_fail:
        print(f"\n  {'=' * 50}")
        print(f"  恢复建议")
        print(f"  {'=' * 50}")
        for item in failed_items:
            item_id = item["item_id"]
            if item_id == "postgresql_running":
                print(f"    [{item_id}] 尝试重启 PostgreSQL: pg_ctl -D /usr/local/var/postgresql@18 start")
            elif item_id == "database_connectivity":
                print(f"    [{item_id}] 检查数据库连接参数和网络")
            elif item_id == "stock_quotes_freshness":
                print(f"    [{item_id}] 若为工作日数据缺失，执行增量导入")
            elif item_id == "snapshot_sync":
                print(f"    [{item_id}] 执行宽表同步: daily_snapshot_sync.py --latest")
            elif item_id == "task_run_log":
                print(f"    [{item_id}] 查看 task_run_log 表定位失败任务原因")
            else:
                print(f"    [{item_id}] 需人工排查")

    # 汇总
    print(f"\n{'-' * 50}")
    print(f"  PASS: {summary.get('pass', 0)}  WARN: {summary.get('warn', 0)}  "
          f"FAIL: {summary.get('fail', 0)}  ERROR: {summary.get('error', 0)}")
    print(f"  {'=' * 50}")

    return 2 if has_fail else (1 if has_warn else 0)


def main() -> int:
    if len(sys.argv) < 2:
        print(f"用法: {sys.argv[0]} <report.json>")
        return 1

    report_path = sys.argv[1]
    report = load_report(report_path)
    return check_report(report)


if __name__ == "__main__":
    sys.exit(main())