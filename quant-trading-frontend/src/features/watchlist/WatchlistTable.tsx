import React, { memo, useState, useMemo } from 'react';
import { Button, Typography, Popconfirm } from 'antd';
import { DeleteOutlined, CaretUpOutlined, CaretDownOutlined } from '@ant-design/icons';
import { useSettings } from '@/shared/contexts/SettingsContext';
import {
  formatNumber,
  formatChangePct,
  formatChangeAmount,
  formatMarketCap,
  calcChangeAmount,
} from './utils/stock-formatter';
import type { WatchlistStockRow } from './index';

const { Text } = Typography;

type SortField = 'stock_code' | 'stock_name' | 'close' | 'change_pct' | 'pe' | 'pb' | 'market_cap';
type SortDir = 'asc' | 'desc';

interface WatchlistTableProps {
  rows: WatchlistStockRow[];
  activeGroup: string | null;
  onDelete: (code: string) => void;
  onDoubleClick: (row: WatchlistStockRow) => void;
}

/** 排序指示器 */
const SortIcon: React.FC<{ field: SortField; sortField: SortField | null; sortDir: SortDir }> = ({
  field,
  sortField,
  sortDir,
}) => {
  if (sortField !== field) return <span className="text-text-secondary ml-1 opacity-30">⇅</span>;
  return sortDir === 'asc' ? (
    <CaretUpOutlined className="ml-1 text-color-up text-xs" />
  ) : (
    <CaretDownOutlined className="ml-1 text-color-down text-xs" />
  );
};

/** 排序按钮 */
const SortHeader: React.FC<{
  label: string;
  field: SortField;
  sortField: SortField | null;
  sortDir: SortDir;
  onSort: (f: SortField) => void;
  className?: string;
}> = ({ label, field, sortField, sortDir, onSort, className }) => (
  <th
    className={`px-3 py-2 cursor-pointer select-none hover:bg-bg-card/50 ${className || ''}`}
    onClick={() => onSort(field)}
  >
    {label}
    <SortIcon field={field} sortField={sortField} sortDir={sortDir} />
  </th>
);

const TableRow = memo<{
  row: WatchlistStockRow;
  onDelete: (code: string) => void;
  onDoubleClick: (row: WatchlistStockRow) => void;
}>(({ row, onDelete, onDoubleClick }) => {
  const { colors } = useSettings();
  const changePct = row.change_pct != null && isFinite(row.change_pct) ? row.change_pct : null;
  const isUp = changePct !== null && changePct >= 0;
  const color = isUp ? colors.up : colors.down;
  const changeAmount = calcChangeAmount(row.close, changePct);

  return (
    <tr
      className="border-b border-border-color hover:bg-bg-panel/60 transition-colors cursor-pointer"
      onDoubleClick={() => onDoubleClick(row)}
      data-testid={`watchlist-row-${row.stock_code}`}
    >
      <td className="px-3 py-2 text-text-primary font-mono">{row.stock_code}</td>
      <td className="px-3 py-2 text-text-primary">{row.stock_name}</td>
      <td className="px-3 py-2 text-right font-mono" style={{ color }}>
        {formatNumber(row.close)}
      </td>
      <td className="px-3 py-2 text-right font-mono" style={{ color }}>
        {formatChangePct(changePct)}
      </td>
      <td className="px-3 py-2 text-right font-mono" style={{ color }}>
        {formatChangeAmount(changeAmount)}
      </td>
      <td className="px-3 py-2 text-right text-text-primary font-mono">
        {formatNumber(row.pe ?? row.pe_ttm)}
      </td>
      <td className="px-3 py-2 text-right text-text-primary font-mono">
        {formatNumber(row.pb)}
      </td>
      <td className="px-3 py-2 text-right text-text-primary font-mono">
        {formatMarketCap(row.market_cap)}
      </td>
      <td className="px-3 py-2 text-center">
        <span className="text-xs px-1.5 py-0.5 bg-bg-card text-text-secondary rounded">
          {row.group_name}
        </span>
      </td>
      <td className="px-3 py-2 text-center">
        <Popconfirm
          title="确认删除"
          description={`确定要从自选股中移除 ${row.stock_code} ${row.stock_name}？`}
          onConfirm={() => onDelete(row.stock_code)}
          okText="删除"
          cancelText="取消"
          placement="left"
          okButtonProps={{ 'data-testid': `watchlist-popconfirm-ok-${row.stock_code}` }}
          cancelButtonProps={{ 'data-testid': `watchlist-popconfirm-cancel-${row.stock_code}` }}
        >
          <Button
            type="text"
            size="small"
            danger
            icon={<DeleteOutlined />}
            onClick={(e) => e.stopPropagation()}
            data-testid={`watchlist-delete-${row.stock_code}`}
          />
        </Popconfirm>
      </td>
    </tr>
  );
});
TableRow.displayName = 'TableRow';

const WatchlistTable: React.FC<WatchlistTableProps> = ({
  rows,
  activeGroup,
  onDelete,
  onDoubleClick,
}) => {
  const [sortField, setSortField] = useState<SortField | null>(null);
  const [sortDir, setSortDir] = useState<SortDir>('desc');

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortField(field);
      setSortDir('desc');
    }
  };

  const sortedRows = useMemo(() => {
    if (!sortField) return rows;
    return [...rows].sort((a, b) => {
      const aVal = a[sortField] ?? 0;
      const bVal = b[sortField] ?? 0;
      if (sortField === 'stock_code' || sortField === 'stock_name') {
        return sortDir === 'asc'
          ? String(aVal).localeCompare(String(bVal))
          : String(bVal).localeCompare(String(aVal));
      }
      const aNum = Number(aVal) || 0;
      const bNum = Number(bVal) || 0;
      return sortDir === 'asc' ? aNum - bNum : bNum - aNum;
    });
  }, [rows, sortField, sortDir]);

  if (rows.length === 0) return null;

  return (
    <div className="w-full" data-testid="watchlist-table">
      <table className="w-full text-sm border-collapse">
        <thead className="sticky top-0 z-10 bg-bg-panel">
          <tr className="text-text-secondary text-xs border-b border-border-color">
            <SortHeader label="代码" field="stock_code" sortField={sortField} sortDir={sortDir} onSort={handleSort} className="text-left" />
            <SortHeader label="名称" field="stock_name" sortField={sortField} sortDir={sortDir} onSort={handleSort} className="text-left" />
            <SortHeader label="最新价" field="close" sortField={sortField} sortDir={sortDir} onSort={handleSort} className="text-right" />
            <SortHeader label="涨跌幅" field="change_pct" sortField={sortField} sortDir={sortDir} onSort={handleSort} className="text-right" />
            <th className="px-3 py-2 text-right">涨跌额</th>
            <SortHeader label="市盈率" field="pe" sortField={sortField} sortDir={sortDir} onSort={handleSort} className="text-right" />
            <SortHeader label="市净率" field="pb" sortField={sortField} sortDir={sortDir} onSort={handleSort} className="text-right" />
            <SortHeader label="总市值" field="market_cap" sortField={sortField} sortDir={sortDir} onSort={handleSort} className="text-right" />
            <th className="px-3 py-2 text-center">分组</th>
            <th className="px-3 py-2 text-center w-12">操作</th>
          </tr>
        </thead>
        <tbody>
          {sortedRows.map((row) => (
            <TableRow
              key={`${row.stock_code}-${row.group_name}`}
              row={row}
              onDelete={onDelete}
              onDoubleClick={onDoubleClick}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default WatchlistTable;