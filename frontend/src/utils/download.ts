/**
 * download.ts — 通用文件下载工具函数
 *
 * 统一处理 Blob 对象下载与 URL 生成，避免重复代码。
 * 支持自定义文件名和自动清理。
 */

/**
 * 下载 Blob 数据为文件
 * @param blob 文件 Blob 数据
 * @param filename 下载文件名（含扩展名）
 */
export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  try {
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  } finally {
    URL.revokeObjectURL(url);
  }
}