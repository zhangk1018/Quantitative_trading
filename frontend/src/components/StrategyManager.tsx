/**
 * StrategyManager.tsx - 选股策略管理抽屉
 *
 * 功能：
 * - 列出所有已保存策略
 * - 加载/重命名/复制/导出/删除策略
 * - 导入预览 Modal（含字段白名单校验）
 * - 支持 JSON 文件 / 短码 / 剪贴板导入
 *
 * 关联设计：docs/design/CUSTOM_INDICATOR_AND_STRATEGY_DESIGN.md
 */

import { useEffect, useRef, useState } from 'react';
import type { ScreenerFilters, Strategy } from '../types';
import { createEmptyStrategy, strategyStorage } from '../utils/strategyStorage';

interface StrategyManagerProps {
  isOpen: boolean;
  onClose: () => void;
  onLoad: (strategy: Strategy) => void;
  currentFilters: ScreenerFilters;
  onSaveCurrent: (strategy: Strategy) => void;
}

// ============================================
// 工具：格式化日期
// ============================================

function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

// ============================================
// 主组件
// ============================================

export default function StrategyManager({
  isOpen,
  onClose,
  onLoad,
  currentFilters,
  onSaveCurrent,
}: StrategyManagerProps) {
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingName, setEditingName] = useState('');
  const [toast, setToast] = useState<{ type: 'success' | 'error' | 'info'; msg: string } | null>(null);

  // 保存当前策略对话框
  const [showSaveDialog, setShowSaveDialog] = useState(false);
  const [newStrategyName, setNewStrategyName] = useState('');

  // 导入预览 Modal
  const [importPreview, setImportPreview] = useState<{
    strategy: Strategy;
    warnings: string[];
  } | null>(null);
  const [importName, setImportName] = useState('');

  // 导入输入对话框
  const [showImportDialog, setShowImportDialog] = useState(false);
  const [importInput, setImportInput] = useState('');

  const fileInputRef = useRef<HTMLInputElement>(null);

  // 加载列表
  useEffect(() => {
    if (isOpen) setStrategies(strategyStorage.list());
  }, [isOpen]);

  // toast 自动消失
  useEffect(() => {
    if (toast) {
      const t = setTimeout(() => setToast(null), 2500);
      return () => clearTimeout(t);
    }
    return;
  }, [toast]);

  // ESC 关闭抽屉
  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [isOpen, onClose]);

  // ============================================
  // 刷新列表
  // ============================================
  const refresh = () => setStrategies(strategyStorage.list());

  // ============================================
  // 保存当前
  // ============================================
  const handleSaveCurrent = () => {
    const name = newStrategyName.trim();
    if (!name) {
      setToast({ type: 'error', msg: '请输入策略名' });
      return;
    }
    const strategy = createEmptyStrategy(name, currentFilters);
    onSaveCurrent(strategy);
    setShowSaveDialog(false);
    setNewStrategyName('');
    refresh();
    setToast({ type: 'success', msg: `已保存：${name}` });
  };

  // ============================================
  // 加载
  // ============================================
  const handleLoad = (s: Strategy) => {
    onLoad(s);
    onClose();
    setToast({ type: 'success', msg: `已加载：${s.name}` });
  };

  // ============================================
  // 重命名
  // ============================================
  const startRename = (s: Strategy) => {
    setEditingId(s.id);
    setEditingName(s.name);
  };
  const commitRename = () => {
    if (!editingId) return;
    const name = editingName.trim();
    if (!name) {
      setToast({ type: 'error', msg: '策略名不能为空' });
      return;
    }
    const s = strategyStorage.get(editingId);
    if (s) {
      strategyStorage.save({ ...s, name });
      refresh();
      setToast({ type: 'success', msg: '已重命名' });
    }
    setEditingId(null);
  };

  // ============================================
  // 复制
  // ============================================
  const handleDuplicate = (s: Strategy) => {
    const copy: Strategy = {
      ...s,
      id: crypto.randomUUID(),
      name: `${s.name} (副本)`,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    };
    strategyStorage.save(copy);
    refresh();
    setToast({ type: 'success', msg: `已复制：${copy.name}` });
  };

  // ============================================
  // 导出（菜单：复制短码 / 下载 .json）
  // ============================================
  const handleExport = async (s: Strategy, format: 'shortcode' | 'file') => {
    try {
      if (format === 'shortcode') {
        await strategyStorage.copyShortCodeToClipboard(s.id);
        setToast({ type: 'success', msg: '短码已复制到剪贴板' });
      } else {
        strategyStorage.downloadAsFile(s.id);
        setToast({ type: 'success', msg: '已下载 .json 文件' });
      }
    } catch (err) {
      setToast({ type: 'error', msg: (err as Error).message });
    }
  };

  // ============================================
  // 删除
  // ============================================
  const handleDelete = (s: Strategy) => {
    if (!confirm(`确认删除策略"${s.name}"？此操作不可恢复。`)) return;
    strategyStorage.delete(s.id);
    refresh();
    setToast({ type: 'info', msg: '已删除' });
  };

  // ============================================
  // 导入：JSON 字符串 / 短码
  // ============================================
  const handleImportSubmit = () => {
    try {
      const result = strategyStorage.import(importInput);
      setImportName(result.strategy.name);
      setImportPreview(result);
      setShowImportDialog(false);
      setImportInput('');
    } catch (err) {
      setToast({ type: 'error', msg: (err as Error).message });
    }
  };

  // ============================================
  // 导入：文件
  // ============================================
  const handleFileImport = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      const text = String(ev.target?.result ?? '');
      try {
        const result = strategyStorage.import(text);
        setImportName(result.strategy.name);
        setImportPreview(result);
      } catch (err) {
        setToast({ type: 'error', msg: (err as Error).message });
      }
    };
    reader.readAsText(file);
    // 清空以便同一文件可重复导入
    e.target.value = '';
  };

  // ============================================
  // 确认导入
  // ============================================
  const confirmImport = () => {
    if (!importPreview) return;
    const name = importName.trim() || importPreview.strategy.name;
    const final: Strategy = { ...importPreview.strategy, name };
    strategyStorage.save(final);
    refresh();
    setToast({ type: 'success', msg: `导入成功：${name}` });
    setImportPreview(null);
    onLoad(final);
    onClose();
  };

  // ============================================
  // 渲染：抽屉
  // ============================================
  if (!isOpen) return null;

  return (
    <>
      {/* 背景遮罩 */}
      <div
        className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm transition-opacity"
        onClick={onClose}
      />

      {/* 右侧抽屉 */}
      <div className="fixed inset-y-0 right-0 z-50 w-[480px] max-w-[90vw] bg-bg-secondary border-l border-border-color shadow-2xl flex flex-col animate-slide-in">
        {/* 头部 */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-border-color bg-bg-primary">
          <div className="flex items-center gap-2">
            <span className="text-lg">📂</span>
            <h2 className="text-text-primary font-semibold text-base">我的策略</h2>
            <span className="text-text-muted text-xs ml-1">共 {strategies.length} 条</span>
          </div>
          <button
            onClick={onClose}
            className="text-text-muted hover:text-text-primary transition-colors text-xl leading-none w-8 h-8 flex items-center justify-center rounded hover:bg-bg-card"
            aria-label="关闭"
          >
            ×
          </button>
        </div>

        {/* 操作栏 */}
        <div className="flex items-center gap-2 px-5 py-3 border-b border-border-color">
          <button
            onClick={() => setShowSaveDialog(true)}
            className="flex items-center gap-1.5 bg-up-green text-white text-sm px-3 py-1.5 rounded hover:opacity-90 transition-opacity"
          >
            <span>💾</span>保存当前
          </button>
          <button
            onClick={() => setShowImportDialog(true)}
            className="flex items-center gap-1.5 bg-bg-card border border-border-color text-text-primary text-sm px-3 py-1.5 rounded hover:bg-bg-primary transition-colors"
          >
            <span>📥</span>导入
          </button>
          <button
            onClick={() => fileInputRef.current?.click()}
            className="flex items-center gap-1.5 bg-bg-card border border-border-color text-text-secondary text-sm px-3 py-1.5 rounded hover:bg-bg-primary transition-colors"
            title="从 .json 文件导入"
          >
            <span>📁</span>文件
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".json,application/json"
            onChange={handleFileImport}
            className="hidden"
          />
        </div>

        {/* 列表 */}
        <div className="flex-1 overflow-auto">
          {strategies.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-text-muted text-sm px-6 py-12">
              <div className="text-5xl mb-3 opacity-40">📋</div>
              <div>暂无保存的策略</div>
              <div className="mt-1 text-xs">点击"保存当前"开始你的第一个策略</div>
            </div>
          ) : (
            <ul className="divide-y divide-border-color/50">
              {strategies.map((s) => (
                <li
                  key={s.id}
                  className="px-5 py-4 hover:bg-bg-card/50 transition-colors group"
                >
                  {/* 标题行 */}
                  <div className="flex items-start justify-between gap-2">
                    {editingId === s.id ? (
                      <input
                        value={editingName}
                        onChange={(e) => setEditingName(e.target.value)}
                        onBlur={commitRename}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') commitRename();
                          if (e.key === 'Escape') setEditingId(null);
                        }}
                        className="flex-1 bg-bg-primary border border-up-green rounded px-2 py-1 text-text-primary text-sm focus:outline-none"
                        autoFocus
                      />
                    ) : (
                      <div
                        className="flex-1 min-w-0 cursor-text"
                        onDoubleClick={() => startRename(s)}
                        title="双击重命名"
                      >
                        <div className="text-text-primary font-medium text-sm truncate">
                          {s.name}
                        </div>
                        <div className="text-text-muted text-xs mt-0.5">
                          {s.author ?? '匿名'} · {formatDate(s.updatedAt)}
                        </div>
                      </div>
                    )}
                  </div>

                  {/* 摘要 */}
                  <div className="text-text-secondary text-xs mt-1.5 leading-relaxed">
                    <span className="text-text-muted">
                      {s.filters.boards.length}板块 · {s.filters.industries.length}行业 ·{' '}
                      {s.filters.patterns.length}形态 · Top {s.filters.topN}
                    </span>
                  </div>

                  {/* 操作按钮 */}
                  <div className="flex items-center gap-1 mt-2.5">
                    <button
                      onClick={() => handleLoad(s)}
                      className="flex items-center gap-1 bg-up-green/20 text-up-green text-xs px-2.5 py-1 rounded hover:bg-up-green/30 transition-colors"
                    >
                      ▶ 加载
                    </button>
                    <button
                      onClick={() => startRename(s)}
                      className="flex items-center gap-1 text-text-secondary text-xs px-2.5 py-1 rounded hover:bg-bg-primary hover:text-text-primary transition-colors"
                    >
                      ✏ 重命名
                    </button>
                    <button
                      onClick={() => handleDuplicate(s)}
                      className="flex items-center gap-1 text-text-secondary text-xs px-2.5 py-1 rounded hover:bg-bg-primary hover:text-text-primary transition-colors"
                    >
                      📋 复制
                    </button>
                    <button
                      onClick={() => handleExport(s, 'shortcode')}
                      className="flex items-center gap-1 text-text-secondary text-xs px-2.5 py-1 rounded hover:bg-bg-primary hover:text-text-primary transition-colors"
                    >
                      📤 短码
                    </button>
                    <button
                      onClick={() => handleExport(s, 'file')}
                      className="flex items-center gap-1 text-text-secondary text-xs px-2.5 py-1 rounded hover:bg-bg-primary hover:text-text-primary transition-colors"
                    >
                      💾 文件
                    </button>
                    <button
                      onClick={() => handleDelete(s)}
                      className="flex items-center gap-1 text-text-muted text-xs px-2 py-1 rounded hover:bg-down-red/20 hover:text-down-red transition-colors ml-auto"
                    >
                      🗑
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* 底部 */}
        <div className="px-5 py-2.5 border-t border-border-color text-text-muted text-xs flex items-center justify-between">
          <span>数据存储在浏览器 localStorage</span>
          <span>上限 50 条</span>
        </div>
      </div>

      {/* 保存当前策略对话框 */}
      {showSaveDialog && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="bg-bg-secondary border border-border-color rounded-lg w-[420px] shadow-2xl">
            <div className="px-5 py-4 border-b border-border-color">
              <h3 className="text-text-primary font-semibold">💾 保存当前策略</h3>
            </div>
            <div className="p-5">
              <label className="text-text-secondary text-xs block mb-2">策略名</label>
              <input
                value={newStrategyName}
                onChange={(e) => setNewStrategyName(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSaveCurrent()}
                placeholder="例如：价值低估"
                className="w-full bg-bg-primary border border-border-color rounded px-3 py-2 text-text-primary text-sm focus:outline-none focus:border-up-green"
                autoFocus
              />
              <div className="text-text-muted text-xs mt-2">
                即将保存: {currentFilters.boards.length}板块 · {currentFilters.industries.length}行业
                · {currentFilters.patterns.length}形态 · Top {currentFilters.topN}
              </div>
            </div>
            <div className="px-5 py-3 border-t border-border-color flex justify-end gap-2">
              <button
                onClick={() => {
                  setShowSaveDialog(false);
                  setNewStrategyName('');
                }}
                className="px-4 py-1.5 text-text-secondary text-sm hover:text-text-primary transition-colors"
              >
                取消
              </button>
              <button
                onClick={handleSaveCurrent}
                className="px-4 py-1.5 bg-up-green text-white text-sm rounded hover:opacity-90 transition-opacity"
              >
                保存
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 导入输入对话框 */}
      {showImportDialog && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="bg-bg-secondary border border-border-color rounded-lg w-[520px] shadow-2xl">
            <div className="px-5 py-4 border-b border-border-color">
              <h3 className="text-text-primary font-semibold">📥 导入策略</h3>
              <p className="text-text-muted text-xs mt-1">支持 JSON 字符串 / Base64 短码</p>
            </div>
            <div className="p-5">
              <textarea
                value={importInput}
                onChange={(e) => setImportInput(e.target.value)}
                placeholder='粘贴 JSON 或短码...'
                rows={6}
                className="w-full bg-bg-primary border border-border-color rounded px-3 py-2 text-text-primary text-xs font-mono focus:outline-none focus:border-up-green resize-none"
              />
            </div>
            <div className="px-5 py-3 border-t border-border-color flex justify-end gap-2">
              <button
                onClick={() => {
                  setShowImportDialog(false);
                  setImportInput('');
                }}
                className="px-4 py-1.5 text-text-secondary text-sm hover:text-text-primary transition-colors"
              >
                取消
              </button>
              <button
                onClick={handleImportSubmit}
                className="px-4 py-1.5 bg-up-green text-white text-sm rounded hover:opacity-90 transition-opacity"
              >
                解析预览
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 导入预览 Modal */}
      {importPreview && (
        <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="bg-bg-secondary border border-border-color rounded-lg w-[480px] shadow-2xl">
            <div className="px-5 py-4 border-b border-border-color">
              <h3 className="text-text-primary font-semibold">导入策略预览</h3>
              <p className="text-text-muted text-xs mt-1">
                {importPreview.strategy.author ?? '匿名'} ·{' '}
                {formatDate(importPreview.strategy.createdAt)}
              </p>
            </div>
            <div className="p-5 space-y-2 max-h-[400px] overflow-auto">
              {importPreview.warnings.length === 0 ? (
                <div className="text-text-secondary text-sm flex items-center gap-2">
                  <span className="text-up-green">✅</span>所有字段校验通过
                </div>
              ) : null}

              {/* 字段有效性分类 */}
              {importPreview.warnings.length > 0 && (
                <div className="text-warning text-xs flex items-start gap-2 bg-warning/10 px-3 py-2 rounded">
                  <span>⚠️</span>
                  <div className="flex-1">
                    <div className="font-medium mb-1">有 {importPreview.warnings.length} 个警告</div>
                    {importPreview.warnings.map((w, i) => (
                      <div key={i} className="text-warning/80">
                        • {w}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className="space-y-1.5 text-sm pt-2">
                <div className="text-up-green">✅ 上市地: {importPreview.strategy.filters.boards.length} 项</div>
                <div className="text-up-green">
                  ✅ 行业: {importPreview.strategy.filters.industries.length} 项
                </div>
                <div className="text-up-green">
                  ✅ 形态: {importPreview.strategy.filters.patterns.length} 项
                </div>
                <div className="text-up-green">
                  ✅ 排序: {importPreview.strategy.filters.sortBy}{' '}
                  {importPreview.strategy.filters.sortOrder.toUpperCase()} · Top{' '}
                  {importPreview.strategy.filters.topN}
                </div>
              </div>

              <div className="pt-3">
                <label className="text-text-secondary text-xs block mb-2">策略名（可改）</label>
                <input
                  value={importName}
                  onChange={(e) => setImportName(e.target.value)}
                  className="w-full bg-bg-primary border border-border-color rounded px-3 py-2 text-text-primary text-sm focus:outline-none focus:border-up-green"
                />
              </div>
            </div>
            <div className="px-5 py-3 border-t border-border-color flex justify-end gap-2">
              <button
                onClick={() => setImportPreview(null)}
                className="px-4 py-1.5 text-text-secondary text-sm hover:text-text-primary transition-colors"
              >
                取消
              </button>
              <button
                onClick={confirmImport}
                className="px-4 py-1.5 bg-up-green text-white text-sm rounded hover:opacity-90 transition-opacity"
              >
                导入并使用
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Toast */}
      {toast && (
        <div
          className={`fixed bottom-6 left-1/2 -translate-x-1/2 z-[80] px-4 py-2.5 rounded-lg shadow-2xl text-sm flex items-center gap-2 animate-fade-in ${
            toast.type === 'success'
              ? 'bg-up-green text-white'
              : toast.type === 'error'
                ? 'bg-down-red text-white'
                : 'bg-bg-card text-text-primary border border-border-color'
          }`}
        >
          {toast.type === 'success' && <span>✅</span>}
          {toast.type === 'error' && <span>❌</span>}
          {toast.type === 'info' && <span>ℹ️</span>}
          {toast.msg}
        </div>
      )}

      {/* 抽屉滑入动画 */}
      <style>{`
        @keyframes slide-in {
          from { transform: translateX(100%); }
          to { transform: translateX(0); }
        }
        @keyframes fade-in {
          from { opacity: 0; transform: translateX(-50%) translateY(10px); }
          to { opacity: 1; transform: translateX(-50%) translateY(0); }
        }
        .animate-slide-in { animation: slide-in 0.25s ease-out; }
        .animate-fade-in { animation: fade-in 0.2s ease-out; }
      `}</style>
    </>
  );
}
