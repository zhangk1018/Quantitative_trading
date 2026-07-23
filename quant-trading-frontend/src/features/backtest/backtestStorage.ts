// backtestStorage.ts — IndexedDB 本地存储
// 最多保留 20 条回测结果，FIFO 淘汰
// 支持 schema 版本管理，版本升级时自动迁移

import type { StoredBacktestResult } from './backtestTypes';
import { STORAGE_SCHEMA_VERSION, MAX_STORED_RESULTS } from './constants';

const DB_NAME = 'backtest_results';
const DB_VERSION = 1;
const STORE_NAME = 'results';

function openDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);

    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME, { keyPath: 'id' });
      }
    };

    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

/** 迁移旧版本数据：为缺少 version 字段的记录填充默认值 */
function migrateResult(result: StoredBacktestResult): StoredBacktestResult {
  if (result.version === undefined || result.version === null) {
    return { ...result, version: STORAGE_SCHEMA_VERSION };
  }
  return result;
}

/** 保存回测结果 */
export async function saveResult(result: StoredBacktestResult): Promise<void> {
  try {
    const db = await openDB();
    const tx = db.transaction(STORE_NAME, 'readwrite');
    const store = tx.objectStore(STORE_NAME);

    // 确保 version 字段存在
    const toSave = result.version === undefined || result.version === null
      ? { ...result, version: STORAGE_SCHEMA_VERSION }
      : result;

    // 检查是否超过上限
    const countRequest = store.count();
    const count = await new Promise<number>((resolve, reject) => {
      countRequest.onsuccess = () => resolve(countRequest.result);
      countRequest.onerror = () => reject(countRequest.error);
    });

    if (count >= MAX_STORED_RESULTS) {
      // 删除最旧的一条（FIFO）
      const allRequest = store.getAll();
      const all = await new Promise<StoredBacktestResult[]>((resolve, reject) => {
        allRequest.onsuccess = () => resolve(allRequest.result);
        allRequest.onerror = () => reject(allRequest.error);
      });

      if (all.length > 0) {
        all.sort((a, b) => a.createdAt.localeCompare(b.createdAt));
        store.delete(all[0].id);
      }
    }

    store.put(toSave);

    return new Promise((resolve, reject) => {
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  } catch (err) {
    console.warn('保存回测结果失败:', err);
  }
}

/** 获取所有回测结果（含迁移逻辑） */
export async function getAllResults(): Promise<StoredBacktestResult[]> {
  try {
    const db = await openDB();
    const tx = db.transaction(STORE_NAME, 'readonly');
    const store = tx.objectStore(STORE_NAME);
    const request = store.getAll();

    return new Promise((resolve, reject) => {
      request.onsuccess = () => {
        const results = (request.result as StoredBacktestResult[])
          .map(migrateResult)
          .filter((r) => r.version === STORAGE_SCHEMA_VERSION);
        results.sort((a, b) => b.createdAt.localeCompare(a.createdAt));
        resolve(results);
      };
      request.onerror = () => reject(request.error);
    });
  } catch {
    return [];
  }
}

/** 删除单条结果 */
export async function deleteResult(id: string): Promise<void> {
  try {
    const db = await openDB();
    const tx = db.transaction(STORE_NAME, 'readwrite');
    const store = tx.objectStore(STORE_NAME);
    store.delete(id);

    return new Promise((resolve, reject) => {
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  } catch {
    // ignore
  }
}

/** 清空所有结果 */
export async function clearAllResults(): Promise<void> {
  try {
    const db = await openDB();
    const tx = db.transaction(STORE_NAME, 'readwrite');
    const store = tx.objectStore(STORE_NAME);
    store.clear();

    return new Promise((resolve, reject) => {
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  } catch {
    // ignore
  }
}

/** 获取存储数量 */
export async function getResultCount(): Promise<number> {
  try {
    const db = await openDB();
    const tx = db.transaction(STORE_NAME, 'readonly');
    const store = tx.objectStore(STORE_NAME);
    const request = store.count();

    return new Promise((resolve, reject) => {
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  } catch {
    return 0;
  }
}