# -*- coding: utf-8 -*-
"""
测试 daily_job_runner.py 核心逻辑

覆盖范围：
- 常量定义
- 工具函数 (_parse_task_result, is_retryable_error, generate_batch_id)
- 数据库查询 (get_latest_trade_date, get_task_db_status, get_last_batch_status)
- 僵尸清理 (cleanup_zombie_task, is_zombie_task)
- 任务执行 (run_task)
- 任务日志 (TaskLogger.log_start, log_end)
- 任务链执行 (run_task_chain running 处理)
- 文件锁 (FileLock.acquire, release)
"""

import json
import os
import subprocess
import sys
import pytest
from unittest.mock import MagicMock, patch, call
from datetime import datetime, date, timedelta


# ===================== 模块加载 Fixture =====================

def _load_module():
    """使用相对路径加载 daily_job_runner 模块"""
    test_dir = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.dirname(test_dir)
    module_path = os.path.join(backend_dir, "cron", "daily_job_runner.py")
    import importlib.util
    spec = importlib.util.spec_from_file_location("daily_job_runner", module_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="session")
def mod():
    """会话级 fixture，各测试类共享同一模块实例"""
    return _load_module()


# ===================== Fixtures =====================

@pytest.fixture
def mock_engine():
    """Mock SQLAlchemy Engine，默认返回空结果"""
    engine = MagicMock()
    conn = MagicMock()
    result = MagicMock()
    engine.connect.return_value.__enter__.return_value = conn
    conn.execute.return_value = result
    result.scalar.return_value = None
    result.fetchone.return_value = None
    result.rowcount = 0
    return engine


@pytest.fixture
def mock_conn(mock_engine):
    """返回 mock_engine 的 connection 对象"""
    return mock_engine.connect.return_value.__enter__.return_value


# ===================== 常量测试 =====================

class TestConstants:
    """验证 Stage 常量定义正确且与 DB 约束一致"""

    def test_stage_constants(self, mod):
        assert mod.STAGE_PRE_IMPORT == 1
        assert mod.STAGE_IMPORT == 2
        assert mod.PIPELINE_STAGE == 0

    def test_stage_definitions_have_expected_tasks(self, mod):
        stage1_names = [t["name"] for t in mod.STAGE1_TASKS]
        stage2_names = [t["name"] for t in mod.STAGE2_TASKS]

        assert "pipeline_health_check" in stage1_names
        assert "stock_list_sync" in stage1_names
        assert len(stage1_names) == 2

        assert "daily_import" in stage2_names
        assert "adj_factor_sync" in stage2_names
        assert "daily_basic_sync" in stage2_names
        assert "indicators_compute" in stage2_names
        assert "signal_precompute" in stage2_names
        assert "daily_sync" in stage2_names
        assert "parquet_export" in stage2_names
        assert len(stage2_names) == 7


# ===================== _parse_task_result 测试 =====================

class TestParseTaskResult:
    """解析子脚本 TASK_RESULT:JSON 输出"""

    def test_parse_normal(self, mod):
        stdout = "普通日志行\nTASK_RESULT:{\"rows_affected\": 5194, \"extra_metrics\": {\"duration_s\": 45}}\n结束"
        rows, extra = mod._parse_task_result(stdout)
        assert rows == 5194
        assert extra == {"duration_s": 45}

    def test_parse_no_result(self, mod):
        rows, extra = mod._parse_task_result("普通日志，无标记")
        assert rows is None
        assert extra is None

    def test_parse_malformed_json(self, mod):
        rows, extra = mod._parse_task_result("TASK_RESULT:{bad json}")
        assert rows is None
        assert extra is None

    def test_parse_empty(self, mod):
        rows, extra = mod._parse_task_result("")
        assert rows is None
        assert extra is None


# ===================== is_retryable_error 测试 =====================

class TestIsRetryableError:
    """判断错误是否可重试"""

    def test_exit_code_zero(self, mod):
        assert mod.is_retryable_error(0, "") is True

    def test_fatal_keyword_returns_false(self, mod):
        for kw in ["SyntaxError", "ImportError", "AttributeError", "NameError", "TypeError"]:
            assert mod.is_retryable_error(1, f"Traceback: {kw}: xxx") is False, f"{kw} 应被识别为不可重试"

    def test_network_error_is_retryable(self, mod):
        assert mod.is_retryable_error(1, "ConnectionError: timeout") is True
        assert mod.is_retryable_error(1, "requests.exceptions.ConnectionError") is True


# ===================== generate_batch_id 测试 =====================

class TestGenerateBatchId:
    """批次 ID 格式验证"""

    def test_format(self, mod):
        bid = mod.generate_batch_id()
        today = date.today().strftime('%Y%m%d')
        assert bid.startswith(today)
        assert len(bid) == len(today) + 1 + 8


# ===================== get_latest_trade_date 测试 =====================

class TestGetLatestTradeDate:
    """获取最近交易日"""

    def test_from_trade_calendar(self, mod, mock_engine):
        """优先从 trade_calendar 获取"""
        mock_engine.connect.return_value.__enter__.return_value.execute.return_value.scalar.return_value = date(2026, 7, 9)
        dt = mod.get_latest_trade_date(mock_engine)
        assert dt == "2026-07-09"

    def test_fallback_to_stock_quotes(self, mod, mock_engine, mock_conn):
        """trade_calendar 无数据时回退到 stock_quotes"""
        mock_conn.execute.side_effect = [
            MagicMock(scalar=lambda: None),
            MagicMock(scalar=lambda: date(2026, 7, 8)),
        ]
        dt = mod.get_latest_trade_date(mock_engine)
        assert dt == "2026-07-08"

    def test_fallback_to_today(self, mod, mock_engine, mock_conn):
        """全部无数据时回退到当天"""
        mock_conn.execute.side_effect = [
            MagicMock(scalar=lambda: None),
            MagicMock(scalar=lambda: None),
        ]
        dt = mod.get_latest_trade_date(mock_engine)
        assert dt == datetime.now().strftime("%Y-%m-%d")


# ===================== 数据库状态查询测试 =====================

class TestGetTaskDbStatus:
    """查询单个任务状态"""

    def test_status_success(self, mod, mock_engine):
        mock_engine.connect.return_value.__enter__.return_value.execute.return_value.scalar.return_value = "success"
        assert mod.get_task_db_status(mock_engine, "2026-07-09", "daily_import", 2) == "success"

    def test_status_failed(self, mod, mock_engine):
        mock_engine.connect.return_value.__enter__.return_value.execute.return_value.scalar.return_value = "failed"
        assert mod.get_task_db_status(mock_engine, "2026-07-09", "daily_import", 2) == "failed"

    def test_status_running(self, mod, mock_engine):
        mock_engine.connect.return_value.__enter__.return_value.execute.return_value.scalar.return_value = "running"
        assert mod.get_task_db_status(mock_engine, "2026-07-09", "daily_import", 2) == "running"

    def test_status_no_record_returns_pending(self, mod, mock_engine):
        mock_engine.connect.return_value.__enter__.return_value.execute.return_value.scalar.return_value = None
        assert mod.get_task_db_status(mock_engine, "2026-07-09", "daily_import", 2) == "pending"


class TestGetLastBatchStatus:
    """查询整体批次状态"""

    def test_all_success(self, mod, mock_engine):
        tasks = [{"name": "task_a"}, {"name": "task_b"}]
        row = (2, 2, 0)
        mock_engine.connect.return_value.__enter__.return_value.execute.return_value.fetchone.return_value = row
        success_cnt, total, has_bad = mod.get_last_batch_status(mock_engine, "2026-07-09", tasks, 1)
        assert success_cnt == 2
        assert total == 2
        assert has_bad is False

    def test_mixed_status(self, mod, mock_engine):
        tasks = [{"name": "task_a"}, {"name": "task_b"}]
        row = (2, 1, 1)
        mock_engine.connect.return_value.__enter__.return_value.execute.return_value.fetchone.return_value = row
        success_cnt, total, has_bad = mod.get_last_batch_status(mock_engine, "2026-07-09", tasks, 1)
        assert success_cnt == 1
        assert has_bad is True

    def test_no_records(self, mod, mock_engine):
        tasks = [{"name": "task_a"}, {"name": "task_b"}]
        mock_engine.connect.return_value.__enter__.return_value.execute.return_value.fetchone.return_value = None
        success_cnt, total, has_bad = mod.get_last_batch_status(mock_engine, "2026-07-09", tasks, 1)
        assert success_cnt == 0
        assert total == 2
        assert has_bad is False


# ===================== 僵尸清理测试 =====================

class TestIsZombieTask:
    """判断任务是否为僵尸进程"""

    def test_is_zombie(self, mod, mock_engine):
        """start_time 超过阈值判定为僵尸"""
        old_time = datetime.now() - timedelta(hours=3)
        mock_engine.connect.return_value.__enter__.return_value.execute.return_value.fetchone.return_value = (old_time,)
        assert mod.is_zombie_task(mock_engine, "2026-07-09", "daily_import", 2) is True

    def test_not_zombie(self, mod, mock_engine):
        """start_time 未超过阈值"""
        recent_time = datetime.now() - timedelta(minutes=30)
        mock_engine.connect.return_value.__enter__.return_value.execute.return_value.fetchone.return_value = (recent_time,)
        assert mod.is_zombie_task(mock_engine, "2026-07-09", "daily_import", 2) is False

    def test_no_running_record(self, mod, mock_engine):
        """无 running 记录时返回 False"""
        mock_engine.connect.return_value.__enter__.return_value.execute.return_value.fetchone.return_value = None
        assert mod.is_zombie_task(mock_engine, "2026-07-09", "daily_import", 2) is False


class TestCleanupZombieTask:
    """清理僵尸任务记录"""

    def test_cleanup_updates_record(self, mod, mock_engine):
        mock_engine.connect.return_value.__enter__.return_value.execute.return_value.rowcount = 1
        assert mod.cleanup_zombie_task(mock_engine, "2026-07-09", "daily_import", 2) is True

    def test_cleanup_no_record(self, mod, mock_engine):
        mock_engine.connect.return_value.__enter__.return_value.execute.return_value.rowcount = 0
        assert mod.cleanup_zombie_task(mock_engine, "2026-07-09", "daily_import", 2) is False

    def test_cleanup_sets_status_failed(self, mod, mock_engine, mock_conn):
        """验证 cleanup 将 status 更新为 'failed'"""
        mock_conn.execute.return_value.rowcount = 1
        mod.cleanup_zombie_task(mock_engine, "2026-07-09", "daily_import", 2)
        sql, params = mock_conn.execute.call_args[0]
        assert "UPDATE task_run_log" in str(sql)
        # SQL 中 status 被硬编码为 'failed'，不在参数中
        assert "SET status = 'failed'" in str(sql)
        # 验证 error_message 包含"僵尸进程"关键词
        assert "僵尸进程" in params.get("err_msg", "")


# ===================== TaskLogger 测试 =====================

class TestTaskLogger:
    """任务日志记录"""

    @pytest.fixture
    def engine(self):
        eng = MagicMock()
        conn = MagicMock()
        result = MagicMock()
        # 抑制 get_latest_trade_date 的查询（返回 None 触发挥底到 today）
        conn.execute.return_value = result
        result.scalar.return_value = None
        eng.connect.return_value.__enter__.return_value = conn
        return eng

    def test_log_start_returns_id(self, mod, engine):
        """log_start 返回插入的 id"""
        conn = engine.connect.return_value.__enter__.return_value
        result = MagicMock()
        result.scalar.return_value = 42
        conn.execute.return_value = result

        logger = mod.TaskLogger(engine)
        log_id = logger.log_start("daily_import", 2)
        assert log_id == 42

    def test_log_start_passes_correct_stage(self, mod, engine):
        """验证 log_start 传入的 SQL 参数包含 stage=2"""
        conn = engine.connect.return_value.__enter__.return_value
        result = MagicMock()
        result.scalar.return_value = 42
        conn.execute.return_value = result

        logger = mod.TaskLogger(engine)
        logger.log_start("daily_import", 2)
        # 提取 execute 调用的参数
        sql, params = conn.execute.call_args[0]
        assert "INSERT INTO task_run_log" in str(sql)
        assert params.get("stage") == 2
        assert params.get("task_name") == "daily_import"

    def test_log_start_operational_error_returns_negative(self, mod, engine):
        """OperationalError 时返回 -1"""
        conn = engine.connect.return_value.__enter__.return_value
        conn.execute.side_effect = mod.OperationalError("mock", "mock", "mock")

        logger = mod.TaskLogger(engine)
        log_id = logger.log_start("daily_import", 2)
        assert log_id == -1

    def test_log_end_updates_record(self, mod, engine):
        """log_end 更新记录"""
        logger = mod.TaskLogger(engine)
        logger.log_end(42, "daily_import", 2, True, 0, None, 5194, {"duration_s": 45})
        conn = engine.connect.return_value.__enter__.return_value
        assert conn.execute.called

    def test_log_end_negative_id_skips_update(self, mod, engine):
        """log_id < 0 时跳过更新"""
        conn = engine.connect.return_value.__enter__.return_value
        logger = mod.TaskLogger(engine)
        init_call_count = conn.execute.call_count
        logger.log_end(-1, "daily_import", 2, True, 0, None)
        assert conn.execute.call_count == init_call_count

    def test_log_end_no_extra_metrics(self, mod, engine):
        """extra_metrics 为 None 时不应传入"""
        logger = mod.TaskLogger(engine)
        logger.log_end(42, "daily_import", 2, True, 0, None, 5194, None)
        conn = engine.connect.return_value.__enter__.return_value
        # 验证 params 中 extra_metrics 为 None
        sql, params = conn.execute.call_args[0]
        assert "extra_metrics" in str(sql)
        assert params.get("extra_metrics") is None

    def test_log_end_passes_extra_metrics_as_json(self, mod, engine):
        """extra_metrics 有值时序列化为 JSON"""
        logger = mod.TaskLogger(engine)
        logger.log_end(42, "daily_import", 2, True, 0, None, 5194, {"duration_s": 45})
        conn = engine.connect.return_value.__enter__.return_value
        sql, params = conn.execute.call_args[0]
        assert params.get("extra_metrics") == '{"duration_s": 45}'

    def test_log_end_passes_status_success(self, mod, engine):
        """success=True 时 status 应为 'success'"""
        logger = mod.TaskLogger(engine)
        logger.log_end(42, "daily_import", 2, True, 0, None)
        conn = engine.connect.return_value.__enter__.return_value
        sql, params = conn.execute.call_args[0]
        assert params.get("status") == "success"

    def test_log_end_passes_status_failed(self, mod, engine):
        """success=False 时 status 应为 'failed'"""
        logger = mod.TaskLogger(engine)
        logger.log_end(42, "daily_import", 2, False, 1, "error msg")
        conn = engine.connect.return_value.__enter__.return_value
        sql, params = conn.execute.call_args[0]
        assert params.get("status") == "failed"
        assert params.get("error_message") == "error msg"


# ===================== run_task 测试 =====================

class TestRunTask:
    """任务执行器"""

    @pytest.fixture
    def engine(self):
        eng = MagicMock()
        conn = MagicMock()
        eng.connect.return_value.__enter__.return_value = conn
        # 按调用顺序返回不同 scalar 值：
        # 1. get_latest_trade_date → 返回 date
        # 2. log_start → 返回 int (log_id)
        # 3. log_end → 无需返回值（UPDATE）
        results = [MagicMock(scalar=lambda: date(2026, 7, 9)),
                   MagicMock(scalar=lambda: 42),
                   MagicMock()]
        conn.execute.side_effect = results
        return eng

    @pytest.fixture
    def task(self):
        return {"name": "test_task", "script": "test.py", "args": []}

    def _patch_subprocess(self, mod, mock_subprocess):
        """设置 mock_subprocess 上的异常类，使 run_task 的 except 子句能正确匹配"""
        mock_subprocess.CalledProcessError = subprocess.CalledProcessError
        mock_subprocess.TimeoutExpired = subprocess.TimeoutExpired

    def test_run_task_success(self, mod, engine, task):
        """子进程返回 0 视为成功"""
        task_logger = mod.TaskLogger(engine)
        with patch.object(mod, 'subprocess') as mock_subprocess:
            self._patch_subprocess(mod, mock_subprocess)
            mock_subprocess.run.return_value = MagicMock(returncode=0, stdout="", stderr="")

            result = mod.run_task(task, task_logger, 1, engine)
            assert result is True

    def test_run_task_failure(self, mod, engine, task):
        """子进程返回非 0 视为失败"""
        task_logger = mod.TaskLogger(engine)
        with patch.object(mod, 'subprocess') as mock_subprocess:
            self._patch_subprocess(mod, mock_subprocess)
            mock_subprocess.run.return_value = MagicMock(returncode=1, stdout="", stderr="error")

            result = mod.run_task(task, task_logger, 1, engine)
            assert result is False

    def test_run_task_timeout(self, mod, engine, task):
        """子进程超时视为失败"""
        task_logger = mod.TaskLogger(engine)
        with patch.object(mod, 'subprocess') as mock_subprocess:
            self._patch_subprocess(mod, mock_subprocess)
            mock_subprocess.run.side_effect = subprocess.TimeoutExpired(cmd="test", timeout=3600)

            result = mod.run_task(task, task_logger, 1, engine)
            assert result is False

    def test_run_task_parses_result(self, mod, engine, task):
        """验证 run_task 解析 TASK_RESULT 并传入 log_end"""
        task_logger = mod.TaskLogger(engine)
        with patch.object(mod, 'subprocess') as mock_subprocess, \
             patch.object(mod, 'setup_task_logger') as mock_setup_logger:
            self._patch_subprocess(mod, mock_subprocess)
            mock_subprocess.run.return_value = MagicMock(
                returncode=0,
                stdout='TASK_RESULT:{"rows_affected": 100, "extra_metrics": {"metric": 1}}',
                stderr=""
            )
            mock_setup_logger.return_value = MagicMock()

            with patch.object(task_logger, 'log_end') as mock_log_end:
                result = mod.run_task(task, task_logger, 1, engine)
                assert result is True
                mock_log_end.assert_called_once()
                args, kwargs = mock_log_end.call_args
                # log_end(log_id, task_name, stage, success, exit_code, error_message, rows_affected, extra_metrics)
                assert args[6] == 100

    def test_run_task_non_retryable_error(self, mod, engine, task):
        """不可重试错误应记录错误消息"""
        task_logger = mod.TaskLogger(engine)
        with patch.object(mod, 'subprocess') as mock_subprocess:
            self._patch_subprocess(mod, mock_subprocess)
            mock_subprocess.run.return_value = MagicMock(returncode=1, stdout="", stderr="SyntaxError: invalid syntax")

            with patch.object(task_logger, 'log_end') as mock_log_end:
                result = mod.run_task(task, task_logger, 1, engine)
                assert result is False
                mock_log_end.assert_called_once()
                error_msg = mock_log_end.call_args[0][5]
                assert "不可重试" in error_msg


# ===================== run_task_chain running 处理测试 =====================

class TestRunTaskChain:
    """run_task_chain 遇到 running 时的行为"""

    def test_running_cleaned_and_continued(self, mod, mock_engine):
        """
        遇到 running 时不再 break，而是清理后继续执行。
        这是 v6 修复的核心验证。
        """
        task_logger = MagicMock()
        task_logger.data_date = "2026-07-09"
        task_logger.batch_id = "20260709-abc123"

        tasks = [{"name": "task_a", "script": "test.py", "args": []},
                 {"name": "task_b", "script": "test.py", "args": []}]

        def mock_db_status(engine, data_date, task_name, stage):
            return "running" if task_name == "task_a" else "pending"

        with patch.object(mod, 'get_task_db_status', side_effect=mock_db_status), \
             patch.object(mod, 'cleanup_zombie_task', return_value=True) as mock_cleanup, \
             patch.object(mod, 'run_task', return_value=True) as mock_run:

            all_success, failed_task = mod.run_task_chain(task_logger, mock_engine, tasks, 1)

            mock_cleanup.assert_called_once_with(mock_engine, "2026-07-09", "task_a", 1)
            assert mock_run.call_count == 2
            assert all_success is True
            assert failed_task is None

    def test_running_chain_not_blocked_when_fails(self, mod, mock_engine):
        """
        验证 running 清理后若执行失败，链式中断。
        """
        task_logger = MagicMock()
        task_logger.data_date = "2026-07-09"
        task_logger.batch_id = "20260709-abc123"

        tasks = [{"name": "task_a", "script": "test.py", "args": []},
                 {"name": "task_b", "script": "test.py", "args": []}]

        def mock_db_status(engine, data_date, task_name, stage):
            return "running" if task_name == "task_a" else "pending"

        with patch.object(mod, 'get_task_db_status', side_effect=mock_db_status), \
             patch.object(mod, 'cleanup_zombie_task', return_value=True), \
             patch.object(mod, 'run_task', side_effect=[False, True]) as mock_run:

            all_success, failed_task = mod.run_task_chain(task_logger, mock_engine, tasks, 1)

            assert mock_run.call_count == 1
            assert all_success is False
            assert failed_task == "task_a"

    def test_skip_success_tasks(self, mod, mock_engine):
        """已成功的任务跳过执行"""
        task_logger = MagicMock()
        task_logger.data_date = "2026-07-09"
        task_logger.batch_id = "20260709-abc123"

        tasks = [{"name": "task_a", "script": "test.py", "args": []},
                 {"name": "task_b", "script": "test.py", "args": []}]

        def mock_db_status(engine, data_date, task_name, stage):
            return "success" if task_name == "task_a" else "pending"

        with patch.object(mod, 'get_task_db_status', side_effect=mock_db_status), \
             patch.object(mod, 'run_task', return_value=True) as mock_run:

            all_success, failed_task = mod.run_task_chain(task_logger, mock_engine, tasks, 1)

            # task_a 跳过，只执行 task_b
            assert mock_run.call_count == 1
            assert all_success is True

    def test_pending_chain_all_success(self, mod, mock_engine):
        """所有 pending 任务正常执行并全部成功"""
        task_logger = MagicMock()
        task_logger.data_date = "2026-07-09"
        task_logger.batch_id = "20260709-abc123"

        tasks = [{"name": "task_a", "script": "test.py", "args": []},
                 {"name": "task_b", "script": "test.py", "args": []}]

        with patch.object(mod, 'get_task_db_status', return_value="pending"), \
             patch.object(mod, 'run_task', return_value=True) as mock_run:

            all_success, failed_task = mod.run_task_chain(task_logger, mock_engine, tasks, 1)

            assert mock_run.call_count == 2
            assert all_success is True
            assert failed_task is None

    def test_pending_chain_failure_breaks(self, mod, mock_engine):
        """pending 任务执行失败时链式中断"""
        task_logger = MagicMock()
        task_logger.data_date = "2026-07-09"
        task_logger.batch_id = "20260709-abc123"

        tasks = [{"name": "task_a", "script": "test.py", "args": []},
                 {"name": "task_b", "script": "test.py", "args": []}]

        with patch.object(mod, 'get_task_db_status', return_value="pending"), \
             patch.object(mod, 'run_task', side_effect=[False, True]) as mock_run:

            all_success, failed_task = mod.run_task_chain(task_logger, mock_engine, tasks, 1)

            # task_a 失败后中断，task_b 不执行
            assert mock_run.call_count == 1
            assert all_success is False
            assert failed_task == "task_a"


# ===================== FileLock 测试 =====================

class TestFileLock:
    """
    跨平台文件锁

    设计说明：FileLock 每次 acquire() 通过 open 打开新文件描述符，
    因此同一进程内两次 acquire() 会竞争同一文件的锁，第二次应返回 False。
    这与 fcntl.flock 的"同一进程内重入"行为不同——因为每次打开新的 fd，
    内核将第二次 flock 视为不同 fd 的锁竞争，而非同一进程的重入。
    """

    def test_acquire_release(self, mod, tmp_path):
        """正常获取和释放锁"""
        lock_path = str(tmp_path / "test.lock")
        lock = mod.FileLock(lock_path)

        assert lock.acquire() is True
        assert lock.lock_fd is not None

        lock.release()
        assert lock.lock_fd is None

    def test_acquire_twice_returns_false(self, mod, tmp_path):
        """
        第二次获取锁应返回 False。
        由于每次 acquire 打开新的 fd，fcntl.flock 视为不同 fd 的锁竞争。
        """
        lock_path = str(tmp_path / "test.lock")
        lock1 = mod.FileLock(lock_path)
        lock2 = mod.FileLock(lock_path)

        assert lock1.acquire() is True
        # lock2 打开新的 fd，flock(LOCK_NB) 会失败
        assert lock2.acquire() is False
        lock1.release()