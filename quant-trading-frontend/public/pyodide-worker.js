/**
 * Pyodide Worker
 * 在 Web Worker 中加载 CPython 解释器（WASM），执行用户自编指标脚本。
 *
 * 协议：
 *   Main → Worker:   { type, batchId, scripts, timeoutMs }
 *   Worker → Main:   { type, batchId, ... }
 *
 * 状态机：
 *   loading → ready → (executing → ready)* → terminated
 */
self.importScripts('/pyodide/pyodide.js');

/** @type {any} */
let pyodide = null;
let ready = false;
let abortController = null;

// ---- 初始化 ----

async function init() {
  try {
    pyodide = await self.loadPyodide({
      indexURL: '/pyodide/',
    });
    // 预加载常用科学计算库（按需加载，不阻塞初始化）
    pyodide.loadPackage(['numpy', 'pandas']).catch(err => {
      console.warn('Pyodide 预加载 numpy/pandas 失败:', err.message);
    });
    ready = true;
    self.postMessage({ type: 'ready' });
  } catch (err) {
    self.postMessage({ type: 'error', error: 'Pyodide 初始化失败: ' + err.message });
  }
}

init();

// ---- 脚本执行 ----

/**
 * 执行单条脚本，返回结果矩阵。
 * 脚本入参: close, high, low, open, volume (均为 list[list[float]], 股票×天数)
 * 脚本返回值: list[list[float]] 或 list[float]
 */
async function executeScript(scriptCode, stockData, signal) {
  const { close, high, low, open, volume } = stockData;

  // 构建安全的 globals 上下文
  const code = `
import json, math, sys

# 允许的库白名单检查
_allowed_modules = {'numpy', 'pandas', 'math', 'json', 'itertools', 'collections', 'statistics', 'typing', 'datetime'}

def calculate(close, high, low, open, volume):
    # 用户实现
    pass

${scriptCode}

# 执行
_result = calculate(close, high, low, open, volume)
`;

  // 传入数据到 Python 全局
  const globals = {
    close: close,
    high: high,
    low: low,
    open: open,
    volume: volume,
    __builtins__: pyodide.globals.get('__builtins__'),
  };

  try {
    // 在独立 globals 中执行
    const pyGlobals = pyodide.toPy(globals);
    pyodide.runPython(code, { globals: pyGlobals });
    const result = pyGlobals.get('_result');

    // 释放 Python 对象
    pyGlobals.destroy();

    if (result === null || result === undefined) {
      return null;
    }

    // 转换为 JS 数组
    const jsResult = result.toJs();
    result.destroy();
    return jsResult;
  } catch (err) {
    throw new Error('脚本执行错误: ' + err.message);
  }
}

/**
 * 检查脚本安全性（import 白名单）
 */
function validateScript(code) {
  const importRegex = /^(?:from\s+(\S+)\s+)?import\s+(\S+)/gm;
  let match;
  const allowed = new Set(['numpy', 'pandas', 'math', 'json', 'itertools', 'collections', 'statistics', 'typing', 'datetime']);
  while ((match = importRegex.exec(code)) !== null) {
    const module = match[1] || match[2].split('.')[0];
    if (!allowed.has(module)) {
      throw new Error('导入不被允许的模块: ' + module + '（仅允许: ' + Array.from(allowed).join(', ') + '）');
    }
  }
}

// ---- 消息处理 ----

self.onmessage = async function (event) {
  const { type, batchId, scripts, timeoutMs } = event.data;

  if (type === 'execute') {
    if (!ready) {
      self.postMessage({ type: 'error', batchId, error: 'Pyodide 尚未就绪' });
      return;
    }

    abortController = new AbortController();
    const signal = abortController.signal;

    // 设置超时
    const timeout = setTimeout(() => {
      if (abortController) {
        abortController.abort();
        self.postMessage({ type: 'error', batchId, error: '脚本执行超时（' + (timeoutMs || 5000) + 'ms）' });
      }
    }, timeoutMs || 5000);

    try {
      const results = [];
      for (let i = 0; i < scripts.length; i++) {
        if (signal.aborted) break;

        const { id, code, stockData } = scripts[i];
        try {
          validateScript(code);
          const values = await executeScript(code, stockData, signal);
          results.push({ id, values, error: null });
        } catch (err) {
          results.push({ id, values: null, error: err.message });
        }

        // 报告进度
        self.postMessage({
          type: 'progress',
          batchId,
          total: scripts.length,
          done: i + 1,
        });
      }

      clearTimeout(timeout);
      if (!signal.aborted) {
        self.postMessage({ type: 'result', batchId, results });
      }
    } catch (err) {
      clearTimeout(timeout);
      self.postMessage({ type: 'error', batchId, error: err.message });
    }
  } else if (type === 'terminate') {
    self.close();
  }
};