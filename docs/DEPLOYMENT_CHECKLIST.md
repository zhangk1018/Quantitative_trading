# ==========================================
# 量化交易系统 - 生产部署前置检查清单
# ==========================================
# 文档版本: v1.0
# 创建日期: 2026-05-30
# 适用环境: 生产环境部署

---

## 📋 部署检查清单

### 1. 操作系统层（冷热分离前置）

| 步骤 | 命令 | 说明 | 状态 |
|------|------|------|------|
| 1.1 | `sudo mkdir -p /data/cold /data/hot` | 创建冷热数据存储目录 | ☐ |
| 1.2 | `sudo chown postgres:postgres /data/cold /data/hot` | 授予 PostgreSQL 用户所有权 | ☐ |
| 1.3 | `sudo chmod 700 /data/cold /data/hot` | 设置安全权限（仅所有者访问） | ☐ |

**说明**: 此步骤需要 root 权限执行，创建完成后才能创建表空间。

---

### 2. 数据库层（执行顺序不可逆）

| 步骤 | 命令 | 说明 | 状态 |
|------|------|------|------|
| 2.1 | `psql -h localhost -U postgres -d quant_trading -f scripts/init_db.sql` | **首次初始化**（超级用户执行） | ☐ |
| 2.2 | `psql -h localhost -U quant_user -d quant_trading -f scripts/partition_maintenance.sql` | 创建分区维护存储过程 | ☐ |
| 2.3 | `psql -h localhost -U postgres -d quant_trading -f scripts/partition_cold_hot.sql` | 冷热分离配置（按需执行） | ☐ |

**重要提示**:
- `init_db.sql` 为首次初始化脚本，**不支持重复执行**
- 后续年度分区维护使用 `partition_maintenance.sql` 中的存储过程
- 冷热分离需要提前完成步骤 1 的 OS 层准备

---

### 3. 验证命令

| 步骤 | 命令 | 预期结果 | 状态 |
|------|------|----------|------|
| 3.1 | `psql -U quant_user -d quant_trading -c "SELECT * FROM get_partition_status('stock_quotes');"` | 显示 2015-2030 年度分区 | ☐ |
| 3.2 | `psql -U quant_user -d quant_trading -c "SELECT * FROM get_partition_status('stock_indicators');"` | 显示 2015-2030 年度分区 | ☐ |
| 3.3 | `psql -U quant_user -d quant_trading -c "CALL add_year_partition('stock_quotes', 2031);"` | 成功添加 2031 分区 | ☐ |
| 3.4 | `psql -U quant_user -d quant_trading -c "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';"` | 显示 10 张业务表 | ☐ |

---

### 4. 权限检查

| 步骤 | 命令 | 说明 | 状态 |
|------|------|------|------|
| 4.1 | `psql -U quant_user -d quant_trading -c "SELECT current_user;"` | 确认当前用户为 quant_user | ☐ |
| 4.2 | `psql -U quant_user -d quant_trading -c "INSERT INTO stock_basic (code, name) VALUES ('TEST', '测试');"` | 测试写入权限 | ☐ |
| 4.3 | `psql -U quant_user -d quant_trading -c "DELETE FROM stock_basic WHERE code = 'TEST';"` | 测试删除权限 | ☐ |

---

### 5. 运维建议

#### 5.1 年度分区维护流程
```bash
# 每年年底执行，添加下一年度分区
psql -U quant_user -d quant_trading <<EOF
CALL add_year_partition('stock_quotes', 2031);
CALL add_year_partition('stock_indicators', 2031);
SELECT * FROM get_partition_status('stock_quotes');
EOF
```

#### 5.2 冷热数据归档（每年执行）
```bash
# 将上一年数据迁移到冷存储
psql -U postgres -d quant_trading <<EOF
ALTER TABLE stock_quotes_2025 SET TABLESPACE cold_storage;
ALTER TABLE stock_indicators_2025 SET TABLESPACE cold_storage;
EOF
```

#### 5.3 推荐监控指标
- 分区表数据量增长趋势
- 查询性能（特别是跨分区查询）
- 冷热存储使用率

---

## 📝 部署状态记录

| 日期 | 执行人 | 环境 | 版本 | 状态 |
|------|--------|------|------|------|
| | | | | |

---

*文档结束*