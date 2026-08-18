-- ============================================================
-- PDCA 测试数据：基于真实行情（2026-W33，2026-08-10 ~ 08-14）
-- 包含好交易、坏交易、违规交易，覆盖完整 PDCA 闭环
-- v2: 修正违规类型，改进 MAX(id) 依赖，增加经验知识库记录
-- ============================================================
--
-- 周期：2026-08 第二周 (2026-W33)
-- 真实行情数据参考：
--   宁德时代(300750) 08-10: O=385.61 H=394.62 L=384.63 C=393.87
--   贵州茅台(600519) 08-10: O=1325.00 H=1359.97 L=1318.08 C=1348.86
--   中国平安(601318) 08-10: O=53.28 H=53.66 L=53.20 C=53.32
--   海康威视(002415) 08-11: O=37.26 H=38.03 L=36.28 C=36.37
--   平安银行(000001) 08-11: O=11.31 H=11.40 L=11.24 C=11.26
-- ============================================================

BEGIN;

-- ============================================================
-- 1. 删除旧数据（重新注入时清理）
-- ============================================================
DELETE FROM pdca.trade_experience WHERE id IN (SELECT id FROM pdca.trade_experience WHERE created_at >= '2026-08-10');
DELETE FROM pdca.pdca_act_record WHERE pdca_cycle_id IN (SELECT id FROM pdca.pdca_cycle WHERE cycle_name = '2026-W33');
DELETE FROM pdca.pdca_check_report WHERE pdca_cycle_id IN (SELECT id FROM pdca.pdca_cycle WHERE cycle_name = '2026-W33');
DELETE FROM pdca.trading_diary WHERE pdca_cycle_id IN (SELECT id FROM pdca.pdca_cycle WHERE cycle_name = '2026-W33');
DELETE FROM pdca.behavior_log WHERE pdca_cycle_id IN (SELECT id FROM pdca.pdca_cycle WHERE cycle_name = '2026-W33');
DELETE FROM pdca.trading_record WHERE pdca_cycle_id IN (SELECT id FROM pdca.pdca_cycle WHERE cycle_name = '2026-W33');
DELETE FROM pdca.trading_plan WHERE pdca_cycle_id IN (SELECT id FROM pdca.pdca_cycle WHERE cycle_name = '2026-W33');
DELETE FROM pdca.pdca_cycle WHERE cycle_name = '2026-W33';

-- ============================================================
-- 2. 创建 PDCA 周期（2026-W33，上周）
-- ============================================================
WITH new_cycle AS (
  INSERT INTO pdca.pdca_cycle (account_id, cycle_type, cycle_name, status, start_date, end_date, goal_text)
  VALUES (1, 'week', '2026-W33', 'CHECK', '2026-08-10', '2026-08-14',
          '严格执行交易计划，控制单笔风险≤2%，月度总风险≤6%')
  RETURNING id
)
SELECT id FROM new_cycle \gset

-- 使用变量保存周期 ID，不依赖 MAX(id)
\echo Created new cycle with id = :id

-- ============================================================
-- 3. 交易计划（好的交易有计划，坏的交易无计划）
-- ============================================================

-- 计划1：宁德时代 — 成功交易（日线多头排列，MACD 金叉区域）
INSERT INTO pdca.trading_plan
    (account_id, pdca_cycle_id, template_id, code, security_name, instrument_type,
     long_short, plan_status, weekly_view, daily_view,
     entry_price, stop_loss_price, target_price, max_risk_rate, plan_quantity, abort_condition)
VALUES
    (1, :id, 1,
     '300750', '宁德时代', 'stock',
     'long', 'executed',
     '周线上升趋势，MACD 零轴上方运行，上周放量突破前高，均线多头排列',
     '日线回调至 20 日均线附近企稳，MACD 红柱缩短后再次放大，RSI 从 50 附近回升，量能配合',
     386.00, 375.00, 400.00, 0.02, 100,
     '跌破 375 或 MACD 死叉');

-- 计划2：贵州茅台 — 成功交易（趋势向上，缩量回调后放量上涨）
INSERT INTO pdca.trading_plan
    (account_id, pdca_cycle_id, template_id, code, security_name, instrument_type,
     long_short, plan_status, weekly_view, daily_view,
     entry_price, stop_loss_price, target_price, max_risk_rate, plan_quantity, abort_condition)
VALUES
    (1, :id, 1,
     '600519', '贵州茅台', 'stock',
     'long', 'executed',
     '周线沿 MA20 稳步上行，MACD 零轴上方金叉，量价配合良好',
     '日线缩量回调至 MA10 支撑位，MACD 红柱未明显缩短，RSI 维持 50 以上强势区域',
     1326.00, 1310.00, 1360.00, 0.02, 100,
     '跌破 1310 或日线放量下跌');

-- 计划3：中国平安 — 失败交易（计划内的止损）
INSERT INTO pdca.trading_plan
    (account_id, pdca_cycle_id, template_id, code, security_name, instrument_type,
     long_short, plan_status, weekly_view, daily_view,
     entry_price, stop_loss_price, target_price, max_risk_rate, plan_quantity, abort_condition)
VALUES
    (1, :id, 1,
     '601318', '中国平安', 'stock',
     'long', 'executed',
     '周线处于箱体震荡下沿，MACD 零轴附近走平，有技术性反弹需求',
     '日线连续缩量回调至前期低点支撑位，RSI 进入超卖区（<30），KDJ 低位金叉',
     53.50, 52.00, 55.00, 0.02, 1000,
     '跌破 52 元支撑位则放弃');

-- ============================================================
-- 4. 交易记录（电子台账）
-- ============================================================

-- 好交易1：宁德时代 300750
-- 入场 08-10: O=385.61 H=394.62 L=384.63 C=393.87
-- 出场 08-13: O=393.04 H=399.39 L=391.04 C=396.30
-- 通道高度: 394.62-384.63=9.99
-- 进场得分: (394.62-386.00)/9.99*100=86.29
-- 出场得分: (396.00-391.04)/(399.39-391.04)*100=59.40
-- 交易得分: (86.29+59.40)/2=72.85 → A级
-- 毛利: (396.00-386.00)*100=+1000
WITH plan_id AS (
  SELECT id FROM pdca.trading_plan WHERE code='300750' AND pdca_cycle_id = :id
)
INSERT INTO pdca.trading_record
    (account_id, pdca_cycle_id, trading_plan_id, code, security_name, instrument_type,
     long_short, order_type, entry_date, exit_date, entry_price, exit_price, quantity,
     channel_height, gross_profit, entry_score, exit_score, trade_score, trade_grade,
     trigger_source, exit_reason, commission_entry, commission_exit)
VALUES
    (1, :id, (SELECT id FROM plan_id),
     '300750', '宁德时代', 'stock',
     'long', 'limit', '2026-08-10', '2026-08-13', 386.00, 396.00, 100,
     9.99, 1000.00, 86.29, 59.40, 72.85, 'A',
     'scanner', 'take_profit', 5.00, 5.00);

-- 好交易2：贵州茅台 600519
-- 入场 08-10: O=1325.00 H=1359.97 L=1318.08 C=1348.86
-- 出场 08-12: O=1346.50 H=1356.88 L=1332.51 C=1343.00
-- 通道高度: 1359.97-1318.08=41.89
-- 进场得分: (1359.97-1326.00)/41.89*100=81.09
-- 出场得分: (1345.00-1332.51)/(1356.88-1332.51)*100=51.25
-- 交易得分: (81.09+51.25)/2=66.17 → A级
-- 毛利: (1345.00-1326.00)*100=+1900
WITH plan_id AS (
  SELECT id FROM pdca.trading_plan WHERE code='600519' AND pdca_cycle_id = :id
)
INSERT INTO pdca.trading_record
    (account_id, pdca_cycle_id, trading_plan_id, code, security_name, instrument_type,
     long_short, order_type, entry_date, exit_date, entry_price, exit_price, quantity,
     channel_height, gross_profit, entry_score, exit_score, trade_score, trade_grade,
     trigger_source, exit_reason, commission_entry, commission_exit)
VALUES
    (1, :id, (SELECT id FROM plan_id),
     '600519', '贵州茅台', 'stock',
     'long', 'limit', '2026-08-10', '2026-08-12', 1326.00, 1345.00, 100,
     41.89, 1900.00, 81.09, 51.25, 66.17, 'A',
     'scanner', 'take_profit', 5.00, 5.00);

-- 坏交易1：中国平安 601318 止损（有计划但执行失败）
-- 入场 08-10: O=53.28 H=53.66 L=53.20 C=53.32
-- 出场 08-14: O=52.67 H=52.77 L=51.75 C=51.75
-- 通道高度: 53.66-53.20=0.46
-- 进场得分: (53.66-53.50)/0.46*100=34.78
-- 出场得分: (51.75-51.75)/(52.77-51.75)*100=0.00（跌停价出场）
-- 交易得分: (34.78+0.00)/2=17.39 → B级 (10-30)
-- 毛利: (51.75-53.50)*1000=-1750
WITH plan_id AS (
  SELECT id FROM pdca.trading_plan WHERE code='601318' AND pdca_cycle_id = :id
)
INSERT INTO pdca.trading_record
    (account_id, pdca_cycle_id, trading_plan_id, code, security_name, instrument_type,
     long_short, order_type, entry_date, exit_date, entry_price, exit_price, quantity,
     channel_height, gross_profit, entry_score, exit_score, trade_score, trade_grade,
     trigger_source, exit_reason, commission_entry, commission_exit, actual_stop_loss)
VALUES
    (1, :id, (SELECT id FROM plan_id),
     '601318', '中国平安', 'stock',
     'long', 'limit', '2026-08-10', '2026-08-14', 53.50, 51.75, 1000,
     0.46, -1750.00, 34.78, 0.00, 17.39, 'B',
     'scanner', 'stop_loss', 5.00, 5.00, 52.00);

-- 坏交易2：海康威视 002415 无计划追涨（违规交易）
-- 入场 08-11: O=37.26 H=38.03 L=36.28 C=36.37
-- 出场 08-14: O=35.62 H=35.81 L=34.54 C=34.88
-- 通道高度: 38.03-36.28=1.75
-- 进场得分: (38.03-38.00)/1.75*100=1.71（追高买入）
-- 出场得分: (34.88-34.54)/(35.81-34.54)*100=26.77（恐慌卖出）
-- 交易得分: (1.71+26.77)/2=14.24 → B级
-- 毛利: (34.88-38.00)*1000=-3120
INSERT INTO pdca.trading_record
    (account_id, pdca_cycle_id, trading_plan_id, code, security_name, instrument_type,
     long_short, order_type, entry_date, exit_date, entry_price, exit_price, quantity,
     channel_height, gross_profit, entry_score, exit_score, trade_score, trade_grade,
     trigger_source, exit_reason, commission_entry, commission_exit)
VALUES
    (1, :id, NULL,  -- 无计划（违规交易）
     '002415', '海康威视', 'stock',
     'long', 'market', '2026-08-11', '2026-08-14', 38.00, 34.88, 1000,
     1.75, -3120.00, 1.71, 26.77, 14.24, 'B',
     'impulse', 'stop_loss', 5.00, 5.00);

-- 裸交易：平安银行 000001（无计划，违反纪律）
-- 入场 08-11: O=11.31 H=11.40 L=11.24 C=11.26
-- 出场 08-12: O=11.26 H=11.29 L=11.20 C=11.25
-- 通道高度: 11.40-11.24=0.16
-- 进场得分: (11.40-11.35)/0.16*100=31.25
-- 出场得分: (11.22-11.20)/(11.29-11.20)*100=22.22
-- 交易得分: (31.25+22.22)/2=26.74 → B级
-- 毛利: (11.22-11.35)*2000=-260
INSERT INTO pdca.trading_record
    (account_id, pdca_cycle_id, trading_plan_id, code, security_name, instrument_type,
     long_short, order_type, entry_date, exit_date, entry_price, exit_price, quantity,
     channel_height, gross_profit, entry_score, exit_score, trade_score, trade_grade,
     trigger_source, exit_reason, commission_entry, commission_exit)
VALUES
    (1, :id, NULL,  -- 无计划（裸交易）
     '000001', '平安银行', 'stock',
     'long', 'market', '2026-08-11', '2026-08-12', 11.35, 11.22, 2000,
     0.16, -260.00, 31.25, 22.22, 26.74, 'B',
     'impulse', 'impulsive', 5.00, 5.00);

-- ============================================================
-- 5. 违规日志
-- ============================================================

-- 海康威视违规（无计划交易）
INSERT INTO pdca.behavior_log
    (account_id, pdca_cycle_id, trading_record_id, log_type, violation_type, severity, log_content, happened_at)
SELECT 1, :id, id, 'violation', 'no_plan_trade', 'high',
       '无计划追涨海康威视(002415)，入场价38.00元，冲动交易，严重违反纪律',
       '2026-08-11 09:35:00+08'
FROM pdca.trading_record WHERE code='002415' AND trading_plan_id IS NULL AND pdca_cycle_id = :id;

-- 平安银行违规（裸交易）
INSERT INTO pdca.behavior_log
    (account_id, pdca_cycle_id, trading_record_id, log_type, violation_type, severity, log_content, happened_at)
SELECT 1, :id, id, 'violation', 'no_plan_trade', 'medium',
       '盘中冲动买入平安银行(000001)，入场价11.35元，无计划裸交易，次日恐慌卖出',
       '2026-08-11 10:22:00+08'
FROM pdca.trading_record WHERE code='000001' AND trading_plan_id IS NULL AND pdca_cycle_id = :id;

-- 中国平安：入场质量不佳（虽然计划内，但评分不高）→ violation_type 设为 NULL（非违规，属复盘反思）
INSERT INTO pdca.behavior_log
    (account_id, pdca_cycle_id, trading_record_id, log_type, violation_type, severity, log_content, happened_at)
SELECT 1, :id, id, 'violation', NULL, 'low',
       '中国平安(601318)入场质量不佳，交易得分17.39分(B级)，入场价偏高需反思入场时机',
       '2026-08-14 14:57:00+08'
FROM pdca.trading_record WHERE code='601318' AND pdca_cycle_id = :id;

-- ============================================================
-- 6. 交易日记
-- ============================================================

-- 宁德时代日记
INSERT INTO pdca.trading_diary
    (account_id, trading_record_id, pdca_cycle_id, emotion_note, review_text)
SELECT 1, id, :id,
       '情绪稳定，按计划执行，入场后略有波动但未恐慌',
       '宁德时代按计划在386入场，当日MACD金叉确认，RSI回升至50上方。'
       ||'周三盘中冲高399未及时止盈，回落至396止盈。'
       ||'教训：触及目标价附近应分批止盈，不可贪心。'
       ||'优点：严格执行了入场计划，止损位设定合理。'
FROM pdca.trading_record WHERE code='300750' AND pdca_cycle_id = :id;

-- 贵州茅台日记
INSERT INTO pdca.trading_diary
    (account_id, trading_record_id, pdca_cycle_id, emotion_note, review_text)
SELECT 1, id, :id,
       '保持耐心，等待到理想入场点，情绪控制良好',
       '茅台周一开盘回调至1326附近入场，缩量回调确认支撑。'
       ||'周二盘中触及1345止盈，获利约1.4%。'
       ||'这是一次标准的计划内交易，入场点位选择合理，'
       ||'止盈也按照计划执行。值得复盘学习。'
FROM pdca.trading_record WHERE code='600519' AND pdca_cycle_id = :id;

-- 中国平安日记
INSERT INTO pdca.trading_diary
    (account_id, trading_record_id, pdca_cycle_id, emotion_note, review_text)
SELECT 1, id, :id,
       '止损时情绪低落，但理性上知道这是正确的风控操作',
       '中国平安这笔交易犯了几个错误：'
       ||'1. 入场价偏高(53.50)，应该等待更好的安全边际'
       ||'2. 虽然设置了止损，但入场位置不够理想'
       ||'3. 周线级别处于下降趋势，逆势交易风险大'
       ||'做得好的地方：严格执行了止损，没有扛单。'
       ||'改进：逆势交易应降低仓位，或者等待更明确的底部信号。'
FROM pdca.trading_record WHERE code='601318' AND pdca_cycle_id = :id;

-- 海康威视日记
INSERT INTO pdca.trading_diary
    (account_id, trading_record_id, pdca_cycle_id, emotion_note, review_text)
SELECT 1, id, :id,
       '追涨后极度焦虑，连续几天睡不好觉，最终恐慌割肉',
       '海康威视是本周最失败的一笔交易。'
       ||'周二看到放量拉升冲动追入，完全违背了交易计划原则。'
       ||'入场后连续下跌，每天都在焦虑中度过，最终在周五恐慌卖出。'
       ||'这是一笔典型的冲动交易，从入场到出场全是错误。'
       ||'教训：永远不要追涨，永远不要进行无计划交易。'
       ||'建议：将这笔交易记录为反面教材，每周复盘时重读。'
FROM pdca.trading_record WHERE code='002415' AND pdca_cycle_id = :id;

-- 平安银行日记
INSERT INTO pdca.trading_diary
    (account_id, trading_record_id, pdca_cycle_id, emotion_note, review_text)
SELECT 1, id, :id,
       '看到盘中有异动就冲动入场，完全没有耐心等待',
       '平安银行是一笔极小的裸交易，虽然亏损不大(260元)，'
       ||'但性质和海康威视一样严重——都是无计划交易。'
       ||'反映出当前交易纪律仍有漏洞，容易受到盘中异动诱惑。'
       ||'改进：坚持"无计划不开仓"的铁律，'
       ||'即使看到机会也要等日线收盘再做决定。'
FROM pdca.trading_record WHERE code='000001' AND pdca_cycle_id = :id;

-- ============================================================
-- 7. Check 复盘报告
-- ============================================================
-- 统计：
--   总交易：5笔
--   按计划完成：3笔（300750、600519、601318）
--   执行率：60%
--   胜率：40%（2笔盈利，3笔亏损）
--   盈亏比：(1000+1900)/(1750+3120+260)=2900/5130=0.5653
--   平均进场得分：(86.29+81.09+34.78+1.71+31.25)/5=47.02
--   平均出场得分：(59.40+51.25+0.00+26.77+22.22)/5=31.93
--   平均交易得分：(72.85+66.17+17.39+14.24+26.74)/5=39.48
--   最大回撤：-3120（海康威视）
--   违规次数：2（海康+平安银行）

INSERT INTO pdca.pdca_check_report
    (account_id, pdca_cycle_id, report_status, total_trade_count, complete_by_plan_count,
     execution_rate, win_rate, profit_loss_ratio, avg_entry_score, avg_exit_score, avg_trade_score,
     max_drawdown, violation_total, report_content)
VALUES
    (1, :id,
     'draft',
     5, 3,
     60.00, 40.00, 0.5653, 47.02, 31.93, 39.48,
     -3120.00, 2,
     '## 2026-W33 复盘报告

### 本周总结

本周共交易5笔，3笔按计划执行（宁德时代 + 贵州茅台 + 中国平安），2笔违规交易（海康威视 + 平安银行）。整体亏损-2230元。

### 做得好的

1. **宁德时代**：按计划入场，MACD金叉确认后入场，获利+1000元。进场时机把握较好。
2. **贵州茅台**：严格按计划在缩量回调时入场，获利+1900元。这是一笔标准交易，值得复制。
3. **中国平安止损**：虽然亏损-1750元，但严格执行了止损计划，没有扛单。这是纪律性的体现。

### 需要改进的

1. **海康威视追涨**：无计划追涨，亏损-3120元，本周最大亏损来源。需深刻反思。
2. **平安银行裸交易**：盘中冲动交易，虽然亏损很小，但性质严重。
3. **入场时机**：中国平安入场价偏高（53.50），应等待更好的安全边际。

### 情绪管理

本周情绪波动较大，海康威视亏损后影响了后续判断。宁波银行裸交易也是情绪失控的结果。

### 改进计划

1. 严格执行"无计划不开仓"铁律
2. 下次入场前先完成交易计划编写
3. 追涨时强制等待15分钟冷静期
4. 单日亏损超过2%时停止交易');

-- ============================================================
-- 8. Act 改进措施
-- ============================================================

INSERT INTO pdca.pdca_act_record
    (account_id, pdca_cycle_id, problem_list, rectify_plan, bind_next_cycle_goal, is_freeze_experience, new_config_version)
VALUES
    (1, :id,
     ARRAY['无计划交易（海康威视、平安银行）', '入场时机选择不佳（中国平安）', '追涨冲动行为', '情绪管理能力不足'],
     '1. 严格执行"无计划不开仓"铁律：任何交易前必须先在系统中创建交易计划，填写完整的weekly_view/daily_view/entry_price/stop_loss_price
2. 建立"冷静期"机制：看到盘中异动时，强制等待15分钟，确认不是冲动后再决策
3. 每日开盘前花10分钟复盘当日计划，写下当日交易目标
4. 单日亏损超过2%时立即停止交易，当日不再开新仓',
     '实现连续5个交易日零违规交易',
     TRUE,
     '1.1.0');

-- ============================================================
-- 9. 经验知识库：冻结经验记录（冻结经验入库）
-- ============================================================

INSERT INTO pdca.trade_experience
    (account_id, trading_record_id, title, content, tags)
SELECT 1, NULL,
       '2026-W33 交易纪律改进：严格执行无计划不开仓',
       '从 2026-W33 两周测试中，两次无计划交易合计亏损 3380 元，说明纪律执行仍有漏洞。'
       ||'\n\n总结教训：'
       ||'\n1. 永远不要追涨，任何追涨都必须等待日线收盘确认'
       ||'\n2. 无计划不开仓是铁律，即使看到机会也要耐心等待计划完成'
       ||'\n3. 情绪失控时必须暂停交易，不能带着情绪开仓'
       ||'\n\n改进措施已记入 pdca_act_record，下一周期目标为"连续 5 个交易日零违规"',
       ARRAY['纪律执行', '无计划交易', '情绪管理'];

COMMIT;

\echo '============================================================'
\echo 'PDCA 测试数据注入完成！'
\echo '周期 ID: ' :id
\echo '数据统计:'
\echo '  - 交易计划: 3'
\echo '  - 交易记录: 5 (2笔好交易 + 3笔坏交易)'
\echo '  - 违规日志: 3'
\echo '  - 交易日记: 5'
\echo '  - 复盘报告: 1'
\echo '  - 改进措施: 1'
\echo '  - 经验知识库: 1'
\echo '============================================================'
