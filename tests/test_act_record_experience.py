"""
test_act_record_experience.py - 冻结经验落库单元测试

覆盖 _sync_trade_experience 的内容生成与 SQL 行为（mock 数据库连接）：
1. 冻结开启：生成 title/content/tags，INSERT 落库
2. 冻结关闭：UPDATE 软删除经验
3. 记录不存在：无写操作
"""
import os
import sys
import unittest
from unittest.mock import MagicMock

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, 'backend'))

from core.api.router.pdca.act_record import _sync_trade_experience  # noqa: E402


class TestSyncTradeExperience(unittest.TestCase):
    """冻结经验落库逻辑测试（mock 数据库连接，不依赖真实库）"""

    def _make_conn(self, row):
        conn = MagicMock()
        cur = conn.cursor.return_value
        cur.__enter__.return_value = cur
        cur.fetchone.return_value = row
        return conn, cur

    def test_freeze_on_inserts_experience(self):
        """冻结开启：生成经验条目并 INSERT 落库"""
        conn, cur = self._make_conn((
            ['止损执行犹豫', '追高买入'],
            '1. 回踩确认\n2. 三秒原则',
            '止损执行率提升至100%',
            True,
            '2026-08W4',
        ))
        _sync_trade_experience(conn, 42)

        insert_call = None
        for call in cur.execute.call_args_list:
            if call.args[0].strip().startswith('INSERT INTO pdca.trade_experience'):
                insert_call = call
        self.assertIsNotNone(insert_call, '冻结开启时应执行 INSERT 落库')

        source_act_id, title, content, tags = insert_call.args[1]
        self.assertEqual(source_act_id, 42)
        self.assertEqual(title, '2026-08W4 交易经验冻结')
        self.assertIn('止损执行犹豫', content)
        self.assertIn('回踩确认', content)
        self.assertIn('止损执行率提升至100%', content)
        self.assertEqual(tags, ['止损执行犹豫', '追高买入'])

    def test_freeze_off_soft_deletes(self):
        """冻结关闭：UPDATE 软删除关联经验"""
        conn, cur = self._make_conn((
            ['止损执行犹豫'],
            '改进计划',
            None,
            False,
            '2026-08W4',
        ))
        _sync_trade_experience(conn, 42)

        update_call = None
        for call in cur.execute.call_args_list:
            if 'UPDATE pdca.trade_experience' in call.args[0]:
                update_call = call
        self.assertIsNotNone(update_call, '冻结关闭时应执行软删除 UPDATE')
        self.assertIn('deleted_at = NOW()', update_call.args[0])
        self.assertEqual(update_call.args[1], (42,))

    def test_missing_record_no_write(self):
        """记录不存在：仅执行 SELECT 查询，无任何写操作"""
        conn = MagicMock()
        cur = conn.cursor.return_value
        cur.__enter__.return_value = cur
        cur.fetchone.return_value = None
        _sync_trade_experience(conn, 999)
        self.assertEqual(cur.execute.call_count, 1)


if __name__ == '__main__':
    unittest.main()
