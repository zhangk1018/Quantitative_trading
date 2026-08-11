import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
vi.setConfig({ testTimeout: 30000 });
import { render, screen, waitFor, fireEvent, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { App } from 'antd';
import { server } from '../../mocks/server';
import { pdcaHandlers, resetMockData } from '../../mocks/pdcaHandlers';
import ImportExcel from '@/features/pdca/components/ImportExcel';
import { parseImportExcel } from '@/features/pdca/api';

const originalFileReader = globalThis.FileReader;
class MockFileReader {
  onload: any = null;
  onerror: any = null;
  result: ArrayBuffer | null = null;
  readAsArrayBuffer(blob: Blob): void {
    blob.arrayBuffer().then((buf) => {
      this.result = buf;
      if (this.onload) {
        const event = { target: this };
        this.onload(event);
      }
    });
  }
  readAsText(_blob: Blob, _encoding?: string): void {}
  readAsDataURL(_blob: Blob): void {}
  abort(): void {}
  get readyState() { return 2; }
  get error() { return null; }
}

const Wrapper: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <App>{children}</App>
);

describe('ImportExcel Debug', () => {
  beforeEach(() => {
    resetMockData();
    server.use(...pdcaHandlers);
    globalThis.FileReader = MockFileReader as unknown as typeof FileReader;
  });
  afterEach(() => {
    globalThis.FileReader = originalFileReader;
  });

  it('API direct call with fetch works', async () => {
    const file = new File([new Uint8Array([0x50, 0x4b, 0x03, 0x04])], 'test.xlsx', { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
    const formData = new FormData();
    formData.append('file', file);
    formData.append('broker_name', 'ht');
    const res = await fetch('/api/pdca/import/parse', { method: 'POST', body: formData });
    const data = await res.json();
    console.log('fetch response:', JSON.stringify(data));
    expect(data.code).toBe(200);
  });

  it('API direct call with axios works', async () => {
    const file = new File([new Uint8Array([0x50, 0x4b, 0x03, 0x04])], 'test.xlsx', { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
    const res = await parseImportExcel(file, 'ht');
    expect(res.code).toBe(200);
    expect(res.data.total_rows).toBe(6);
  });

  it('DOM after upload and parse', async () => {
    const user = userEvent.setup();
    render(<ImportExcel />, { wrapper: Wrapper });
    await screen.findByText('券商成交单导入');
    await screen.findByText('选择券商模板');

    fireEvent.mouseDown(document.querySelector('.ant-select-selector')!);
    const htOption = await screen.findByText('华泰证券');
    await user.click(htOption);

    const file = new File([new Uint8Array([0x50, 0x4b, 0x03, 0x04])], 'test.xlsx', { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
    const fileInput = document.querySelector('input[type="file"]')!;
    
    await act(async () => {
      Object.defineProperty(fileInput, 'files', { value: [file], writable: false });
      fireEvent.change(fileInput);
      await new Promise((r) => setTimeout(r, 500));
    });

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /解析文件/i })).not.toBeDisabled();
    });

    const htmlBefore = document.body.innerHTML;
    console.log('Before click - has upload file:', htmlBefore.includes('test.xlsx'));
    console.log('Before click - buttons:', screen.getAllByRole('button').map(b => b.textContent));

    await user.click(screen.getByRole('button', { name: /解析文件/i }));
    await new Promise((r) => setTimeout(r, 1500));

    const htmlAfter = document.body.innerHTML;
    console.log('After click - has result text:', htmlAfter.includes('共 6 条'));
    console.log('After click - buttons:', screen.getAllByRole('button').map(b => b.textContent));
    
    const resultEl = screen.queryByText(/共.*条.*有效.*条.*错误/);
    console.log('Result element:', resultEl ? 'FOUND' : 'NOT FOUND');
  });
});