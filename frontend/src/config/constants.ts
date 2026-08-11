/** PDCA 模块常量配置 */

// API 基础路径
export const API_PREFIX = '/pdca';

// 分页配置
export const DEFAULT_PAGE_SIZE = 20;
export const PAGE_SIZE_OPTIONS = [10, 20, 50, 100];

// 搜索防抖延迟（毫秒）
export const SEARCH_DEBOUNCE_MS = 300;

// 文件上传限制
export const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB
export const VALID_FILE_EXTENSIONS = ['xlsx', 'xls'];
export const ALLOWED_IMAGE_MIME_TYPES = ['image/jpeg', 'image/png', 'image/gif', 'image/webp'];

// Excel 文件魔数
export const XLSX_MAGIC = '504b0304'; // PK\x03\x04
export const XLS_MAGIC = 'd0cf11e0';  // \xD0\xCF\x11\xE0
export const VALID_EXCEL_MAGICS = [XLSX_MAGIC, XLS_MAGIC];

// API 超时时间（毫秒）
export const API_TIMEOUT = 30000;