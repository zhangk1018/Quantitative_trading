/**
 * 自编指标脚本存储 — localStorage CRUD + 版本控制
 *
 * 存储结构（localStorage）:
 *   custom_scripts_index: string[]                    ← 所有脚本 ID 列表
 *   custom_script_{id}: string                        ← 脚本元数据 JSON
 *
 * 脚本元数据:
 *   { id, name, version, code, createdAt, updatedAt }
 *
 * 版本控制:
 *   每次保存 version +1，用作缓存失效键 cacheKey = `${id}_v${version}`
 */

const STORAGE_KEY_INDEX = 'custom_scripts_index';

export interface CustomScriptMeta {
  id: string;
  name: string;
  version: number;
  createdAt: number;
  updatedAt: number;
}

export interface CustomScript extends CustomScriptMeta {
  code: string;
}

// ---- 工具 ----

function generateId(): string {
  return 'cs_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 8);
}

function scriptStorageKey(id: string): string {
  return `custom_script_${id}`;
}

// ---- 索引 ----

function loadIndex(): string[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY_INDEX);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function saveIndex(index: string[]): void {
  localStorage.setItem(STORAGE_KEY_INDEX, JSON.stringify(index));
}

// ---- CRUD ----

/** 获取所有脚本的元数据列表（不含 code） */
export function listScripts(): CustomScriptMeta[] {
  const index = loadIndex();
  const result: CustomScriptMeta[] = [];
  for (const id of index) {
    try {
      const raw = localStorage.getItem(scriptStorageKey(id));
      if (raw) {
        const script = JSON.parse(raw) as CustomScript;
        const { code, ...meta } = script;
        result.push(meta);
      }
    } catch {
      // 损坏数据跳过
    }
  }
  return result;
}

/** 获取单个脚本（含 code） */
export function getScript(id: string): CustomScript | null {
  try {
    const raw = localStorage.getItem(scriptStorageKey(id));
    return raw ? (JSON.parse(raw) as CustomScript) : null;
  } catch {
    return null;
  }
}

/** 创建新脚本 */
export function createScript(name: string, code: string): CustomScript {
  const now = Date.now();
  const script: CustomScript = {
    id: generateId(),
    name,
    version: 1,
    code,
    createdAt: now,
    updatedAt: now,
  };

  const index = loadIndex();
  index.push(script.id);
  saveIndex(index);
  localStorage.setItem(scriptStorageKey(script.id), JSON.stringify(script));
  return script;
}

/** 更新脚本（code 变化时 version +1） */
export function updateScript(id: string, name: string, code: string): CustomScript | null {
  const existing = getScript(id);
  if (!existing) return null;

  const now = Date.now();
  const version = existing.code !== code ? existing.version + 1 : existing.version;
  const updated: CustomScript = {
    ...existing,
    name,
    code,
    version,
    updatedAt: now,
  };

  localStorage.setItem(scriptStorageKey(id), JSON.stringify(updated));
  return updated;
}

/** 删除脚本 */
export function deleteScript(id: string): boolean {
  const index = loadIndex();
  const newIndex = index.filter(i => i !== id);
  if (newIndex.length === index.length) return false;

  saveIndex(newIndex);
  localStorage.removeItem(scriptStorageKey(id));
  return true;
}

/** 获取脚本的缓存键 */
export function getScriptCacheKey(id: string): string | null {
  const script = getScript(id);
  if (!script) return null;
  return `${script.id}_v${script.version}`;
}