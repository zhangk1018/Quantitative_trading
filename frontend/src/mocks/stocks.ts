/**
 * mocks/stocks.ts - 股票列表 Mock 数据
 * 
 * 用于前端开发阶段的模拟数据
 * 对应后端 /api/stocks 接口
 */

import type { StockResponse } from '../types'

/**
 * 生成 Mock 股票数据
 */
export function generateMockStocks(count: number = 100): StockResponse[] {
  const stocks: StockResponse[] = []
  
  const stockNames = [
    '平安银行', '万科A', '国农科技', '世纪星源', '深振业A',
    '全新好', '神州高铁', '中国宝安', '美丽生态', '深物业A',
    '南玻A', '沙河股份', '深能源A', '飞亚达', '国药一致',
    '深深房A', '中集集团', '中冠A', '深深宝A', '深深华A',
    '深康佳A', '深中华A', '深纺织A', '特力A', '飞亚达A',
    '亨通光电', '中天科技', '烽火通信', '长江通信', '光迅科技'
  ]
  
  const industries = ['银行', '地产', '医药', '电子', '计算机', '通信', '传媒']
  const boards: Array<'主板' | '创业板' | '科创板' | '北交所'> = ['主板', '创业板', '科创板', '北交所']
  
  for (let i = 0; i < count; i++) {
    const basePrice = 5 + Math.random() * 50
    const changePct = (Math.random() - 0.5) * 10
    const close = basePrice * (1 + changePct / 100)
    
    stocks.push({
      stock_code: `${String(i).padStart(6, '0')}.${i % 2 === 0 ? 'SZ' : 'SH'}`,
      stock_name: stockNames[i % stockNames.length],
      listed_board: boards[i % boards.length],
      industry: industries[i % industries.length],
      sub_industry: null,
      trade_date: '2026-05-29',
      pre_close: basePrice,
      open: basePrice * (0.98 + Math.random() * 0.04),
      close: Number(close.toFixed(2)),
      high: Number((close * (1 + Math.random() * 0.03)).toFixed(2)),
      low: Number((close * (1 - Math.random() * 0.03)).toFixed(2)),
      volume: Math.floor(Math.random() * 10000000),
      amount: Number((close * Math.random() * 10000000).toFixed(2)),
      change: Number((changePct * basePrice / 100).toFixed(2)),
      change_pct: Number(changePct.toFixed(2)),
      turnover_rate: Number((Math.random() * 10).toFixed(2)),
      pe: Number((5 + Math.random() * 50).toFixed(2)),
      pb: Number((0.5 + Math.random() * 10).toFixed(2)),
      market_cap: Number((100000 + Math.random() * 10000000).toFixed(2)),
      circ_mv: Number((80000 + Math.random() * 8000000).toFixed(2)),
      ma5: Number((close * (0.95 + Math.random() * 0.1)).toFixed(2)),
      ma10: Number((close * (0.93 + Math.random() * 0.14)).toFixed(2)),
      ma20: Number((close * (0.90 + Math.random() * 0.2)).toFixed(2)),
      v_ma5: Math.floor(Math.random() * 10000000),
      rsi_6: Number((30 + Math.random() * 40).toFixed(2)),
      macd: Number(((Math.random() - 0.5) * 2).toFixed(2)),
      boll_upper: Number((close * (1 + Math.random() * 0.05)).toFixed(2)),
      boll_mid: Number(close.toFixed(2)),
      boll_lower: Number((close * (1 - Math.random() * 0.05)).toFixed(2)),
      is_st: Math.random() < 0.05,
      is_new: Math.random() < 0.1,
      limit_up: changePct > 9.5,
      limit_down: changePct < -9.5
    })
  }
  
  return stocks
}

/**
 * Mock 股票列表响应（前10条）
 */
export const mockStocksResponse: StockResponse[] = generateMockStocks(10)
