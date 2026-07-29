// backtestListStorage.test.ts — 回测股票列表存储（localStorage CRUD）
//
// 覆盖场景：
//   - 空/非空列表读取
//   - 添加/去重
//   - 移除/清空
//   - 存在性检查
//   - localStorage 异常降级

import { describe, it, expect, beforeEach } from 'vitest';
import {
  getBacktestList,
  addToBacktestList,
  removeFromBacktestList,
  clearBacktestList,
  isInBacktestList,
  type BacktestStockItem,
} from '../../src/features/backtest/backtestListStorage';

const STORAGE_KEY = 'backtest_list';

function setStorage(data: unknown): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
}

beforeEach(() => {
  localStorage.clear();
});

// ==================== getBacktestList ====================

describe('getBacktestList', () => {
  it('空 localStorage 返回空数组', () => {
    expect(getBacktestList()).toEqual([]);
  });

  it('返回已存储的股票列表', () => {
    const items: BacktestStockItem[] = [
      { stock_code: '000001', stock_name: '平安银行' },
      { stock_code: '600000', stock_name: '浦发银行' },
    ];
    setStorage(items);
    const result = getBacktestList();
    expect(result).toHaveLength(2);
    expect(result[0].stock_code).toBe('000001');
  });

  it('损坏的 JSON 返回空数组', () => {
    localStorage.setItem(STORAGE_KEY, '{invalid');
    expect(getBacktestList()).toEqual([]);
  });

  it('非数组数据返回空数组', () => {
    localStorage.setItem(STORAGE_KEY, '"not an array"');
    expect(getBacktestList()).toEqual([]);
  });

  it('非法 JSON 不抛异常', () => {
    localStorage.setItem(STORAGE_KEY, 'not-json');
    expect(() => getBacktestList()).not.toThrow();
  });
});

// ==================== addToBacktestList ====================

describe('addToBacktestList', () => {
  it('往空列表添加股票', () => {
    const items: BacktestStockItem[] = [{ stock_code: '000001', stock_name: '平安银行' }];
    const added = addToBacktestList(items);
    expect(added).toBe(1);
    expect(getBacktestList()).toHaveLength(1);
  });

  it('批量添加多只股票', () => {
    const items: BacktestStockItem[] = [
      { stock_code: '000001', stock_name: '平安银行' },
      { stock_code: '600000', stock_name: '浦发银行' },
    ];
    const added = addToBacktestList(items);
    expect(added).toBe(2);
    expect(getBacktestList()).toHaveLength(2);
  });

  it('重复股票去重', () => {
    setStorage([{ stock_code: '000001', stock_name: '平安银行' }]);
    const items: BacktestStockItem[] = [
      { stock_code: '000001', stock_name: '平安银行' },
      { stock_code: '600000', stock_name: '浦发银行' },
    ];
    const added = addToBacktestList(items);
    expect(added).toBe(1);
    expect(getBacktestList()).toHaveLength(2);
  });

  it('全部重复返回 0', () => {
    setStorage([{ stock_code: '000001', stock_name: '平安银行' }]);
    const items: BacktestStockItem[] = [{ stock_code: '000001', stock_name: '平安银行' }];
    const added = addToBacktestList(items);
    expect(added).toBe(0);
  });

  it('空数组返回 0', () => {
    const added = addToBacktestList([]);
    expect(added).toBe(0);
  });
});

// ==================== removeFromBacktestList ====================

describe('removeFromBacktestList', () => {
  it('移除存在的股票', () => {
    setStorage([
      { stock_code: '000001', stock_name: '平安银行' },
      { stock_code: '600000', stock_name: '浦发银行' },
    ]);
    removeFromBacktestList('000001');
    expect(getBacktestList()).toHaveLength(1);
    expect(getBacktestList()[0].stock_code).toBe('600000');
  });

  it('移除不存在的股票不报错', () => {
    setStorage([{ stock_code: '000001', stock_name: '平安银行' }]);
    removeFromBacktestList('999999');
    expect(getBacktestList()).toHaveLength(1);
  });
});

// ==================== clearBacktestList ====================

describe('clearBacktestList', () => {
  it('清空列表', () => {
    setStorage([{ stock_code: '000001', stock_name: '平安银行' }]);
    clearBacktestList();
    expect(getBacktestList()).toEqual([]);
  });

  it('空列表清空不报错', () => {
    expect(() => clearBacktestList()).not.toThrow();
  });
});

// ==================== isInBacktestList ====================

describe('isInBacktestList', () => {
  it('存在返回 true', () => {
    setStorage([{ stock_code: '000001', stock_name: '平安银行' }]);
    expect(isInBacktestList('000001')).toBe(true);
  });

  it('不存在返回 false', () => {
    expect(isInBacktestList('000001')).toBe(false);
  });
});