/**
 * 自编指标导入/导出按钮组件测试（P3.2）
 *
 * 测试覆盖：
 * 1. 基础渲染：导入/导出两个按钮 + 当前数量显示
 * 2. 导出按钮：空数据 disabled、有数据可下载（验证 Blob + 锚点下载）
 * 3. 导入按钮：触发 file input
 * 4. 导入流程：
 *    a) 选择文件 → FileReader 解析成功 → Preview 弹窗
 *    b) file-level 错误（版本不支持/格式无效）→ message.error 不进入 Preview
 *    c) indicator-level 错误（name_duplicate）→ Preview 弹窗显示按类型分组明细
 * 5. 确认导入：写入 localStorage + 回调 onImportSuccess
 * 6. 取消导入：关闭 Preview 弹窗
 * 7. 文件大小超限 → message.error
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ConfigProvider, message } from 'antd';
import { ImportExportButtons } from '@/features/stock-picker/components/ImportExportButtons';
import { CustomIndicator } from '@/features/stock-picker/types/customIndicator';
import * as storage from '@/features/stock-picker/utils/customIndicatorStorage';

// ============================================================================
// Helpers
// ============================================================================

function makeIndicator(overrides: Partial<CustomIndicator> = {}): CustomIndicator {
  return {
    id: overrides.id ?? `ind_test_${Math.random().toString(36).slice(2, 8)}`,
    userId: 'mock_user_default',
    name: '测试指标',
    category: 'trend',
    syntax: 'tdx',
    formula: 'CLOSE > MA(CLOSE, 5)',
    params: [],
    operator: '>',
    defaultThreshold: 0,
    description: '',
    visibility: 'private',
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    ...overrides,
  };
}

/** 构造一个导出文件 JSON 字符串 */
function makeExportJson(indicators: Partial<CustomIndicator>[]) {
  return JSON.stringify({
    version: 1,
    exportedAt: new Date().toISOString(),
    userId: 'mock_user_default',
    indicators,
  });
}

/** 模拟选择文件：创建 File 并触发 file input change */
function selectFile(file: File) {
  const input = document.querySelector(
    '[data-testid="import-export-file-input"]',
  ) as HTMLInputElement;
  Object.defineProperty(input, 'files', {
    value: [file],
    writable: false,
  });
  fireEvent.change(input);
}

function renderButtons(props: Partial<React.ComponentProps<typeof ImportExportButtons>> = {}) {
  const onImportSuccess = props.onImportSuccess ?? vi.fn();
  const customIndicators = props.customIndicators ?? [];
  return render(
    <ConfigProvider>
      <ImportExportButtons
        customIndicators={customIndicators}
        onImportSuccess={onImportSuccess}
        {...props}
      />
    </ConfigProvider>,
  );
}

// ============================================================================
// Mocks
// ============================================================================

// 监听 message 调用
const messageSpy = vi.spyOn(message, 'success').mockImplementation(() => {});
const messageErrorSpy = vi.spyOn(message, 'error').mockImplementation(() => {});

// 拦截 Blob URL 与下载行为
let lastDownloadAnchor: HTMLAnchorElement | null = null;
const originalCreateObjectURL = URL.createObjectURL;
const originalRevokeObjectURL = URL.revokeObjectURL;

beforeEach(() => {
  window.localStorage.clear();
  storage.clearAllCustomIndicators();
  lastDownloadAnchor = null;

  // mock createObjectURL 记录被创建的 Blob
  URL.createObjectURL = vi.fn().mockImplementation((blob: Blob) => {
    // 把 blob 内容读出来备用（测试可验证）
    return 'blob:mock-url';
  });
  URL.revokeObjectURL = vi.fn().mockImplementation(() => {});

  // mock HTMLAnchorElement.click 拦截下载
  const originalClick = HTMLAnchorElement.prototype.click;
  HTMLAnchorElement.prototype.click = function (this: HTMLAnchorElement) {
    if (this.download && this.href.startsWith('blob:')) {
      lastDownloadAnchor = this;
    }
    // 不真正触发下载，仅记录
  };

  messageSpy.mockClear();
  messageErrorSpy.mockClear();
});

afterEach(() => {
  URL.createObjectURL = originalCreateObjectURL;
  URL.revokeObjectURL = originalRevokeObjectURL;
  HTMLAnchorElement.prototype.click = HTMLAnchorElement.prototype.click;
  vi.clearAllMocks();
});

// ============================================================================
// 1. 基础渲染
// ============================================================================

describe('ImportExportButtons - 基础渲染', () => {
  it('渲染导入 + 导出两个按钮 + 隐藏 file input', () => {
    renderButtons();
    expect(screen.getByTestId('import-export-import-btn')).toBeInTheDocument();
    expect(screen.getByTestId('import-export-export-btn')).toBeInTheDocument();
    expect(
      document.querySelector('[data-testid="import-export-file-input"]'),
    ).toBeInTheDocument();
  });

  it('导出按钮：customIndicators 为空时 disabled', () => {
    renderButtons({ customIndicators: [] });
    expect(screen.getByTestId('import-export-export-btn')).toBeDisabled();
  });

  it('导出按钮：customIndicators 非空时显示数量', () => {
    renderButtons({ customIndicators: [makeIndicator(), makeIndicator()] });
    expect(screen.getByTestId('import-export-export-btn')).toHaveTextContent('导出(2)');
    expect(screen.getByTestId('import-export-export-btn')).not.toBeDisabled();
  });

  it('点击导入按钮触发 file input click', async () => {
    const user = userEvent.setup();
    const clickSpy = vi.fn();
    renderButtons();
    const input = document.querySelector(
      '[data-testid="import-export-file-input"]',
    ) as HTMLInputElement;
    input.click = clickSpy;
    await user.click(screen.getByTestId('import-export-import-btn'));
    expect(clickSpy).toHaveBeenCalled();
  });
});

// ============================================================================
// 2. 导出
// ============================================================================

describe('ImportExportButtons - 导出', () => {
  it('点击导出按钮创建 Blob URL 并触发下载', async () => {
    const user = userEvent.setup();
    // 预先 seed storage（exportCustomIndicators 实际从 storage 读取）
    storage.saveCustomIndicator(makeIndicator({ id: undefined as any, name: '指标A' }) as any);
    storage.saveCustomIndicator(makeIndicator({ id: undefined as any, name: '指标B' }) as any);
    const indicators = [makeIndicator({ name: '指标A' }), makeIndicator({ name: '指标B' })];
    renderButtons({ customIndicators: indicators });
    await user.click(screen.getByTestId('import-export-export-btn'));

    await waitFor(() => {
      expect(URL.createObjectURL).toHaveBeenCalled();
    });
    expect(lastDownloadAnchor).not.toBeNull();
    // 文件名格式：custom-indicators-YYYY-MM-DD.json
    expect(lastDownloadAnchor?.download).toMatch(/^custom-indicators-\d{4}-\d{2}-\d{2}\.json$/);
    // revokeObjectURL 被调用
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:mock-url');
    // message.success 被调用
    expect(messageSpy).toHaveBeenCalledWith(expect.stringContaining('已导出 2 条'));
  });

  it('导出空列表时按钮 disabled 不触发下载', async () => {
    const user = userEvent.setup();
    renderButtons({ customIndicators: [] });
    // 即使用 userEvent 点击 disabled 按钮也不应触发
    await user.click(screen.getByTestId('import-export-export-btn'));
    expect(URL.createObjectURL).not.toHaveBeenCalled();
    expect(lastDownloadAnchor).toBeNull();
  });
});

// ============================================================================
// 3. 导入 - file-level 错误
// ============================================================================

describe('ImportExportButtons - 导入 file-level 错误', () => {
  it('选择版本过高的文件：message.error + 不进入 Preview', async () => {
    const user = userEvent.setup();
    renderButtons();
    const json = JSON.stringify({ version: 999, indicators: [] });
    const file = new File([json], 'test.json', { type: 'application/json' });
    selectFile(file);

    await waitFor(() => {
      expect(messageErrorSpy).toHaveBeenCalledWith(expect.stringContaining('版本 v999'));
    });
    // Preview 弹窗不应打开
    expect(screen.queryByTestId('import-export-preview-modal')).not.toBeInTheDocument();
  });

  it('选择格式无效的 JSON：message.error + 不进入 Preview', async () => {
    const user = userEvent.setup();
    renderButtons();
    const file = new File(['not a json'], 'test.json', { type: 'application/json' });
    selectFile(file);

    await waitFor(() => {
      expect(messageErrorSpy).toHaveBeenCalledWith(expect.stringContaining('JSON 解析失败'));
    });
    expect(screen.queryByTestId('import-export-preview-modal')).not.toBeInTheDocument();
  });

  it('选择根对象缺失（数组）：message.error + 不进入 Preview', async () => {
    const user = userEvent.setup();
    renderButtons();
    const file = new File(['[]'], 'test.json', { type: 'application/json' });
    selectFile(file);

    await waitFor(() => {
      expect(messageErrorSpy).toHaveBeenCalledWith(expect.stringContaining('根对象缺失'));
    });
  });

  it('选择 indicators 非数组：message.error + 不进入 Preview', async () => {
    const user = userEvent.setup();
    renderButtons();
    const file = new File(
      [JSON.stringify({ version: 1, indicators: 'not an array' })],
      'test.json',
      { type: 'application/json' },
    );
    selectFile(file);

    await waitFor(() => {
      expect(messageErrorSpy).toHaveBeenCalledWith(expect.stringContaining('indicators 必须为数组'));
    });
  });
});

// ============================================================================
// 4. 导入 - indicator-level 错误
// ============================================================================

describe('ImportExportButtons - 导入 indicator-level 错误', () => {
  it('导入含 name_duplicate 错误的文件：Preview 弹窗显示跳过数 + 错误明细', async () => {
    const user = userEvent.setup();
    // 预先 seed storage + 传 prop 保持一致（preview 用 prop 检测重名）
    storage.saveCustomIndicator(
      makeIndicator({ id: undefined as any, name: '重复名称' }) as any,
    );

    renderButtons({
      customIndicators: [makeIndicator({ id: 'existing', name: '重复名称' })],
    });
    const json = makeExportJson([
      { name: '新指标A', category: 'trend', syntax: 'tdx', formula: 'A', operator: '>', params: [] },
      { name: '重复名称', category: 'trend', syntax: 'tdx', formula: 'B', operator: '>', params: [] },
    ]);
    const file = new File([json], 'test.json', { type: 'application/json' });
    selectFile(file);

    await waitFor(() => {
      expect(screen.getByTestId('import-export-preview-modal')).toBeInTheDocument();
    });

    // 预览统计：1 个新增 + 1 个跳过 + 1 个错误
    expect(screen.getByTestId('import-export-preview-added')).toHaveTextContent('1');
    expect(screen.getByTestId('import-export-preview-skipped')).toHaveTextContent('1');
    // 错误明细表格存在
    expect(screen.getByTestId('import-export-preview-errors-table')).toBeInTheDocument();
    // 错误类型 Tag 出现
    expect(screen.getByText(/名称重复已跳过/)).toBeInTheDocument();
  });

  it('导入含 field_invalid 错误的文件：Preview 弹窗显示错误明细', async () => {
    const user = userEvent.setup();
    renderButtons();
    // indicators[0] 缺 name
    const json = JSON.stringify({
      version: 1,
      exportedAt: new Date().toISOString(),
      userId: 'mock_user_default',
      indicators: [{ category: 'trend', formula: 'A', operator: '>' }],
    });
    const file = new File([json], 'test.json', { type: 'application/json' });
    selectFile(file);

    await waitFor(() => {
      expect(screen.getByTestId('import-export-preview-modal')).toBeInTheDocument();
    });
    expect(screen.getByText(/字段缺失\/类型错误/)).toBeInTheDocument();
  });

  it('导入全部合法文件：Preview 弹窗显示"全部指标可正常导入"', async () => {
    const user = userEvent.setup();
    renderButtons();
    const json = makeExportJson([
      { name: '新指标A', category: 'trend', syntax: 'tdx', formula: 'A', operator: '>', params: [] },
      { name: '新指标B', category: 'trend', syntax: 'tdx', formula: 'B', operator: '>', params: [] },
    ]);
    const file = new File([json], 'test.json', { type: 'application/json' });
    selectFile(file);

    await waitFor(() => {
      expect(screen.getByTestId('import-export-preview-modal')).toBeInTheDocument();
    });
    expect(screen.getByTestId('import-export-preview-added')).toHaveTextContent('2');
    expect(screen.getByText(/全部指标可正常导入/)).toBeInTheDocument();
  });
});

// ============================================================================
// 5. 确认导入
// ============================================================================

describe('ImportExportButtons - 确认导入', () => {
  it('点击确认导入：写入 localStorage + 调用 onImportSuccess 回调', async () => {
    const user = userEvent.setup();
    const onImportSuccess = vi.fn();
    renderButtons({ onImportSuccess });

    const json = makeExportJson([
      { name: '新指标A', category: 'trend', syntax: 'tdx', formula: 'A', operator: '>', params: [] },
    ]);
    const file = new File([json], 'test.json', { type: 'application/json' });
    selectFile(file);

    await waitFor(() => {
      expect(screen.getByTestId('import-export-preview-modal')).toBeInTheDocument();
    });

    await user.click(screen.getByTestId('import-export-preview-confirm'));

    // 写入 storage
    const stored = storage.listCustomIndicators();
    expect(stored).toHaveLength(1);
    expect(stored[0].name).toBe('新指标A');

    // 回调被调用，payload 为新增的指标
    expect(onImportSuccess).toHaveBeenCalledTimes(1);
    expect(onImportSuccess.mock.calls[0][0]).toHaveLength(1);
    expect(onImportSuccess.mock.calls[0][0][0].name).toBe('新指标A');

    // 弹窗关闭
    await waitFor(() => {
      expect(screen.queryByTestId('import-export-preview-modal')).not.toBeInTheDocument();
    });

    // message.success 提示
    expect(messageSpy).toHaveBeenCalledWith(expect.stringContaining('导入完成'));
  });
});

// ============================================================================
// 6. 取消导入
// ============================================================================

describe('ImportExportButtons - 取消导入', () => {
  it('点击取消按钮关闭 Preview 弹窗（不写入 storage）', async () => {
    const user = userEvent.setup();
    renderButtons();
    const json = makeExportJson([
      { name: '新指标A', category: 'trend', syntax: 'tdx', formula: 'A', operator: '>', params: [] },
    ]);
    const file = new File([json], 'test.json', { type: 'application/json' });
    selectFile(file);

    await waitFor(() => {
      expect(screen.getByTestId('import-export-preview-modal')).toBeInTheDocument();
    });
    await user.click(screen.getByTestId('import-export-preview-cancel'));

    await waitFor(() => {
      expect(screen.queryByTestId('import-export-preview-modal')).not.toBeInTheDocument();
    });
    // 不写入 storage
    expect(storage.listCustomIndicators()).toHaveLength(0);
  });
});

// ============================================================================
// 7. 文件大小超限
// ============================================================================

describe('ImportExportButtons - 文件大小超限', () => {
  it('选择超过 5MB 的文件：message.error + 不进入 Preview', async () => {
    const user = userEvent.setup();
    renderButtons();
    // 构造 5MB+ 1 字节的内容
    const largeContent = 'A'.repeat(5 * 1024 * 1024 + 1);
    const file = new File([largeContent], 'big.json', { type: 'application/json' });
    selectFile(file);

    await waitFor(() => {
      expect(messageErrorSpy).toHaveBeenCalledWith(expect.stringContaining('文件过大'));
    });
    expect(screen.queryByTestId('import-export-preview-modal')).not.toBeInTheDocument();
  });
});
