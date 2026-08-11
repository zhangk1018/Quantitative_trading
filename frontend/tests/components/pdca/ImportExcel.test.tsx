/**
 * ImportExcel 组件测试
 *
 * 覆盖：
 * - 渲染初始状态（券商选择、上传区域）
 * - 加载券商列表
 * - 解析按钮在未选择券商和文件时禁用
 * - 选择券商和文件后解析按钮可用，点击后显示解析结果
 * - 确认导入按钮功能
 */

import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';

// 设置全局超时（JSDOM + Antd 渲染较慢）
vi.setConfig({ testTimeout: 30000 });
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { App } from 'antd';
import { server } from '../../mocks/server';
import { pdcaHandlers, resetMockData } from '../../mocks/pdcaHandlers';
import ImportExcel from '@/features/pdca/components/ImportExcel';

// 模拟 FileReader 使其同步返回，避免 Antd Upload async beforeUpload 在 JSDOM 中的异步兼容问题
const originalFileReader = globalThis.FileReader;
class MockFileReader {
  onload: ((this: FileReader, ev: ProgressEvent<FileReader>) => void) | null = null;
  onerror: ((this: FileReader, ev: ProgressEvent<FileReader>) => void) | null = null;
  result: ArrayBuffer | null = null;

  readAsArrayBuffer(blob: Blob): void {
    blob.arrayBuffer().then((buf) => {
      this.result = buf;
      if (this.onload) {
        // 传递正确的 e.target，使组件中的 e.target.result 能读到 ArrayBuffer
        const event = { target: this } as unknown as ProgressEvent<FileReader>;
        this.onload.call(this as unknown as FileReader, event);
      }
    });
  }
  readAsText(_blob: Blob, _encoding?: string): void { /* no-op */ }
  readAsDataURL(_blob: Blob): void { /* no-op */ }
  abort(): void { /* no-op */ }
  get readyState() { return 2; } // DONE
  get error() { return null; }
}

// 包装 Antd App 上下文
const Wrapper: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <App>{children}</App>
);

describe('ImportExcel', () => {
  beforeEach(() => {
    resetMockData();
    server.use(...pdcaHandlers);
    globalThis.FileReader = MockFileReader as unknown as typeof FileReader;
  });

  afterEach(() => {
    globalThis.FileReader = originalFileReader;
  });

  it('渲染初始状态，包含标题和上传区域', async () => {
    render(<ImportExcel />, { wrapper: Wrapper });

    expect(await screen.findByText('券商成交单导入')).toBeInTheDocument();
    expect(screen.getByText('点击或拖拽 Excel 文件到此处')).toBeInTheDocument();
    expect(screen.getByText(/支持 .xlsx \/ .xls 格式，最大 10MB/)).toBeInTheDocument();
  });

  it('加载券商列表后显示选择器', async () => {
    render(<ImportExcel />, { wrapper: Wrapper });

    await screen.findByText('选择券商模板');
    const selectTrigger = screen.getByTestId('broker-select');
    expect(selectTrigger).toBeInTheDocument();
  });

  it('解析按钮在未选择券商和文件时禁用', async () => {
    render(<ImportExcel />, { wrapper: Wrapper });

    await screen.findByText('券商成交单导入');
    const parseButton = screen.getByRole('button', { name: /解析文件/i });
    expect(parseButton).toBeDisabled();
  });

  // 上传文件的辅助函数
async function uploadFile(user: ReturnType<typeof userEvent.setup>) {
  const file = new File(
    [new Uint8Array([0x50, 0x4b, 0x03, 0x04])],
    'test.xlsx',
    { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' },
  );
  const fileInput = document.querySelector('input[type="file"]')!;
  // 通过 Object.defineProperty 设置 files 属性，确保 Antd Upload 的 rc-upload 能正确读取
  Object.defineProperty(fileInput, 'files', { value: [file], writable: false });
  fireEvent.change(fileInput);
  // 等待 Antd Upload 处理异步 beforeUpload → validateMagic → onChange 链
  await new Promise((r) => setTimeout(r, 200));
}

  it('选择券商和文件后解析按钮可用，点击后显示解析结果', async () => {
    const user = userEvent.setup();
    render(<ImportExcel />, { wrapper: Wrapper });

    await screen.findByText('券商成交单导入');
    await screen.findByText('选择券商模板');

    // 选择券商（使用 fireEvent.mouseDown 避免 Antd Select 的 pointer-events: none 限制）
    fireEvent.mouseDown(document.querySelector('.ant-select-selector')!);
    const htOption = await screen.findByText('华泰证券');
    await user.click(htOption);

    // 上传文件
    await uploadFile(user);

    // 等待解析按钮变为可用（使用 findByRole 查找元素，waitFor 等待状态变化）
    const parseButton = await screen.findByRole('button', { name: /解析文件/i });
    await waitFor(() => expect(parseButton).not.toBeDisabled());

    // 点击解析文件
    await user.click(parseButton);

    // 验证解析结果显示
    await screen.findByText('共 6 条，5 条有效，1 条错误');
    expect(screen.getByText('1 行数据解析失败')).toBeInTheDocument();
    expect(screen.getByText('确认导入 (2 条)')).toBeInTheDocument();
  });

  it('解析后点击确认导入按钮完成导入', async () => {
    const user = userEvent.setup();
    render(<ImportExcel />, { wrapper: Wrapper });

    await screen.findByText('券商成交单导入');
    await screen.findByText('选择券商模板');

    // 选择券商（使用 fireEvent.mouseDown 避免 Antd Select 的 pointer-events: none 限制）
    fireEvent.mouseDown(document.querySelector('.ant-select-selector')!);
    const htOption = await screen.findByText('华泰证券');
    await user.click(htOption);

    // 上传文件
    await uploadFile(user);

    // 等待解析按钮变为可用
    await waitFor(() => {
      const parseButton = screen.getByRole('button', { name: /解析文件/i });
      expect(parseButton).not.toBeDisabled();
    });

    // 解析
    await user.click(screen.getByRole('button', { name: /解析文件/i }));
    await screen.findByText('共 6 条，5 条有效，1 条错误');

    // 点击确认导入（使用 findByRole 查找元素，waitFor 等待状态变化）
    const confirmButton = await screen.findByRole('button', { name: /确认导入/i });
    await waitFor(() => expect(confirmButton).not.toBeDisabled());
    await user.click(confirmButton);

    // 验证导入成功后成功提示出现
    await screen.findByText('成功导入 5 条交易记录');
  });
});