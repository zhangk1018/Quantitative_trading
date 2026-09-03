#!/usr/bin/env python3
"""
行情修正后级联重算编排（协作单 30.0 V6 / ④）

当港/美股行情被修正（补数/改错价/复权因子变更）后，需按 market 从底向上级联重算，
各下游依赖本脚本还原最新一致数据：
    compute_indicators_daily（指标）→ pattern_precompute（K线形态）→
    signal_precompute（信号）→ daily_snapshot_sync（宽表）→ export_parquet（parquet）

复用 V4 已加 `--market` 的 5 个脚本，按序串行执行，任一步失败即中止并返回非零退出码。

用法：
    ./venv/bin/python backend/monitoring/recompute_market.py --market hk
    ./venv/bin/python backend/monitoring/recompute_market.py --market us --steps indicators,pattern,signal
    ./venv/bin/python backend/monitoring/recompute_market.py --market cn --signal-force-full
"""
import os
import sys
import argparse
import subprocess
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import setup_logger  # noqa: E402

logger = setup_logger('recompute_market')

BASE_DIR = Path(__file__).resolve().parents[2]  # 项目根
BACKEND_DIR = BASE_DIR / 'backend'
PYTHON = str(Path(sys.executable))  # 复用当前 venv 解释器，保证跑在正确环境


# 步骤 -> (脚本相对 backend 路径, 追加参数列表)
STEPS = {
    'indicators': ('clean/etl/compute_indicators_daily.py', ['--market']),
    'pattern': ('clean/etl/pattern_precompute.py', ['--market', '--latest']),
    'signal': ('clean/etl/signal_precompute.py', ['--market']),
    'snapshot': ('collector/etl/daily_snapshot_sync.py', ['--market', '--latest']),
    'parquet': ('clean/enrich/export_parquet.py', ['--market']),
}
ORDER = ['indicators', 'pattern', 'signal', 'snapshot', 'parquet']


def _run_step(step: str, market: str, signal_force_full: bool) -> bool:
    """执行单个步骤，返回是否成功。"""
    rel_path, base_args = STEPS[step]
    script = BACKEND_DIR / rel_path
    args: List[str] = [PYTHON, str(script)] + base_args + [market]
    if step == 'signal' and signal_force_full:
        args.append('--force-full')
    logger.info(f"▶️ 步骤 [{step}] 开始: {' '.join(args)}")
    try:
        proc = subprocess.run(args, capture_output=True, text=True, cwd=str(BASE_DIR))
    except OSError as e:
        logger.error(f"❌ 步骤 [{step}] 启动失败: {e}")
        return False
    if proc.stdout.strip():
        logger.info(f"  [{step}] stdout:\n{proc.stdout.strip()}")
    if proc.stderr.strip():
        logger.warning(f"  [{step}] stderr:\n{proc.stderr.strip()}")
    if proc.returncode != 0:
        logger.error(f"❌ 步骤 [{step}] 失败（exit={proc.returncode}）")
        return False
    logger.info(f"✅ 步骤 [{step}] 完成")
    return True


def main() -> None:
    """主函数：按依赖顺序执行选定步骤。"""
    parser = argparse.ArgumentParser(description='行情修正后按市场级联重算指标→形态→信号→宽表→parquet')
    parser.add_argument('--market', required=True, choices=['cn', 'hk', 'us'], help='重算的市场')
    parser.add_argument('--steps', default=','.join(ORDER),
                        help='要执行的步骤(用逗号分隔)：indicators,pattern,signal,snapshot,parquet')
    parser.add_argument('--signal-force-full', action='store_true', help='signal 步骤强制全量重算(--force-full)')
    args = parser.parse_args()

    steps = [s.strip() for s in args.steps.split(',') if s.strip()]
    unknown = [s for s in steps if s not in STEPS]
    if unknown:
        logger.error(f"❌ 未知步骤: {unknown}（可选 {list(STEPS)}）")
        sys.exit(2)

    logger.info("=" * 70)
    logger.info(f"🚀 级联重算开始 market={args.market}，步骤={steps}")
    for step in ORDER:
        if step not in steps:
            continue
        if not _run_step(step, args.market, args.signal_force_full):
            logger.error(f"🛑 级联重算中止于步骤 [{step}]（market={args.market}）")
            sys.exit(1)
    logger.info(f"✅ 级联重算全部完成（market={args.market}）")
    logger.info("=" * 70)


if __name__ == '__main__':
    main()