/**
 * Pyodide Worker
 * 在 Web Worker 中加载 CPython 解释器（WASM），执行用户自编指标脚本。
 */
self.importScripts('/pyodide/pyodide.js');

let pyodide = null;
let ready = false;
let abortController = null;

async function init() {
  try {
    pyodide = await self.loadPyodide({
      indexURL: '/pyodide/',
    });
    await pyodide.loadPackage(['numpy']);
    ready = true;
    self.postMessage({ type: 'ready' });
  } catch (err) {
    console.error('[pyodide-worker] 初始化失败:', err);
    self.postMessage({ type: 'error', error: 'Pyodide 初始化失败: ' + err.message });
  }
}

init();

function toJsValue(pyResult) {
  if (pyResult === null || pyResult === undefined) {
    return null;
  }
  if (typeof pyResult === 'object' && typeof pyResult.toJs === 'function') {
    const jsVal = pyResult.toJs();
    if (typeof pyResult.destroy === 'function') {
      pyResult.destroy();
    }
    return jsVal;
  }
  return pyResult;
}

async function executeScript(scriptCode, stockData, signal) {
  const { close, high, low, open, volume } = stockData;

  const needsNumpy = /\bnumpy\b/.test(scriptCode) || /\bnp\./.test(scriptCode);
  const needsPandas = /\bpandas\b/.test(scriptCode) || /\bpd\./.test(scriptCode);
  if (needsNumpy || needsPandas) {
    const pkgs = [];
    if (needsNumpy) pkgs.push('numpy');
    if (needsPandas) pkgs.push('pandas');
    await pyodide.loadPackage(pkgs);
  }

  const code = `
def calculate(open_prices, high_prices, low_prices, close_prices, volumes):
    return 0

${scriptCode}

def _calculate_single(o, h, l, c, v):
    try:
        import sys
        def _type_name(x):
            return type(x).__name__
        def _safe_len(x):
            try:
                return len(x)
            except:
                return -1
        # 调试：打印参数类型和长度（仅第一只股票）
        if not hasattr(_calculate_single, '_debug_printed'):
            _calculate_single._debug_printed = True
            print(f'[DEBUG] o type={_type_name(o)}, len={_safe_len(o)}, first3={list(o[:3]) if _safe_len(o) > 0 else "N/A"}')
            print(f'[DEBUG] h type={_type_name(h)}, len={_safe_len(h)}, first3={list(h[:3]) if _safe_len(h) > 0 else "N/A"}')
            print(f'[DEBUG] l type={_type_name(l)}, len={_safe_len(l)}, first3={list(l[:3]) if _safe_len(l) > 0 else "N/A"}')
            print(f'[DEBUG] c type={_type_name(c)}, len={_safe_len(c)}, first3={list(c[:3]) if _safe_len(c) > 0 else "N/A"}')
            print(f'[DEBUG] v type={_type_name(v)}, len={_safe_len(v)}, first3={list(v[:3]) if _safe_len(v) > 0 else "N/A"}')
            sys.stdout.flush()
        result = calculate(o, h, l, c, v)
        if isinstance(result, (int, float)):
            return result
        elif isinstance(result, list):
            return result
        else:
            return float(result) if result else 0
    except Exception as e:
        import traceback
        return '__ERROR__:' + traceback.format_exc()
`;

  try {
    pyodide.runPython(code);
    const calcFunc = pyodide.globals.get('_calculate_single');

    const numStocks = close.length;
    const results = [];
    
    // JS 端调试：打印第一只股票的数据结构
    if (numStocks > 0) {
      console.log('[pyodide-worker] 数据结构调试:', {
        股票数: numStocks,
        close_是否二维数组: Array.isArray(close) && Array.isArray(close[0]),
        close_第一只长度: close[0]?.length,
        close_第一只前3个值: close[0]?.slice(0, 3),
        open_第一只前3个值: open[0]?.slice(0, 3),
      });
    }
    
    for (let i = 0; i < numStocks; i++) {
      if (signal && signal.aborted) break;
      const o = open[i] || [];
      const h = high[i] || [];
      const l = low[i] || [];
      const c = close[i] || [];
      const v = volume[i] || [];

      try {
        const pyResult = calcFunc(
          pyodide.toPy(o),
          pyodide.toPy(h),
          pyodide.toPy(l),
          pyodide.toPy(c),
          pyodide.toPy(v)
        );
        const jsResult = toJsValue(pyResult);
        
        if (typeof jsResult === 'string' && jsResult.startsWith('__ERROR__:')) {
          console.error('[pyodide-worker] Python执行错误:', jsResult.substring(10));
          results.push(null);
        } else {
          results.push(jsResult);
        }
      } catch (err) {
        console.error('[pyodide-worker] JS执行错误:', err.message);
        results.push(null);
      }
    }

    return results;
  } catch (err) {
    console.error('[pyodide-worker] 脚本加载错误:', err.message);
    throw new Error('脚本加载错误: ' + err.message);
  }
}

function validateScript(code) {
  const importRegex = /^(?:from\s+(\S+)\s+)?import\s+(\S+)/gm;
  let match;
  const allowed = new Set(['numpy', 'pandas', 'math', 'json', 'itertools', 'collections', 'statistics', 'typing', 'datetime']);
  while ((match = importRegex.exec(code)) !== null) {
    const module = match[1] || match[2].split('.')[0];
    if (!allowed.has(module)) {
      throw new Error('导入不被允许的模块: ' + module);
    }
  }
}

self.onmessage = async function (event) {
  const { type, batchId, scripts, timeoutMs } = event.data;

  if (type === 'execute') {
    if (!ready) {
      self.postMessage({ type: 'error', batchId, error: 'Pyodide 尚未就绪' });
      return;
    }

    abortController = new AbortController();
    const signal = abortController.signal;

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