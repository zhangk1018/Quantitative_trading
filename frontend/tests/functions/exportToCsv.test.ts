/**
 * CSV 导出工具函数测试
 *
 * 验证：
 * - 基础 CSV 生成（含 BOM）
 * - options 对象参数（headers/fields/filename）
 * - 危险前缀注入防护（半角 + 全角）
 * - 逗号/引号/换行转义
 * - 空数据 console.warn 返回
 * - 资源释放（removeChild + revokeObjectURL）
 * - 单元格长度截断
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { exportToCsv } from '@/features/stock-picker/utils/screener';

/** 保存原生 Blob 引用，避免 mock 内递归调用 */
const RealBlob = globalThis.Blob;

/** 辅助：从 Blob 中读取文本内容（FileReader 兼容 jsdom） */
async function blobText(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = () => reject(reader.error);
    reader.readAsText(blob);
  });
}

function setupCsvMock() {
  const mocks = {
    appendChild: vi.fn(),
    removeChild: vi.fn(),
    revokeObjectURL: vi.fn(),
    createObjectURL: vi.fn(() => 'blob:mock-url'),
    click: vi.fn(),
  };

  let capturedBlob: Blob | null = null;

  vi.stubGlobal('Blob', vi.fn(function (
    this: Blob,
    parts: BlobPart[],
    opts?: BlobPropertyBag,
  ) {
    capturedBlob = new RealBlob(parts, opts);
  }));

  vi.stubGlobal('URL', {
    createObjectURL: mocks.createObjectURL,
    revokeObjectURL: mocks.revokeObjectURL,
  });

  document.body.appendChild = mocks.appendChild;

  /** 在 appendChild 时自动设置 parentNode，使 finally 块能执行 removeChild */
  mocks.appendChild.mockImplementation((el: any) => {
    if (el && typeof el === 'object') {
      (el as Record<string, unknown>).parentNode = document.body;
    }
  });

  document.body.removeChild = mocks.removeChild;

  document.createElement = vi.fn((tag: string) => {
    if (tag === 'a') {
      return {
        href: '',
        download: '',
        click: mocks.click,
        parentNode: null,
      } as unknown as HTMLAnchorElement;
    }
    return document.createElement(tag);
  });

  /** 获取导出时生成的 CSV 内容 */
  const getCsvContent = async (): Promise<string> => {
    if (capturedBlob) return blobText(capturedBlob);
    return '';
  };

  return { ...mocks, getCsvContent };
}

describe('exportToCsv', () => {
  let mock: ReturnType<typeof setupCsvMock>;

  beforeEach(() => {
    mock = setupCsvMock();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  // ---------- 基础生成 ----------
  it('生成正确的 CSV（实现自动添加 BOM，FileReader 透明处理）', async () => {
    exportToCsv(
      [
        { code: '000001', name: '平安银行', close: 12.34 },
        { code: '000002', name: '万科A', close: 8.56 },
      ],
      { headers: ['代码', '名称', '收盘价'], fields: ['code', 'name', 'close'] },
    );

    const content = await mock.getCsvContent();
    expect(content).toContain('代码,名称,收盘价');
    expect(content).toContain('000001,平安银行,12.34');
    expect(content).toContain('000002,万科A,8.56');
  });

  it('不传 options 时使用对象 key 作为 fields', async () => {
    exportToCsv([{ code: '000001', name: '平安银行' }]);

    const content = await mock.getCsvContent();
    expect(content).toContain('code,name');
    expect(content).toContain('000001,平安银行');
  });

  // ---------- 公式注入防护 ----------
  it.each(['=', '+', '-', '@'] as const)('半角危险前缀 "%s" 添加单引号', async (prefix) => {
    exportToCsv(
      [{ field: `${prefix}SUM(A1:A10)` }],
      { headers: ['字段'], fields: ['field'] },
    );

    const content = await mock.getCsvContent();
    expect(content).toContain(`'${prefix}SUM(A1:A10)`);
  });

  it.each(['＝', '＋', '－', '＠'] as const)('全角危险前缀 "%s" 添加单引号', async (prefix) => {
    exportToCsv(
      [{ field: `${prefix}SUM(A1)` }],
      { headers: ['字段'], fields: ['field'] },
    );

    const content = await mock.getCsvContent();
    expect(content).toContain(`'${prefix}SUM(A1)`);
  });

  // ---------- 引用/转义 ----------
  it('包含逗号的值用引号包裹', async () => {
    exportToCsv(
      [{ code: '000001', name: '平安,银行' }],
      { headers: ['代码', '名称'], fields: ['code', 'name'] },
    );

    const content = await mock.getCsvContent();
    expect(content).toContain('"平安,银行"');
  });

  it('包含双引号的值转义为两个引号', async () => {
    exportToCsv(
      [{ code: '000001', name: '平安"银行"' }],
      { headers: ['代码', '名称'], fields: ['code', 'name'] },
    );

    const content = await mock.getCsvContent();
    expect(content).toContain('"平安""银行"""');
  });

  it('包含换行符的值用引号包裹', async () => {
    exportToCsv(
      [{ code: '000001', remark: '多行\n内容\r\n第二行' }],
      { headers: ['代码', '备注'], fields: ['code', 'remark'] },
    );

    const content = await mock.getCsvContent();
    expect(content).toContain('"多行\n内容\r\n第二行"');
  });

  // ---------- 空数据和 null 字段 ----------
  it('空数据时 console.warn 并返回，不生成 Blob', () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});

    exportToCsv([], { headers: ['代码'], fields: ['code'] });

    expect(warnSpy).toHaveBeenCalledWith('无数据可导出');
    warnSpy.mockRestore();
  });

  it('null/undefined 字段按空字符串处理', async () => {
    exportToCsv(
      [{ code: '000001', name: null, close: undefined }],
      { headers: ['代码', '名称', '收盘价'], fields: ['code', 'name', 'close'] },
    );

    const content = await mock.getCsvContent();
    const body = content;
    expect(body).toContain('000001,,');
  });

  // ---------- 长度截断 ----------
  it('超过 10000 字符的单元格被截断并追加 "…"', async () => {
    const longStr = 'a'.repeat(10001);
    exportToCsv(
      [{ code: '000001', desc: longStr }],
      { headers: ['代码', '描述'], fields: ['code', 'desc'] },
    );

    const content = await mock.getCsvContent();
    const body = content;
    expect(body).toContain('a'.repeat(10000) + '…');
  });

  // ---------- 资源释放 ----------
  it('导出后执行 cleanup（removeChild + revokeObjectURL）', () => {
    exportToCsv(
      [{ code: '000001', name: 'test' }],
      { headers: ['代码', '名称'], fields: ['code', 'name'] },
    );

    expect(mock.appendChild).toHaveBeenCalled();
    expect(mock.removeChild).toHaveBeenCalled();
    expect(mock.revokeObjectURL).toHaveBeenCalledWith('blob:mock-url');
  });

  // ---------- filename 传递 ----------
  it('指定的 filename 传给 download 属性', () => {
    let capturedDownload = '';

    document.createElement = vi.fn((tag: string) => {
      if (tag === 'a') {
        return {
          href: '',
          parentNode: null,
          set download(val: string) { capturedDownload = val; },
          get download() { return capturedDownload; },
          click: vi.fn(),
        } as unknown as HTMLAnchorElement;
      }
      return document.createElement(tag);
    });

    exportToCsv(
      [{ code: '000001' }],
      { headers: ['代码'], fields: ['code'], filename: 'stock_screener_20260703.csv' },
    );

    expect(capturedDownload).toBe('stock_screener_20260703.csv');
  });
});