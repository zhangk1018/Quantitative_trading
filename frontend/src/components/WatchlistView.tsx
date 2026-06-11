/**
 * WatchlistView.tsx - 我的自选股
 *
 * Phase 4.4.2 (2026-06-10): 接入真实 API
 * - GET /api/watchlist/ 拉取自选股列表
 * - POST /api/watchlist/ 添加自选股
 * - DELETE /api/watchlist/{code} 移除自选股
 * - 行情信息：对每只自选股调 /api/stocks/{code}/ 补全（接受 N+1，自选股数量小）
 * - Loading / Error / Empty 态
 */

import { useEffect, useState, useCallback, useRef } from 'react';
import {
  fetchWatchlist,
  addWatchlist,
  deleteWatchlist,
  fetchStockByCode,
  type WatchlistItem,
} from '../api';
import type { StockResponse } from '../types';

interface WatchlistViewProps {
  selectedCode?: string | null;
  onSelectCode?: (code: string) => void;
}

/** 自选股展示行：watchlist 元数据 + 行情快照 */
interface WatchlistRow {
  watchlist: WatchlistItem;
  quote: StockResponse | null;
}

export default function WatchlistView({
  selectedCode: _selectedCode,
  onSelectCode,
}: WatchlistViewProps = {}) {
  const [rows, setRows] = useState<WatchlistRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [addInput, setAddInput] = useState('');
  const [toast, setToast] = useState<{ type: 'success' | 'error'; msg: string } | null>(null);

  const abortRef = useRef<AbortController | null>(null);

  // toast 自动消失
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 2500);
    return () => clearTimeout(t);
  }, [toast]);

  /**
   * 加载自选股列表 + 行情
   */
  const loadWatchlist = useCallback(async () => {
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    setLoading(true);
    setError(null);
    try {
      const wlResp = await fetchWatchlist('default', ctrl.signal);
      if (ctrl.signal.aborted) return;
      if (wlResp.code !== 200 || !wlResp.data) {
        setError(wlResp.message || '加载自选股失败');
        setRows([]);
        return;
      }
      const items = wlResp.data;
      if (items.length === 0) {
        setRows([]);
        return;
      }

      // 对每只股票拉行情（N+1，自选股数量小可接受）
      const quotes = await Promise.all(
        items.map((it) =>
          fetchStockByCode(it.code, ctrl.signal)
            .then((r) => (r?.code === 200 ? r.data : null))
            .catch(() => null)
        )
      );
      if (ctrl.signal.aborted) return;
      setRows(
        items.map((it, i) => ({
          watchlist: it,
          quote: quotes[i] ?? null,
        }))
      );
    } catch (e) {
      if (e instanceof Error && e.name === 'AbortError') return;
      setError(e instanceof Error ? e.message : '网络错误');
      setRows([]);
    } finally {
      if (!ctrl.signal.aborted) setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadWatchlist();
    return () => abortRef.current?.abort();
  }, [loadWatchlist]);

  /**
   * 添加自选股
   */
  const handleAdd = async () => {
    const code = addInput.trim();
    if (!/^\d{6}$/.test(code)) {
      setToast({ type: 'error', msg: '请输入 6 位股票代码（如 000001）' });
      return;
    }
    setAdding(true);
    try {
      const resp = await addWatchlist(code, '默认分组');
      if (resp.code === 200) {
        setToast({ type: 'success', msg: `已添加 ${code} 到自选` });
        setAddInput('');
        await loadWatchlist();
      } else if (resp.code === 409) {
        setToast({ type: 'error', msg: `股票 ${code} 已在自选股中` });
      } else {
        setToast({ type: 'error', msg: resp.message || '添加失败' });
      }
    } catch (e) {
      setToast({ type: 'error', msg: e instanceof Error ? e.message : '网络错误' });
    } finally {
      setAdding(false);
    }
  };

  /**
   * 移除自选股
   */
  const handleRemove = async (code: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      const resp = await deleteWatchlist(code);
      if (resp.code === 200) {
        setToast({ type: 'success', msg: `已移除 ${code}` });
        // 本地乐观更新
        setRows((prev) => prev.filter((r) => r.watchlist.code !== code));
      } else {
        setToast({ type: 'error', msg: resp.message || '移除失败' });
      }
    } catch (err) {
      setToast({ type: 'error', msg: err instanceof Error ? err.message : '网络错误' });
    }
  };

  return (
    <div className="flex flex-col h-full relative">
      <div className="flex-1 overflow-hidden flex flex-col">
        {/* 顶部工具栏：标题 + 添加输入 + 添加按钮 */}
        <div className="flex items-center justify-between p-4 border-b border-border-color bg-bg-secondary gap-4">
          <h3 className="text-text-primary font-medium text-lg whitespace-nowrap">
            ⭐ 我的自选股
            <span className="text-text-muted text-sm ml-2">({rows.length} 只)</span>
          </h3>
          <div className="flex items-center gap-2 flex-1 max-w-md">
            <input
              type="text"
              value={addInput}
              onChange={(e) => setAddInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleAdd()}
              placeholder="输入 6 位股票代码"
              maxLength={6}
              className="flex-1 bg-bg-card border border-border-color text-text-primary text-sm px-3 py-2 rounded focus:outline-none focus:border-up-green"
              disabled={adding}
            />
            <button
              onClick={handleAdd}
              disabled={adding || addInput.length === 0}
              className="bg-up-green text-white px-4 py-2 rounded text-sm hover:opacity-90 transition-opacity disabled:opacity-50 whitespace-nowrap"
            >
              {adding ? '添加中…' : '添加自选'}
            </button>
          </div>
        </div>

        {/* 主体：列表 / Loading / Error / Empty */}
        <div className="flex-1 overflow-auto">
          {loading && rows.length === 0 ? (
            <div className="p-8 text-center text-text-muted text-sm">加载中…</div>
          ) : error ? (
            <div className="p-8 text-center">
              <p className="text-down-red text-sm mb-2">加载失败</p>
              <p className="text-text-muted text-xs">{error}</p>
              <button
                onClick={loadWatchlist}
                className="mt-3 bg-bg-card border border-border-color text-text-primary text-xs px-3 py-1.5 rounded hover:bg-bg-primary"
              >
                重试
              </button>
            </div>
          ) : rows.length === 0 ? (
            <div className="p-8 text-center text-text-muted text-sm">
              暂无自选股，请在上方输入 6 位股票代码添加
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-bg-secondary border-b border-border-color">
                <tr>
                  <th className="text-left px-4 py-3 text-text-muted font-medium">代码</th>
                  <th className="text-left px-4 py-3 text-text-muted font-medium">名称</th>
                  <th className="text-right px-4 py-3 text-text-muted font-medium">最新价</th>
                  <th className="text-right px-4 py-3 text-text-muted font-medium">涨跌额</th>
                  <th className="text-right px-4 py-3 text-text-muted font-medium">涨跌幅%</th>
                  <th className="text-left px-4 py-3 text-text-muted font-medium">分组</th>
                  <th className="text-center px-4 py-3 text-text-muted font-medium">操作</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-color/50">
                {rows.map(({ watchlist: w, quote }) => {
                  const close = quote?.close ?? null;
                  const change = quote?.change ?? null;
                  const changePct = quote?.change_pct ?? null;
                  return (
                    <tr
                      key={w.code}
                      className="hover:bg-bg-card transition-colors cursor-pointer"
                      onClick={() => onSelectCode?.(w.code)}
                      title="点击查看详情"
                    >
                      <td className="px-4 py-3 text-blue-400 hover:underline">{w.code}</td>
                      <td className="px-4 py-3 text-text-primary">
                        {quote?.stock_name ?? <span className="text-text-muted">—</span>}
                      </td>
                      <td className="px-4 py-3 font-mono text-right text-text-primary">
                        {close !== null ? close.toFixed(2) : '-'}
                      </td>
                      <td
                        className={`px-4 py-3 font-mono text-right ${
                          (change ?? 0) >= 0 ? 'text-up-green' : 'text-down-red'
                        }`}
                      >
                        {change !== null
                          ? `${change >= 0 ? '+' : ''}${change.toFixed(2)}`
                          : '-'}
                      </td>
                      <td
                        className={`px-4 py-3 font-mono text-right ${
                          (changePct ?? 0) >= 0 ? 'text-up-green' : 'text-down-red'
                        }`}
                      >
                        {changePct !== null
                          ? `${changePct >= 0 ? '+' : ''}${changePct.toFixed(2)}%`
                          : '-'}
                      </td>
                      <td className="px-4 py-3 text-text-muted text-xs">{w.group_name}</td>
                      <td className="px-4 py-3 text-center">
                        <button
                          onClick={(e) => handleRemove(w.code, e)}
                          className="text-text-muted hover:text-down-red text-sm"
                        >
                          移除
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* Toast 提示 */}
      {toast && (
        <div
          className={`fixed bottom-6 left-1/2 -translate-x-1/2 px-4 py-2 rounded text-sm z-50 ${
            toast.type === 'success'
              ? 'bg-up-green text-white'
              : 'bg-down-red text-white'
          }`}
        >
          {toast.msg}
        </div>
      )}
    </div>
  );
}
