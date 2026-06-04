# Akshare 股票列表数据源

项目已集成 Akshare 作为主要的股票列表数据源（免费无调用限制）。

## 📦 安装依赖

```bash
pip install akshare
```

## 🚀 使用方式

### 方式1: 独立脚本（推荐）

```bash
# 更新股票列表
python update_stock_list.py
```

### 方式2: 使用主程序

```bash
# 更新股票列表
python src/main.py --mode list

# 查看股票数据
python src/view_data.py /path/to/stock_list.parquet
```

## 📋 功能说明

### 智能数据源选择

程序会按以下优先级获取股票列表：

1. **Akshare**（优先，免费无限制）
2. **Tushare**（备选，有调用限制）
3. **本地缓存**（最后备选）

### 支持的市场

- 上海主板（600/601/602/603/605）
- 科创板（688/689）
- 深圳主板（000/001/002/003）
- 创业板（300/301）
- 北交所（400/800/830/880）

## 📁 文件结构

```
src/
├── akshare_fetcher.py      # Akshare 数据源模块
├── main.py                 # 主程序（已集成 Akshare）
└── view_data.py            # 数据查看脚本（已添加过期检测）

update_stock_list.py        # 快捷更新脚本
AKSHARE_README.md          # 本说明文档
```

## 💡 最佳实践

1. **定期更新股票列表**：建议每天运行一次 `update_stock_list.py`
2. **查看数据状态**：使用 `view_data.py` 检查股票列表是否过期
3. **优先使用 Akshare**：相比 Tushare，Akshare 完全免费且无调用限制

## 🔧 故障排除

### 问题：ModuleNotFoundError: No module named 'akshare'

解决：安装 akshare

```bash
pip install akshare
```

### 问题：获取股票列表失败

解决：
1. 检查网络连接
2. 确认 Akshare 版本为最新
3. 查看日志获取详细错误信息

## 📊 Akshare 优势

- ✅ 完全免费
- ✅ 无调用次数限制
- ✅ 数据更新及时
- ✅ 社区活跃，文档完善
