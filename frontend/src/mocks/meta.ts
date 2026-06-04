/**
 * mocks/meta.ts - 元数据 Mock 数据
 * 
 * 用于前端开发阶段的模拟数据
 * 对应后端 /api/meta 接口
 */

import type { MetaResponseData } from '../types'

/**
 * Mock 元数据响应
 */
export const mockMetaResponse: MetaResponseData = {
  trade_date: '20260529',
  total: 5234,
  groups: [
    {
      id: 'pattern',
      label: 'K线形态',
      fields: [
        { key: 'pattern_morning_star', label: '早晨之星', count: 89 },
        { key: 'pattern_evening_star', label: '黄昏之星', count: 67 },
        { key: 'pattern_bullish_engulfing', label: '看涨吞没', count: 123 },
        { key: 'pattern_bearish_engulfing', label: '看跌吞没', count: 98 },
        { key: 'pattern_hammer', label: '锤子线', count: 156 },
      ]
    },
    {
      id: 'momentum',
      label: '动量突破',
      fields: [
        { key: 'break_high_20', label: '20日新高', count: 234 },
        { key: 'break_high_60', label: '60日新高', count: 123 },
      ]
    },
    {
      id: 'volume',
      label: '成交量异动',
      fields: [
        { key: 'vol_ratio_5', label: '5日量比>2', count: 456 },
      ]
    }
  ],
  industry_options: [
    '银行', '地产', '医药', '电子', '计算机', '通信', '传媒',
    '电力设备', '汽车', '食品饮料', '家用电器', '建筑材料',
    '交通运输', '机械设备', '化工', '有色金属', '钢铁', '煤炭',
    '石油石化', '农林牧渔', '纺织服装', '轻工制造', '商业贸易',
    '休闲服务', '综合'
  ],
  area_options: [
    '北京', '上海', '深圳', '广州', '杭州', '南京', '成都',
    '武汉', '西安', '重庆', '天津', '苏州', '青岛', '宁波',
    '厦门', '长沙', '郑州', '合肥', '福州', '济南'
  ]
}
