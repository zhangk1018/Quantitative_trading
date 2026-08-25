"""
pdca 路由模块
由 main.py 注册：from .router import pdca
"""
from fastapi import APIRouter

from . import records, snapshots, diaries, config, import_export, stocks, cycles, brokers, exit_slips, plans, securities, check_report, act_record, behavior_log, experience

router = APIRouter(prefix="/api/pdca", tags=["PDCA交易自律系统"])

# 注册子路由
router.include_router(records.router, prefix="/records", tags=["交易台账"])
router.include_router(exit_slips.router, prefix="", tags=["退出子单"])
router.include_router(snapshots.router, prefix="/snapshots", tags=["资金快照"])
router.include_router(diaries.router, prefix="/diaries", tags=["交易日记"])
router.include_router(config.router, prefix="/config", tags=["系统配置"])
router.include_router(import_export.router, prefix="", tags=["导入导出"])
router.include_router(stocks.router, prefix="/stocks", tags=["股票搜索"])
router.include_router(cycles.router, prefix="/cycles", tags=["PDCA周期"])
router.include_router(brokers.router, prefix="/import/brokers", tags=["券商适配器"])
router.include_router(plans.router, prefix="/plans", tags=["交易计划"])
router.include_router(securities.router, prefix="/securities", tags=["ABC分类"])
router.include_router(check_report.router, prefix="", tags=["复盘报告"])
router.include_router(act_record.router, prefix="", tags=["迭代处理记录"])
router.include_router(behavior_log.router, prefix="", tags=["行为日志"])
router.include_router(experience.router, prefix="", tags=["经验知识库"])