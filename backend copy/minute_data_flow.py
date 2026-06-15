#!/usr/bin/env python3
"""
分钟线数据导入 Prefect 流程

功能：
- 定义数据导入工作流
- 支持失败重试
- 集成告警通知
- 可视化 DAG

依赖安装：
    pip install prefect

注册流程：
    prefect deployment build flows/minute_data_flow.py:minute_data_import_flow -n "分钟线数据导入"
    prefect deployment apply minute_data_import_flow-deployment.yaml

运行方式：
    prefect deployment run "分钟线数据导入/minute_data_import_flow"
    或设置定时调度：
    prefect deployment set-schedule "分钟线数据导入/minute_data_import_flow" --cron "0 18 * * *"
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '..'))

from prefect import flow, task, get_run_logger
from prefect.blocks.notifications import SlackWebhook
from prefect.flow_runners import SubprocessFlowRunner
from prefect.deployments import Deployment
from prefect.orion.schemas.schedules import CronSchedule

import subprocess
from datetime import datetime


@task(retries=2, retry_delay_seconds=60)
def import_minute_data(code: str = None, incremental: bool = True, end_date: str = None):
    """执行分钟线数据导入"""
    logger = get_run_logger()
    
    cmd = [
        sys.executable,
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'scripts', 'import_minute_data.py')
    ]
    
    if code:
        cmd.append(f'--code={code}')
    
    if incremental:
        cmd.append('--incremental')
    
    if end_date:
        cmd.append(f'--end={end_date}')
    
    logger.info(f"执行命令: {' '.join(cmd)}")
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        logger.error(f"导入失败: {result.stderr}")
        raise Exception(f"导入失败: {result.stderr}")
    
    logger.info(f"导入成功: {result.stdout}")
    return result.stdout


@task(retries=1, retry_delay_seconds=30)
def validate_data(code: str = None):
    """验证导入数据质量"""
    logger = get_run_logger()
    
    cmd = [
        sys.executable,
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'scripts', 'validate_minute_data.py')
    ]
    
    if code:
        cmd.append(f'--code={code}')
    
    cmd.append('--all-cycles')
    
    logger.info(f"执行数据验证: {' '.join(cmd)}")
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        logger.warning(f"数据验证发现问题: {result.stderr}")
        # 验证警告不中断流程，但记录日志
    
    logger.info(f"验证完成: {result.stdout}")
    return result.stdout


@task
def send_slack_notification(message: str, status: str = "success"):
    """发送 Slack 通知"""
    try:
        slack_webhook = SlackWebhook.load("quant-trading-alerts")
        color = "#4CAF50" if status == "success" else "#f44336"
        slack_webhook.notify(
            message=f"**分钟线数据导入** - {status}\n\n{message}",
            attachments=[{"color": color}]
        )
    except Exception as e:
        logger = get_run_logger()
        logger.warning(f"发送 Slack 通知失败: {e}")


@flow(name="minute_data_import_flow", flow_runner=SubprocessFlowRunner())
def minute_data_import_flow(
    code: str = None,
    incremental: bool = True,
    end_date: str = None,
    notify: bool = True
):
    """
    分钟线数据导入主流程
    
    Args:
        code: 股票代码，为空则导入所有股票
        incremental: 是否增量导入
        end_date: 结束日期，为空则使用昨天
        notify: 是否发送 Slack 通知
    """
    logger = get_run_logger()
    start_time = datetime.now()
    
    logger.info(f"开始分钟线数据导入流程 - 代码: {code}, 增量: {incremental}, 日期: {end_date}")
    
    try:
        # 执行数据导入
        import_result = import_minute_data(code, incremental, end_date)
        
        # 执行数据验证
        validate_data(code)
        
        elapsed_time = (datetime.now() - start_time).total_seconds()
        
        message = f"""
✅ 数据导入成功！
- 股票代码: {code or '全部'}
- 模式: {'增量' if incremental else '全量'}
- 日期: {end_date or '自动'}
- 耗时: {elapsed_time:.2f}秒
        """
        
        logger.info(message)
        
        if notify:
            send_slack_notification(message, "success")
        
        return {"status": "success", "message": message}
        
    except Exception as e:
        elapsed_time = (datetime.now() - start_time).total_seconds()
        
        message = f"""
❌ 数据导入失败！
- 股票代码: {code or '全部'}
- 模式: {'增量' if incremental else '全量'}
- 日期: {end_date or '自动'}
- 耗时: {elapsed_time:.2f}秒
- 错误: {str(e)}
        """
        
        logger.error(message)
        
        if notify:
            send_slack_notification(message, "failed")
        
        raise


# ==========================================
# 部署配置示例
# ==========================================
if __name__ == "__main__":
    # 创建每日增量导入部署
    daily_deployment = Deployment.build_from_flow(
        flow=minute_data_import_flow,
        name="daily_incremental_import",
        schedule=CronSchedule(cron="0 18 * * *", timezone="Asia/Shanghai"),
        parameters={
            "incremental": True,
            "notify": True
        },
        tags=["minute_data", "daily", "incremental"]
    )
    
    # 创建每周全量验证部署
    weekly_deployment = Deployment.build_from_flow(
        flow=minute_data_import_flow,
        name="weekly_full_validation",
        schedule=CronSchedule(cron="0 2 * * 1", timezone="Asia/Shanghai"),
        parameters={
            "incremental": False,
            "notify": True
        },
        tags=["minute_data", "weekly", "validation"]
    )
    
    print("部署配置已创建，请运行以下命令注册：")
    print("prefect deployment apply flows/minute_data_flow-daily_incremental_import.yaml")
    print("prefect deployment apply flows/minute_data_flow-weekly_full_validation.yaml")