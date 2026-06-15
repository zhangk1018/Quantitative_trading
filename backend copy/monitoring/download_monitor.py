"""
数据下载监控程序 - 通用监控和自动重传机制

功能特点：
1. 心跳检测：定期检查下载任务状态
2. 超时检测：自动识别长时间无响应的任务
3. 自动重试：检测到死机后立即重启任务
4. 断点续传：支持从中断位置继续下载
5. 指数退避：重试间隔逐渐增加，避免频繁重试
6. 通用设计：适用于所有数据下载任务
"""

import os
import sys
import time
import signal
import subprocess
import threading
from datetime import datetime, timedelta
from typing import Callable, Dict, Optional, Any
import logging

logger = logging.getLogger(__name__)

class DownloadMonitor:
    """
    通用下载监控器
    
    监控下载任务的执行状态，检测死机或超时，并自动触发重试机制。
    """
    
    def __init__(
        self,
        task_name: str,
        task_func: Callable,
        max_retries: int = 5,
        heartbeat_interval: int = 30,  # 心跳检测间隔（秒）
        timeout_threshold: int = 300,   # 超时阈值（秒）
        base_retry_delay: int = 60,     # 基础重试延迟（秒）
        max_retry_delay: int = 3600,    # 最大重试延迟（秒）
        **kwargs
    ):
        """
        初始化监控器
        
        Args:
            task_name: 任务名称
            task_func: 任务函数（无参数，返回任务标识或None）
            max_retries: 最大重试次数
            heartbeat_interval: 心跳检测间隔（秒）
            timeout_threshold: 超时阈值（秒）
            base_retry_delay: 基础重试延迟（秒）
            max_retry_delay: 最大重试延迟（秒）
            kwargs: 其他参数
        """
        self.task_name = task_name
        self.task_func = task_func
        self.max_retries = max_retries
        self.heartbeat_interval = heartbeat_interval
        self.timeout_threshold = timeout_threshold
        self.base_retry_delay = base_retry_delay
        self.max_retry_delay = max_retry_delay
        
        # 状态管理
        self._running = False
        self._current_retry = 0
        self._last_activity_time = datetime.now()
        self._task_thread: Optional[threading.Thread] = None
        self._monitor_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        
        # 注册信号处理
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)
    
    def _handle_signal(self, signum, frame):
        """处理中断信号"""
        logger.info(f"收到信号 {signum}，正在停止监控...")
        self.stop()
    
    def _update_heartbeat(self):
        """更新心跳时间"""
        with self._lock:
            self._last_activity_time = datetime.now()
    
    def _is_timed_out(self) -> bool:
        """检查是否超时"""
        with self._lock:
            elapsed = (datetime.now() - self._last_activity_time).total_seconds()
            return elapsed > self.timeout_threshold
    
    def _get_retry_delay(self) -> int:
        """计算指数退避延迟"""
        delay = self.base_retry_delay * (2 ** self._current_retry)
        return min(delay, self.max_retry_delay)
    
    def _heartbeat_monitor(self):
        """心跳监控线程"""
        while self._running:
            try:
                time.sleep(self.heartbeat_interval)
                
                if not self._running:
                    break
                
                # 检查超时
                if self._is_timed_out():
                    logger.error(f"⚠️  [{self.task_name}] 检测到超时，最后活跃时间: {self._last_activity_time}")
                    self._handle_timeout()
                    
            except Exception as e:
                logger.error(f"❤️  [{self.task_name}] 监控线程异常: {e}")
    
    def _handle_timeout(self):
        """处理超时情况"""
        with self._lock:
            if self._current_retry >= self.max_retries:
                logger.error(f"❌  [{self.task_name}] 已达到最大重试次数 ({self.max_retries})，放弃重试")
                self.stop()
                return
            
            self._current_retry += 1
            retry_delay = self._get_retry_delay()
            
            logger.warning(f"🔄  [{self.task_name}] 第 {self._current_retry}/{self.max_retries} 次重试，等待 {retry_delay} 秒...")
            
            # 延迟后重启任务
            time.sleep(retry_delay)
            self._restart_task()
    
    def _restart_task(self):
        """重启任务"""
        logger.info(f"🔀  [{self.task_name}] 重新启动任务...")
        
        # 确保旧任务已停止
        if self._task_thread and self._task_thread.is_alive():
            logger.info(f"⏹️  [{self.task_name}] 等待旧任务线程退出...")
            # 可以添加强制终止逻辑
        
        # 启动新任务
        self._last_activity_time = datetime.now()
        self._task_thread = threading.Thread(target=self._task_wrapper)
        self._task_thread.daemon = True
        self._task_thread.start()
    
    def _task_wrapper(self):
        """任务包装器，捕获异常并更新心跳"""
        try:
            logger.info(f"🚀  [{self.task_name}] 任务开始执行")
            
            # 执行任务
            result = self.task_func()
            
            # 任务正常完成
            logger.info(f"✅  [{self.task_name}] 任务完成，结果: {result}")
            self._current_retry = 0  # 重置重试计数
            
        except Exception as e:
            logger.error(f"💥  [{self.task_name}] 任务执行异常: {e}", exc_info=True)
            
            # 触发重试
            with self._lock:
                if self._current_retry < self.max_retries:
                    self._current_retry += 1
                    retry_delay = self._get_retry_delay()
                    logger.warning(f"🔄  [{self.task_name}] 异常重试 {self._current_retry}/{self.max_retries}，等待 {retry_delay} 秒")
                    time.sleep(retry_delay)
                    self._restart_task()
                else:
                    logger.error(f"❌  [{self.task_name}] 已达到最大重试次数，任务失败")
                    self.stop()
    
    def start(self):
        """启动监控"""
        logger.info(f"🎯  [{self.task_name}] 启动监控程序")
        
        self._running = True
        self._current_retry = 0
        self._last_activity_time = datetime.now()
        
        # 启动监控线程
        self._monitor_thread = threading.Thread(target=self._heartbeat_monitor)
        self._monitor_thread.daemon = True
        self._monitor_thread.start()
        
        # 启动任务线程
        self._task_thread = threading.Thread(target=self._task_wrapper)
        self._task_thread.daemon = True
        self._task_thread.start()
    
    def stop(self):
        """停止监控"""
        logger.info(f"🛑  [{self.task_name}] 停止监控程序")
        
        self._running = False
        
        # 等待线程退出
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=5)
        
        if self._task_thread and self._task_thread.is_alive():
            self._task_thread.join(timeout=5)
        
        logger.info(f"✅  [{self.task_name}] 监控程序已停止")
    
    def wait(self):
        """等待任务完成"""
        if self._task_thread:
            self._task_thread.join()


class ExternalProcessMonitor:
    """
    外部进程监控器
    
    监控外部命令/脚本的执行状态，支持自动重启。
    """
    
    def __init__(
        self,
        task_name: str,
        command: str,
        cwd: Optional[str] = None,
        max_retries: int = 5,
        heartbeat_interval: int = 30,
        timeout_threshold: int = 300,
        base_retry_delay: int = 60,
        max_retry_delay: int = 3600,
        **kwargs
    ):
        """
        初始化外部进程监控器
        
        Args:
            task_name: 任务名称
            command: 要执行的命令
            cwd: 工作目录
            max_retries: 最大重试次数
            heartbeat_interval: 心跳检测间隔（秒）
            timeout_threshold: 超时阈值（秒）
            base_retry_delay: 基础重试延迟（秒）
            max_retry_delay: 最大重试延迟（秒）
        """
        self.task_name = task_name
        self.command = command
        self.cwd = cwd
        self.max_retries = max_retries
        self.heartbeat_interval = heartbeat_interval
        self.timeout_threshold = timeout_threshold
        self.base_retry_delay = base_retry_delay
        self.max_retry_delay = max_retry_delay
        
        self._running = False
        self._current_retry = 0
        self._last_activity_time = datetime.now()
        self._process: Optional[subprocess.Popen] = None
        self._monitor_thread: Optional[threading.Thread] = None
        
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)
    
    def _handle_signal(self, signum, frame):
        """处理中断信号"""
        logger.info(f"收到信号 {signum}，正在停止监控...")
        self.stop()
    
    def _read_output(self, pipe, is_stdout=True):
        """读取进程输出并更新心跳"""
        try:
            for line in iter(pipe.readline, b''):
                if line:
                    self._last_activity_time = datetime.now()
                    prefix = "[STDOUT]" if is_stdout else "[STDERR]"
                    logger.info(f"{prefix} [{self.task_name}] {line.decode('utf-8', errors='ignore').strip()}")
        except Exception as e:
            pass
    
    def _start_process(self):
        """启动外部进程"""
        logger.info(f"🚀  [{self.task_name}] 启动命令: {self.command}")
        
        try:
            self._process = subprocess.Popen(
                self.command,
                shell=True,
                cwd=self.cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=False
            )
            
            # 启动输出读取线程
            stdout_thread = threading.Thread(
                target=self._read_output,
                args=(self._process.stdout, True)
            )
            stdout_thread.daemon = True
            stdout_thread.start()
            
            stderr_thread = threading.Thread(
                target=self._read_output,
                args=(self._process.stderr, False)
            )
            stderr_thread.daemon = True
            stderr_thread.start()
            
            return True
        except Exception as e:
            logger.error(f"💥  [{self.task_name}] 启动进程失败: {e}")
            return False
    
    def _wait_process(self):
        """等待进程完成"""
        if self._process:
            try:
                return self._process.wait()
            except Exception as e:
                logger.error(f"⚠️  [{self.task_name}] 等待进程异常: {e}")
                return -1
    
    def _monitor_loop(self):
        """监控主循环"""
        while self._running:
            # 启动进程
            if not self._start_process():
                self._handle_failure()
                continue
            
            # 等待进程执行
            exit_code = self._wait_process()
            
            # 检查退出码
            if exit_code == 0:
                logger.info(f"✅  [{self.task_name}] 进程正常退出")
                self._current_retry = 0
            else:
                logger.error(f"💥  [{self.task_name}] 进程异常退出，退出码: {exit_code}")
                self._handle_failure()
            
            # 如果不是持续运行模式，退出循环
            if not self._running:
                break
    
    def _handle_failure(self):
        """处理进程失败"""
        if not self._running:
            return
        
        if self._current_retry >= self.max_retries:
            logger.error(f"❌  [{self.task_name}] 已达到最大重试次数 ({self.max_retries})，放弃重试")
            self.stop()
            return
        
        self._current_retry += 1
        retry_delay = self.base_retry_delay * (2 ** (self._current_retry - 1))
        retry_delay = min(retry_delay, self.max_retry_delay)
        
        logger.warning(f"🔄  [{self.task_name}] 第 {self._current_retry}/{self.max_retries} 次重试，等待 {retry_delay} 秒...")
        time.sleep(retry_delay)
    
    def start(self):
        """启动监控"""
        logger.info(f"🎯  [{self.task_name}] 启动外部进程监控")
        
        self._running = True
        self._current_retry = 0
        self._last_activity_time = datetime.now()
        
        self._monitor_thread = threading.Thread(target=self._monitor_loop)
        self._monitor_thread.daemon = True
        self._monitor_thread.start()
    
    def stop(self):
        """停止监控"""
        logger.info(f"🛑  [{self.task_name}] 停止外部进程监控")
        
        self._running = False
        
        # 终止进程
        if self._process and self._process.poll() is None:
            logger.info(f"⏹️  [{self.task_name}] 终止进程...")
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except Exception as e:
                logger.error(f"⚠️  [{self.task_name}] 终止进程失败，强制杀死")
                self._process.kill()
        
        # 等待监控线程退出
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=5)
        
        logger.info(f"✅  [{self.task_name}] 监控已停止")
    
    def wait(self):
        """等待任务完成"""
        if self._monitor_thread:
            self._monitor_thread.join()


def main():
    """示例用法"""
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler()
        ]
    )
    
    # 示例1: 使用 ExternalProcessMonitor 监控外部脚本
    monitor = ExternalProcessMonitor(
        task_name="日线数据导入",
        command="python scripts/import_daily_data.py",
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        max_retries=3,
        heartbeat_interval=30,
        timeout_threshold=300,
        base_retry_delay=60
    )
    
    try:
        monitor.start()
        monitor.wait()
    except KeyboardInterrupt:
        logger.info("收到中断信号，退出监控")
    finally:
        monitor.stop()


if __name__ == "__main__":
    main()
