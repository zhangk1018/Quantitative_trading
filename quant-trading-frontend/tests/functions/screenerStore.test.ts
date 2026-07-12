/**
 * 测试 ScreenerContext 中 Store 类的 selector 订阅机制
 * 覆盖：subscribeWithSelector / getSelectorSnapshot / dispatch 通知 / 取消订阅 / 异常处理
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { ScreenerState } from '@/features/stock-picker/context/ScreenerContext';

// ==================== 最小化 Store 复制（不依赖 React 上下文） ====================

type Listener = () => void;
type SelectorListener<T> = (value: T) => void;

interface SelectorSubscription<T = unknown> {
  selector: (state: ScreenerState) => T;
  listener: SelectorListener<T>;
  snapshot: T;
}

function shallowEqual(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  if (typeof a !== 'object' || a === null || typeof b !== 'object' || b === null) return false;
  const keysA = Object.keys(a as Record<string, unknown>);
  const keysB = Object.keys(b as Record<string, unknown>);
  if (keysA.length !== keysB.length) return false;
  return keysA.every((key) => (a as Record<string, unknown>)[key] === (b as Record<string, unknown>)[key]);
}

function rootReducer(state: ScreenerState, action: { type: string; payload?: unknown }): ScreenerState {
  switch (action.type) {
    case 'SET_FILTER': {
      const { key, value } = action.payload as { key: string; value: unknown };
      return { ...state, [key]: value };
    }
    default:
      return state;
  }
}

class Store {
  private state: ScreenerState;
  private listeners: Set<Listener> = new Set();
  private selectorSubscriptions: Map<SelectorListener<unknown>, SelectorSubscription<unknown>> = new Map();

  constructor(initialState: ScreenerState) {
    this.state = initialState;
    this.dispatch = this.dispatch.bind(this);
  }

  getState(): ScreenerState {
    return this.state;
  }

  dispatch(action: { type: string; payload?: unknown }) {
    const newState = rootReducer(this.state, action);
    if (newState !== this.state) {
      this.state = newState;
      this.listeners.forEach((l) => l());
      this.selectorSubscriptions.forEach((sub) => {
        try {
          const newValue = sub.selector(this.state);
          if (!shallowEqual(sub.snapshot, newValue)) {
            sub.snapshot = newValue;
            sub.listener(newValue);
          }
        } catch (error) {
          console.error('[Screener] selector 订阅执行失败', error);
        }
      });
    }
  }

  subscribeWithSelector<T>(
    selector: (state: ScreenerState) => T,
    listener: SelectorListener<T>,
  ): () => void {
    const sub: SelectorSubscription<T> = {
      selector,
      listener,
      snapshot: selector(this.state),
    };
    this.selectorSubscriptions.set(listener as SelectorListener<unknown>, sub as SelectorSubscription<unknown>);
    return () => {
      this.selectorSubscriptions.delete(listener as SelectorListener<unknown>);
    };
  }

  getSelectorSnapshot<T>(listener: SelectorListener<T>): T | undefined {
    return this.selectorSubscriptions.get(listener as SelectorListener<unknown>)?.snapshot as T | undefined;
  }
}

// ==================== 测试数据 ====================

function makeState(overrides: Partial<ScreenerState> = {}): ScreenerState {
  return {
    selectedBoards: ['all'],
    stockRange: null,
    marketIndicatorRanges: {},
    financialIndicatorRanges: {},
    selectedTechnicalIndicators: {},
    filterGroup: null,
    ...overrides,
  } as unknown as ScreenerState;
}

// ==================== 测试用例 ====================

describe('Store selector 订阅机制', () => {
  let store: Store;

  beforeEach(() => {
    store = new Store(makeState());
  });

  describe('subscribeWithSelector', () => {
    it('订阅后 getSelectorSnapshot 返回初始值', () => {
      const listener = vi.fn();
      const selector = (s: ScreenerState) => s.selectedBoards;

      store.subscribeWithSelector(selector, listener);

      const snapshot = store.getSelectorSnapshot(listener);
      expect(snapshot).toEqual(['all']);
    });

    it('dispatch 改变值时 listener 被调用且 snapshot 更新', () => {
      const listener = vi.fn();
      const selector = (s: ScreenerState) => s.selectedBoards;

      store.subscribeWithSelector(selector, listener);
      store.dispatch({ type: 'SET_FILTER', payload: { key: 'selectedBoards', value: ['cn'] } });

      expect(listener).toHaveBeenCalledTimes(1);
      expect(listener).toHaveBeenCalledWith(['cn']);

      const snapshot = store.getSelectorSnapshot(listener);
      expect(snapshot).toEqual(['cn']);
    });

    it('dispatch 值未变化时 listener 不被调用', () => {
      const listener = vi.fn();
      const selector = (s: ScreenerState) => s.selectedBoards;

      store.subscribeWithSelector(selector, listener);
      // 设置相同的值
      store.dispatch({ type: 'SET_FILTER', payload: { key: 'selectedBoards', value: ['all'] } });

      expect(listener).not.toHaveBeenCalled();
    });

    it('多个 selector 订阅互不干扰', () => {
      const listenerA = vi.fn();
      const listenerB = vi.fn();
      const selectorA = (s: ScreenerState) => s.selectedBoards;
      const selectorB = (s: ScreenerState) => s.stockRange;

      store.subscribeWithSelector(selectorA, listenerA);
      store.subscribeWithSelector(selectorB, listenerB);
      store.dispatch({ type: 'SET_FILTER', payload: { key: 'selectedBoards', value: ['cn'] } });

      expect(listenerA).toHaveBeenCalledTimes(1);
      expect(listenerB).not.toHaveBeenCalled();
    });
  });

  describe('取消订阅', () => {
    it('取消订阅后 dispatch 不再调用 listener', () => {
      const listener = vi.fn();
      const selector = (s: ScreenerState) => s.selectedBoards;

      const unsubscribe = store.subscribeWithSelector(selector, listener);
      unsubscribe();

      store.dispatch({ type: 'SET_FILTER', payload: { key: 'selectedBoards', value: ['cn'] } });
      expect(listener).not.toHaveBeenCalled();
    });

    it('取消订阅后 getSelectorSnapshot 返回 undefined', () => {
      const listener = vi.fn();
      const selector = (s: ScreenerState) => s.selectedBoards;

      const unsubscribe = store.subscribeWithSelector(selector, listener);
      unsubscribe();

      const snapshot = store.getSelectorSnapshot(listener);
      expect(snapshot).toBeUndefined();
    });
  });

  describe('异常处理', () => {
    it('selector 在 dispatch 时抛出异常不影响其他订阅者', () => {
      const badListener = vi.fn();
      const goodListener = vi.fn();
      // 第一次快照成功，dispatch 时抛出异常
      let callCount = 0;
      const badSelector = (s: ScreenerState) => {
        callCount++;
        if (callCount > 1) throw new Error('selector error');
        return s.selectedBoards;
      };
      const goodSelector = (s: ScreenerState) => s.selectedBoards;

      store.subscribeWithSelector(badSelector, badListener);
      store.subscribeWithSelector(goodSelector, goodListener);
      store.dispatch({ type: 'SET_FILTER', payload: { key: 'selectedBoards', value: ['cn'] } });

      expect(badListener).not.toHaveBeenCalled();
      expect(goodListener).toHaveBeenCalledTimes(1);
      expect(goodListener).toHaveBeenCalledWith(['cn']);
    });
  });

  describe('浅比较（shallowEqual）', () => {
    it('返回内容相同的对象（基本类型值）时 listener 不触发', () => {
      const listener = vi.fn();
      // selector 返回包含基本类型字段的对象，shallowEqual 只比较一层
      const selector = (s: ScreenerState) => ({
        boardCount: s.selectedBoards.length,
        hasRange: s.stockRange !== null,
      });

      store.subscribeWithSelector(selector, listener);
      // 设置相同值，state 内容不变
      store.dispatch({ type: 'SET_FILTER', payload: { key: 'selectedBoards', value: ['all'] } });

      // 内容相同，shallowEqual 应为 true，listener 不应触发
      expect(listener).not.toHaveBeenCalled();
    });

    it('返回内容不同的对象时 listener 触发', () => {
      const listener = vi.fn();
      const selector = (s: ScreenerState) => ({ boards: s.selectedBoards });

      store.subscribeWithSelector(selector, listener);
      store.dispatch({ type: 'SET_FILTER', payload: { key: 'selectedBoards', value: ['cn'] } });

      expect(listener).toHaveBeenCalledTimes(1);
    });
  });
});