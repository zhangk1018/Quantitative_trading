def _update_tech_patterns(self, session, target_date: str):
    """
    独立计算 14 个技术指标 pattern（分批次 UPDATE，降低单次查询复杂度）
    
    2026-06-16 修复版：
    - 增加数据存在性检查，避免空跑
    - 放宽 MACD/RSI 金叉死叉条件（不再限制 dif 正负）
    - 增加底背离/顶背离计算（基于股价与指标低点/高点的比较）
    - 使用 LATERAL JOIN 优化前一日数据获取，避免子查询重复执行
    - 输出每个 pattern 更新的影响行数
    """
    logger = logging.getLogger(__name__)
    
    # 1. 检查 stock_indicators 表中是否有 target_date 的数据
    check_sql = text("""
        SELECT COUNT(*) FROM stock_indicators
        WHERE trade_date = :target_date AND cycle = '1d'
    """)
    cnt = session.execute(check_sql, {'target_date': target_date}).scalar()
    if cnt == 0:
        logger.warning(f"⚠️ {target_date} 无指标数据 (stock_indicators)，跳过 pattern 更新")
        session.commit()
        return

    # 2. MA pattern（基于已计算的 ma5/ma10/ma20）
    ma_sql = text("""
        UPDATE stock_daily_snapshot
        SET ma_long_align = (ma5 IS NOT NULL AND ma5 > ma10 AND ma10 > ma20),
            ma_short_align = (ma5 IS NOT NULL AND ma5 < ma10 AND ma10 < ma20)
        WHERE trade_date = :target_date
    """)
    result = session.execute(ma_sql, {'target_date': target_date})
    logger.info(f"  ✓ MA pattern 更新完成，影响 {result.rowcount} 行")

    # 3. MACD pattern（金叉/死叉 + 底背离/顶背离）
    #    使用 LATERAL 获取前一日指标，避免性能问题
    macd_sql = text("""
        UPDATE stock_daily_snapshot s
        SET
            -- 金叉（macd 从下向上穿过 dea），不再限制 dif 正负
            macd_low_golden_cross = (
                i.macd IS NOT NULL AND iprev.macd IS NOT NULL
                AND iprev.macd < iprev.dea AND i.macd >= i.dea
            ),
            -- 死叉（macd 从上向下穿过 dea）
            macd_high_death_cross = (
                i.macd IS NOT NULL AND iprev.macd IS NOT NULL
                AND iprev.macd > iprev.dea AND i.macd <= i.dea
            ),
            -- 底背离：股价新低，MACD 低点抬高
            macd_bottom_divergence = (
                q.close IS NOT NULL AND qprev.close IS NOT NULL
                AND i.macd IS NOT NULL AND iprev.macd IS NOT NULL
                AND q.close < qprev.close
                AND i.macd > iprev.macd
            ),
            -- 顶背离：股价新高，MACD 高点降低
            macd_top_divergence = (
                q.close IS NOT NULL AND qprev.close IS NOT NULL
                AND i.macd IS NOT NULL AND iprev.macd IS NOT NULL
                AND q.close > qprev.close
                AND i.macd < iprev.macd
            )
        FROM
            -- 当前股票的指标
            stock_indicators i
            -- 前一日指标（LATERAL 保证每个 i 只取一条前一条记录）
            LEFT JOIN LATERAL (
                SELECT macd, dea, dif
                FROM stock_indicators iprev2
                WHERE iprev2.code = i.code
                  AND iprev2.cycle = '1d'
                  AND iprev2.trade_date < i.trade_date
                ORDER BY iprev2.trade_date DESC
                LIMIT 1
            ) iprev ON TRUE
            -- 当前股票的行情（用于背离中的收盘价）
            LEFT JOIN stock_quotes q
                ON q.code = i.code AND q.cycle = '1d' AND q.trade_date = i.trade_date
            -- 前一日行情
            LEFT JOIN LATERAL (
                SELECT close
                FROM stock_quotes qprev2
                WHERE qprev2.code = q.code
                  AND qprev2.cycle = '1d'
                  AND qprev2.trade_date < q.trade_date
                ORDER BY qprev2.trade_date DESC
                LIMIT 1
            ) qprev ON TRUE
        WHERE s.code = i.code
          AND s.trade_date = :target_date
          AND i.cycle = '1d'
          AND i.trade_date = :target_date
    """)
    result = session.execute(macd_sql, {'target_date': target_date})
    logger.info(f"  ✓ MACD pattern 更新完成，影响 {result.rowcount} 行")

    # 4. BOLL pattern（需要前一日收盘价，使用 CTE 避免 LATERAL 引用问题）
    boll_sql = text("""
        WITH prev_close AS (
            SELECT DISTINCT ON (code) code, close AS close_prev
            FROM stock_quotes
            WHERE cycle = '1d' AND trade_date = (
                SELECT MAX(trade_date) FROM stock_quotes q2
                WHERE q2.code = stock_quotes.code AND q2.cycle = '1d' AND q2.trade_date < :target_date
            )
        )
        UPDATE stock_daily_snapshot s
        SET boll_break_upper = (pc.close_prev IS NOT NULL AND s.close > s.boll_upper AND pc.close_prev <= s.boll_upper),
            boll_break_middle_up = (pc.close_prev IS NOT NULL AND s.close > s.boll_mid AND pc.close_prev <= s.boll_mid),
            boll_break_middle_down = (pc.close_prev IS NOT NULL AND s.close < s.boll_mid AND pc.close_prev >= s.boll_mid),
            boll_break_lower = (pc.close_prev IS NOT NULL AND s.close < s.boll_lower AND pc.close_prev >= s.boll_lower)
        FROM prev_close pc
        WHERE s.trade_date = :target_date AND s.code = pc.code
    """)
    result = session.execute(boll_sql, {'target_date': target_date})
    logger.info(f"  ✓ BOLL pattern 更新完成，影响 {result.rowcount} 行")

    # 5. RSI pattern（金叉/死叉 + 底背离/顶背离）
    #    使用 LATERAL 获取前一日指标，同时需要 rsi24 字段（若不存在则跳过背离）
    rsi_sql = text("""
        UPDATE stock_daily_snapshot s
        SET
            -- RSI 低位金叉（rsi6 从下向上穿过 rsi24，且两者均在 30 以下）
            rsi_low_golden_cross = (
                i.rsi6 IS NOT NULL AND iprev.rsi6 IS NOT NULL
                AND i.rsi24 IS NOT NULL AND iprev.rsi24 IS NOT NULL
                AND i.rsi6 < 30 AND iprev.rsi6 < 30
                AND iprev.rsi6 <= iprev.rsi24 AND i.rsi6 > i.rsi24
            ),
            -- RSI 高位死叉（rsi6 从上向下穿过 rsi24，且两者均在 70 以上）
            rsi_high_death_cross = (
                i.rsi6 IS NOT NULL AND iprev.rsi6 IS NOT NULL
                AND i.rsi24 IS NOT NULL AND iprev.rsi24 IS NOT NULL
                AND i.rsi6 > 70 AND iprev.rsi6 > 70
                AND iprev.rsi6 >= iprev.rsi24 AND i.rsi6 < i.rsi24
            ),
            -- RSI 底背离：股价新低，RSI6 低点抬高
            rsi_bottom_divergence = (
                q.close IS NOT NULL AND qprev.close IS NOT NULL
                AND i.rsi6 IS NOT NULL AND iprev.rsi6 IS NOT NULL
                AND q.close < qprev.close
                AND i.rsi6 > iprev.rsi6
            ),
            -- RSI 顶背离：股价新高，RSI6 高点降低
            rsi_top_divergence = (
                q.close IS NOT NULL AND qprev.close IS NOT NULL
                AND i.rsi6 IS NOT NULL AND iprev.rsi6 IS NOT NULL
                AND q.close > qprev.close
                AND i.rsi6 < iprev.rsi6
            )
        FROM
            stock_indicators i
            LEFT JOIN LATERAL (
                SELECT rsi6, rsi24
                FROM stock_indicators iprev2
                WHERE iprev2.code = i.code
                  AND iprev2.cycle = '1d'
                  AND iprev2.trade_date < i.trade_date
                ORDER BY iprev2.trade_date DESC
                LIMIT 1
            ) iprev ON TRUE
            LEFT JOIN stock_quotes q
                ON q.code = i.code AND q.cycle = '1d' AND q.trade_date = i.trade_date
            LEFT JOIN LATERAL (
                SELECT close
                FROM stock_quotes qprev2
                WHERE qprev2.code = q.code
                  AND qprev2.cycle = '1d'
                  AND qprev2.trade_date < q.trade_date
                ORDER BY qprev2.trade_date DESC
                LIMIT 1
            ) qprev ON TRUE
        WHERE s.code = i.code
          AND s.trade_date = :target_date
          AND i.cycle = '1d'
          AND i.trade_date = :target_date
    """)
    result = session.execute(rsi_sql, {'target_date': target_date})
    logger.info(f"  ✓ RSI pattern 更新完成，影响 {result.rowcount} 行")

    session.commit()
    logger.info(f"✅ {target_date} 全部 pattern 更新完成")