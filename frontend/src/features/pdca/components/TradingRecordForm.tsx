/**
 * TradingRecordForm.tsx — 交易记录录入/编辑表单
 *
 * 功能：
 * - 股票代码自动补全（搜索 stock_basic，带防抖）
 * - 数值范围校验（前后端双重）
 * - 日期先后校验（出场日期 > 入场日期）
 * - 支持新增和编辑模式
 * - 卖出记录管理：委托 ExitSlipList / ExitSlipModal 子组件（统一通过新增卖出记录操作）
 * - 自动计算入场佣金/出场佣金/滑点（从系统设置读取手续费率/滑点率）
 * - 保存时校验入场价/出场价在当日最高最低价范围内
 * - 全部卖出时自动计算进场得分、出场得分、总得分、等级（《走进我的交易室》原著公式）
 */

import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import {
  Modal, Form, Input, InputNumber, DatePicker, Select, App, Row, Col, AutoComplete,
} from 'antd';
import dayjs from 'dayjs';
import type { TradingRecord, TradingRecordFormData, StockSearchResult, ExitSlip, ExitSlipFormData } from '../types';
import {
  INSTRUMENT_TYPE_OPTIONS, LONG_SHORT_OPTIONS, ORDER_TYPE_OPTIONS,
  TRADE_GRADE_OPTIONS, TRIGGER_SOURCE_OPTIONS,
} from '../constants';
import { createRecord, updateRecord, fetchExitSlips, updateExitSlip, deleteExitSlip, batchCreateExitSlips, fetchDailyOHLC } from '../services/record';
import { searchStocks } from '../services/stock';
import type { DailyOHLC } from '../services/record';
import { calcEntryScore, calcExitScore, calcChannelHeight, calcTradeScore, calcTradeGrade } from '../utils/scoreCalculator';
import { calcCommission, calcTransferFee, calcSlippageCost } from '../utils/tradingCostUtils';
import ExitSlipList from './ExitSlipList';
import ExitSlipModal from './ExitSlipModal';

interface Props {
  open: boolean;
  record: TradingRecord | null;
  onClose: () => void;
  onSuccess: () => void;
  /** 子单删除后刷新父表数据（不关闭表单），保持 remain_qty / gross_profit 同步 */
  onSlipDeleted?: () => void;
}

const TradingRecordForm: React.FC<Props> = ({ open, record, onClose, onSuccess, onSlipDeleted }) => {
  const { message } = App.useApp();
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [loadingExitSlips, setLoadingExitSlips] = useState(false);
  const [stockOptions, setStockOptions] = useState<{ value: string; label: string; code: string }[]>([]);
  const [exitSlips, setExitSlips] = useState<ExitSlip[]>([]);
  const [exitSlipModalOpen, setExitSlipModalOpen] = useState(false);
  const [editingSlip, setEditingSlip] = useState<ExitSlip | null>(null);
  const [snapshotMaxSellQty, setSnapshotMaxSellQty] = useState(0);
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const tempIdCounterRef = useRef(0);
  const dirtyFieldsRef = useRef<Set<string>>(new Set());
  const isEdit = !!record;

  // ────────── 自动计算得分 — 监听表单字段 ──────────

  const code = Form.useWatch('code', form);
  const entryDate = Form.useWatch('entry_date', form);
  const entryPrice = Form.useWatch('entry_price', form);
  const quantity = Form.useWatch('quantity', form);
  const longShort = Form.useWatch('long_short', form);

  const [entryDayOHLC, setEntryDayOHLC] = useState<DailyOHLC | null>(null);
  const [exitDayOHLC, setExitDayOHLC] = useState<DailyOHLC | null>(null);
  const initialLoadRef = useRef(true);

  // --- 从卖出记录推导有效出场数据（加权平均出场价 + 末笔子单日期） ---
  const slipDerivedData = useMemo(() => {
    if (exitSlips.length === 0) return null;
    const totalQty = exitSlips.reduce((sum, s) => sum + s.quantity, 0);
    if (totalQty === 0) return null;
    const weightedPrice = exitSlips.reduce((sum, s) => sum + s.exit_price * s.quantity, 0) / totalQty;
    const dates = exitSlips.map(s => s.exit_date).sort();
    return {
      exitPrice: Math.round(weightedPrice * 10000) / 10000,
      exitDate: dates[dates.length - 1],
    };
  }, [exitSlips]);

  // 有效出场日期（仅从卖出记录推导）
  const effectiveExitDate = useMemo(() => {
    if (slipDerivedData) return slipDerivedData.exitDate;
    return null;
  }, [slipDerivedData]);

  // 有效出场价（仅从卖出记录推导）
  const effectiveExitPrice = useMemo(() => {
    if (slipDerivedData) return slipDerivedData.exitPrice;
    return null;
  }, [slipDerivedData]);

  // 是否全部卖出
  const totalExitQty = useMemo(
    () => exitSlips.reduce((sum, slip) => sum + slip.quantity, 0),
    [exitSlips],
  );
  const entryQty = form.getFieldValue('quantity') || 0;
  const isFullySold = totalExitQty > 0 && totalExitQty >= entryQty;

  // 初始加载完成后，标记允许自动计算（编辑模式不覆盖已有值）
  useEffect(() => {
    if (open) {
      const t = setTimeout(() => { initialLoadRef.current = false; }, 0);
      return () => clearTimeout(t);
    } else {
      initialLoadRef.current = true;
      setEntryDayOHLC(null);
      setExitDayOHLC(null);
    }
  }, [open]);

  // 入场日期变化 → 异步获取入场日 OHLC
  useEffect(() => {
    if (!code || !entryDate) {
      setEntryDayOHLC(null);
      return;
    }
    const dateStr = dayjs.isDayjs(entryDate) ? entryDate.format('YYYY-MM-DD') : entryDate;
    if (!dateStr) return;

    const timer = setTimeout(async () => {
      const ohlc = await fetchDailyOHLC(code, dateStr);
      if (ohlc) {
        setEntryDayOHLC(ohlc);
        const ch = calcChannelHeight(ohlc.high, ohlc.low);
        form.setFieldsValue({ channel_height: ch });
        // 入场价已填写时，重新校验是否超出当日最高/最低价
        const ep = form.getFieldValue('entry_price');
        if (ep != null) form.validateFields(['entry_price']).catch(() => {});
      }
    }, 400);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [code, entryDate, open]);

  // 出场日期变化（仅从卖出记录推导） → 异步获取出场日 OHLC
  useEffect(() => {
    if (!code || !effectiveExitDate) {
      if (!slipDerivedData) setExitDayOHLC(null);
      return;
    }
    const dateStr = effectiveExitDate;
    if (!dateStr) return;

    const timer = setTimeout(async () => {
      const ohlc = await fetchDailyOHLC(code, dateStr);
      if (ohlc) {
        setExitDayOHLC(ohlc);
      }
    }, 400);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [code, effectiveExitDate, open]);

  // 卖出记录变化 → 自动汇总出场佣金、印花税、过户费
  useEffect(() => {
    const aggCommission = exitSlips.reduce((sum, s) => sum + (s.commission || 0), 0);
    const aggStampDuty = exitSlips.reduce((sum, s) => sum + (s.stamp_duty || 0), 0);
    const aggExitTransfer = exitSlips.reduce((sum, s) => sum + (s.transfer_fee || 0), 0);
    form.setFieldsValue({ commission_exit: Math.round(aggCommission * 100) / 100 });
    form.setFieldsValue({ stamp_duty: Math.round(aggStampDuty * 100) / 100 });

    // 过户费 = 入场过户费 + 出场过户费汇总
    const entryTransfer = Number(form.getFieldValue('transfer_fee')) || 0;
    form.setFieldsValue({ transfer_fee: Math.round((entryTransfer + aggExitTransfer) * 100) / 100 });
  }, [exitSlips, form]);

  // 入场价/数量变化 → 自动计算入场佣金、入场过户费和滑点（不覆盖用户手动编辑）
  useEffect(() => {
    if (entryPrice != null && quantity != null && Number.isFinite(entryPrice) && Number.isFinite(quantity)) {
      const p = Number(entryPrice);
      const q = Number(quantity);

      // 不覆盖用户手动编辑过的字段
      if (!dirtyFieldsRef.current.has('commission_entry')) {
        form.setFieldsValue({ commission_entry: calcCommission(p, q) });
      }
      if (!dirtyFieldsRef.current.has('transfer_fee')) {
        form.setFieldsValue({ transfer_fee: calcTransferFee(p, q) });
      }
      if (!dirtyFieldsRef.current.has('slip_point')) {
        form.setFieldsValue({ slip_point: Math.round(calcSlippageCost(p) * 10000) / 10000 });
      }
    }
  }, [entryPrice, quantity, form]);

  // 核心计算：入场价/出场价/方向/OHLC 变化 → 重算得分
  useEffect(() => {
    if (initialLoadRef.current) return;
    if (!entryDayOHLC) return;

    const ls = longShort || 'long';
    const ep = entryPrice;
    const ch = entryDayOHLC.high - entryDayOHLC.low;

    // 进场得分
    if (ep != null && Number.isFinite(ep)) {
      const es = calcEntryScore(Number(ep), entryDayOHLC.high, entryDayOHLC.low, ls);
      form.setFieldsValue({ entry_score: Math.round(es * 10) / 10 });
    }

    // 出场得分 + 总得分（需要出场价格和出场日 OHLC）
    const xp = effectiveExitPrice;
    if (xp != null && Number.isFinite(xp)) {
      // 出场得分使用出场日 OHLC
      if (exitDayOHLC) {
        const xs = calcExitScore(Number(xp), exitDayOHLC.high, exitDayOHLC.low, ls);
        form.setFieldsValue({ exit_score: Math.round(xs * 10) / 10 });
      }

      // 交易总得分使用进场日通道高度
      if (ep != null && Number.isFinite(ep) && ch > 0) {
        const ts = calcTradeScore(Number(ep), Number(xp), ch, ls);
        const rounded = Math.round(ts * 10) / 10;
        form.setFieldsValue({ trade_score: rounded });
        form.setFieldsValue({ trade_grade: calcTradeGrade(ts) });
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [entryPrice, effectiveExitPrice, effectiveExitDate, longShort, entryDayOHLC, exitDayOHLC, exitSlips, slipDerivedData]);

  // --- 加载已有卖出记录（编辑模式） ---
  useEffect(() => {
    if (open && record) {
      setLoadingExitSlips(true);
      fetchExitSlips(record.id)
        .then(slips => {
          setExitSlips(slips);
        })
        .catch(() => {
          message.warning('加载卖出记录失败，请检查网络连接');
        })
        .finally(() => {
          setLoadingExitSlips(false);
        });
    } else {
      setExitSlips([]);
    }
  }, [open, record, message]);

  // --- 表单初始值 ---
  useEffect(() => {
    if (open) {
      dirtyFieldsRef.current = new Set<string>();
      if (record) {
        // 编辑模式：已有费用值视为用户意图，标记为脏不自动覆盖
        dirtyFieldsRef.current.add('commission_entry');
        dirtyFieldsRef.current.add('transfer_fee');
        dirtyFieldsRef.current.add('slip_point');
        form.setFieldsValue({
          ...record,
          entry_date: record.entry_date ? dayjs(record.entry_date) : null,
          exit_date: record.exit_date ? dayjs(record.exit_date) : null,
        });
      } else {
        form.resetFields();
        form.setFieldsValue({
          instrument_type: 'stock',
          long_short: 'long',
          order_type: 'limit',
          quantity: 100,
          commission_entry: 0,
          commission_exit: 0,
          slip_point: 0,
          settlement_currency: 'CNY',
        });
      }
    }
  }, [open, record, form]);

  // --- 股票搜索（防抖） ---
  const handleStockSearch = useCallback((q: string) => {
    if (debounceTimer.current) clearTimeout(debounceTimer.current);
    if (!q || q.length < 1) {
      setStockOptions([]);
      return;
    }
    debounceTimer.current = setTimeout(async () => {
      try {
        const results = await searchStocks(q);
        setStockOptions(
          results.map((s: StockSearchResult) => ({
            value: s.code,
            label: `${s.code} ${s.name}`,
            code: s.code,
          })),
        );
      } catch {
        message.warning('股票搜索失败，请检查网络连接');
      }
    }, 300);
  }, [message]);

  useEffect(() => {
    return () => {
      if (debounceTimer.current) clearTimeout(debounceTimer.current);
    };
  }, []);

  const handleStockSelect = useCallback((_value: string, option: { label: string }) => {
    const name = option.label.replace(/^\d+\s*/, '');
    form.setFieldsValue({ security_name: name });
  }, [form]);

  // --- 卖出记录管理 ---
  const openNewExitSlip = useCallback(() => {
    setEditingSlip(null);
    setSnapshotMaxSellQty(Math.max(0, entryQty - totalExitQty));
    setExitSlipModalOpen(true);
  }, [entryQty, totalExitQty]);

  const editExitSlip = useCallback((slip: ExitSlip) => {
    setEditingSlip(slip);
    const maxQty = Math.max(0, entryQty - (totalExitQty - slip.quantity));
    setSnapshotMaxSellQty(maxQty);
    setExitSlipModalOpen(true);
  }, [entryQty, totalExitQty]);

  const saveExitSlip = useCallback(async (data: ExitSlipFormData, editing: ExitSlip | null) => {
    if (editing) {
      // 编辑已有子单 → 实时保存到后端
      await updateExitSlip(editing.id, data);
      setExitSlips(prev => prev.map(s => s.id === editing.id ? { ...s, ...data, id: s.id } : s));
      message.success('更新成功');
      setExitSlipModalOpen(false);
    } else {
      // 新增临时子单 → 暂存本地，主单保存后批量提交
      tempIdCounterRef.current -= 1;
      const tempId = tempIdCounterRef.current;
      const newSlip: ExitSlip = {
        id: tempId,
        record_id: record?.id || 0,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        ...data,
      } as ExitSlip;
      setExitSlips(prev => [...prev, newSlip]);
      setExitSlipModalOpen(false);
      message.success('已添加卖出记录，保存主记录时一并提交');
    }
  }, [record, message]);

  const removeExitSlip = useCallback(async (id: number) => {
    if (id < 0) {
      // 本地临时记录，直接删除
      setExitSlips(prev => prev.filter(s => s.id !== id));
      return;
    }
    // 已保存到后端的记录，调用删除接口
    await deleteExitSlip(id);
    setExitSlips(prev => prev.filter(s => s.id !== id));
    message.success('删除成功');
    // 仅刷新父表数据（remain_qty / gross_profit），不关闭表单，保留其余卖出记录
    onSlipDeleted?.();
  }, [message, onSlipDeleted]);

  // --- 价格合规校验（入场价/出场价在当日最高最低价范围内） ---
  const validatePriceAgainstOHLC = useCallback(async (): Promise<string | null> => {
    // 校验入场价
    const ep = form.getFieldValue('entry_price');
    const dateStr = dayjs.isDayjs(entryDate) ? entryDate.format('YYYY-MM-DD') : entryDate;
    if (ep != null && dateStr && code) {
      const ohlc = entryDayOHLC || await fetchDailyOHLC(code, dateStr);
      if (ohlc) {
        if (ep < ohlc.low || ep > ohlc.high) {
          return `入场价 ${ep} 不在 ${dateStr} 的价格范围 [${ohlc.low}, ${ohlc.high}] 内，请检查输入`;
        }
      }
    }

    // 校验每条卖出记录的出场价
    for (const slip of exitSlips) {
      if (slip.exit_price != null) {
        const slipDate = slip.exit_date;
        const ohlc = await fetchDailyOHLC(code, slipDate);
        if (ohlc) {
          if (slip.exit_price < ohlc.low || slip.exit_price > ohlc.high) {
            return `出场价 ${slip.exit_price} 不在 ${slipDate} 的价格范围 [${ohlc.low}, ${ohlc.high}] 内，请检查卖出记录`;
          }
        }
      }
    }

    return null;
  }, [code, entryDate, entryDayOHLC, exitSlips, form]);

  // --- 主表单提交 ---
  const handleSubmit = useCallback(async () => {
    try {
      const values = await form.validateFields();
      setLoading(true);

      // 价格合规校验
      const validationError = await validatePriceAgainstOHLC();
      if (validationError) {
        message.error(validationError);
        setLoading(false);
        return;
      }

      // 从卖出记录推导出场日期和出场价
      const derivedExitDate = slipDerivedData?.exitDate;
      const derivedExitPrice = slipDerivedData?.exitPrice;

      const data: TradingRecordFormData = {
        ...values,
        security_name: form.getFieldValue('security_name') || '',
        entry_date: values.entry_date?.format('YYYY-MM-DD'),
        // 出场日期和出场价仅从卖出记录推导，不保留手动输入
        exit_date: derivedExitDate || undefined,
        exit_price: derivedExitPrice || undefined,
      };

      // 清理空字段
      Object.keys(data).forEach(key => {
        const k = key as keyof TradingRecordFormData;
        if (data[k] === undefined || data[k] === null || data[k] === '') {
          delete data[k];
        }
      });

      // 收集本地新增的临时子单（id < 0）
      const localSlips = exitSlips.filter(s => s.id < 0).map(s => ({
        exit_date: s.exit_date,
        exit_price: s.exit_price,
        quantity: s.quantity,
        commission: s.commission,
        stamp_duty: s.stamp_duty,
        transfer_fee: s.transfer_fee,
        exit_reason: s.exit_reason ?? undefined,
        exit_score: s.exit_score ?? undefined,
        actual_stop_loss: s.actual_stop_loss ?? undefined,
        slip_point: s.slip_point,
      }));

      let recordId: number;
      if (isEdit) {
        await updateRecord(record!.id, data);
        recordId = record!.id;
      } else {
        recordId = await createRecord(data);
      }

      if (!recordId) {
        message.error('创建记录失败：返回数据异常');
        return;
      }

      // 批量提交本地新增的子单（仅针对新增的临时子单）
      if (localSlips.length > 0) {
        try {
          await batchCreateExitSlips(recordId, localSlips);
          // 全部卖出时，后端已更新 remain_qty 和 gross_profit，但需要更新得分
          if (isFullySold && derivedExitPrice != null && entryPrice != null && entryDayOHLC) {
            const ls = longShort || 'long';
            const ch = entryDayOHLC.high - entryDayOHLC.low;
            const es = calcEntryScore(Number(entryPrice), entryDayOHLC.high, entryDayOHLC.low, ls);
            let xs: number | null = null;
            if (exitDayOHLC) {
              xs = calcExitScore(Number(derivedExitPrice), exitDayOHLC.high, exitDayOHLC.low, ls);
            }
            const scoreData: Partial<TradingRecordFormData> = {
              entry_score: Math.round(es * 10) / 10,
              exit_score: xs != null ? Math.round(xs * 10) / 10 : undefined,
            };
            if (ch > 0) {
              const ts = calcTradeScore(Number(entryPrice), derivedExitPrice, ch, ls);
              scoreData.trade_score = Math.round(ts * 10) / 10;
              scoreData.trade_grade = calcTradeGrade(ts);
            }
            await updateRecord(recordId, scoreData);
          }
        } catch {
          setExitSlips(prev => prev.filter(s => s.id >= 0));
          message.warning(
            `主记录已保存，但 ${localSlips.length} 条卖出记录同步失败。请重新编辑该记录并添加卖出记录。`,
          );
        }
      } else if (isFullySold && derivedExitPrice != null && entryPrice != null && entryDayOHLC) {
        // 没有新增子单但已全部卖出（编辑场景），也更新得分
        const ls = longShort || 'long';
        const ch = entryDayOHLC.high - entryDayOHLC.low;
        const es = calcEntryScore(Number(entryPrice), entryDayOHLC.high, entryDayOHLC.low, ls);
        let xs: number | null = null;
        if (exitDayOHLC) {
          xs = calcExitScore(Number(derivedExitPrice), exitDayOHLC.high, exitDayOHLC.low, ls);
        }
        const scoreData: Partial<TradingRecordFormData> = {
          entry_score: Math.round(es * 10) / 10,
          exit_score: xs != null ? Math.round(xs * 10) / 10 : undefined,
        };
        if (ch > 0) {
          const ts = calcTradeScore(Number(entryPrice), derivedExitPrice, ch, ls);
          scoreData.trade_score = Math.round(ts * 10) / 10;
          scoreData.trade_grade = calcTradeGrade(ts);
        }
        await updateRecord(recordId, scoreData);
      }

      message.success(isEdit ? '更新成功' : '新增成功');
      onSuccess();
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'errorFields' in err) {
        return;
      }
      message.error(err instanceof Error ? err.message : '保存失败，请检查网络连接');
    } finally {
      setLoading(false);
    }
  }, [form, isEdit, record, exitSlips, message, onSuccess, slipDerivedData, isFullySold, entryPrice, entryDayOHLC, longShort, validatePriceAgainstOHLC]);

  return (
    <>
      <Modal
        title={isEdit ? '编辑交易记录' : '新增交易记录'}
        open={open}
        onCancel={onClose}
        onOk={handleSubmit}
        confirmLoading={loading}
        width={800}
        destroyOnClose
        okText="保存"
        cancelText="取消"
      >
        <Form form={form} layout="vertical" className="mt-4">
          {/* ---- 股票代码 & 名称 ---- */}
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                name="code"
                label="股票代码"
                rules={[{ required: true, message: '请输入股票代码' }]}
              >
                <AutoComplete
                  options={stockOptions}
                  onSearch={handleStockSearch}
                  onSelect={handleStockSelect}
                  placeholder="输入代码或名称搜索"
                />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="security_name" label="股票名称">
                <Input placeholder="自动补全" disabled />
              </Form.Item>
            </Col>
          </Row>

          {/* ---- 品种 / 方向 / 订单类型 ---- */}
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item name="instrument_type" label="品种" rules={[{ required: true }]}>
                <Select options={INSTRUMENT_TYPE_OPTIONS} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="long_short" label="方向" rules={[{ required: true }]}>
                <Select options={LONG_SHORT_OPTIONS} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="order_type" label="订单类型">
                <Select options={ORDER_TYPE_OPTIONS} />
              </Form.Item>
            </Col>
          </Row>

          {/* ---- 入场日期 / 入场价 / 数量 ---- */}
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item name="entry_date" label="入场日期" rules={[{ required: true, message: '请选择' }]}>
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item
                name="entry_price"
                label="入场价"
                rules={[
                  { required: true, message: '请输入' },
                  {
                    validator: (_, value) => {
                      if (value == null || !entryDayOHLC) return Promise.resolve();
                      const v = Number(value);
                      if (v > entryDayOHLC.high || v < entryDayOHLC.low) {
                        return Promise.reject(
                          new Error(`入场价 ${v} 超出当日范围 [${entryDayOHLC.low}, ${entryDayOHLC.high}]`),
                        );
                      }
                      return Promise.resolve();
                    },
                  },
                ]}
              >
                <InputNumber style={{ width: '100%' }} min={0} step={0.01} precision={4} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="quantity" label="数量(股)" rules={[{ required: true, message: '请输入' }]}>
                <InputNumber style={{ width: '100%' }} min={1} step={100} precision={0} />
              </Form.Item>
            </Col>
          </Row>

          {/* ---- 卖出记录列表卡片（委托子组件，统一通过此组件操作卖出） ---- */}
          <ExitSlipList
            exitSlips={exitSlips}
            entryQty={entryQty}
            totalExitQty={totalExitQty}
            loading={loadingExitSlips}
            onAdd={openNewExitSlip}
            onEdit={editExitSlip}
            onDelete={removeExitSlip}
          />

          {/* ---- 已全部卖出提示 ---- */}
          {isFullySold && (
            <div className="bg-green-50 text-green-700 text-xs px-3 py-2 rounded mb-4">
              已全部卖出，总得分将在保存后自动计算
            </div>
          )}

          {/* ---- 交易费用 ---- */}
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item
                name="commission_entry"
                label="入场佣金"
                tooltip="max(入场价×数量×手续费率, 最低5元)，从系统设置自动计算"
              >
                <InputNumber style={{ width: '100%' }} min={0} step={0.01} precision={4}
                  onChange={() => dirtyFieldsRef.current.add('commission_entry')} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item
                name="commission_exit"
                label="出场佣金（汇总）"
                tooltip="从卖出记录自动汇总"
              >
                <InputNumber style={{ width: '100%' }} min={0} step={0.01} precision={4} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item
                name="stamp_duty"
                label="印花税（汇总）"
                tooltip="出场价×数量×印花税率，仅卖出收取，从卖出记录自动汇总"
              >
                <InputNumber style={{ width: '100%' }} min={0} step={0.01} precision={4} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item
                name="transfer_fee"
                label="过户费（汇总）"
                tooltip="入场过户费 + 出场过户费汇总，从系统设置自动计算"
              >
                <InputNumber style={{ width: '100%' }} min={0} step={0.01} precision={4}
                  onChange={() => dirtyFieldsRef.current.add('transfer_fee')} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item
                name="slip_point"
                label="滑点(元/股)"
                tooltip="入场价×滑点率，从系统设置自动计算"
              >
                <InputNumber style={{ width: '100%' }} min={0} step={0.001} precision={4}
                  onChange={() => dirtyFieldsRef.current.add('slip_point')} />
              </Form.Item>
            </Col>
            <Col span={8} />
          </Row>

          {/* ---- 毛盈亏 / 通道高度 / 实际止损 ---- */}
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item name="gross_profit" label="毛盈亏" tooltip="应用层计算，可手动覆盖">
                <InputNumber style={{ width: '100%' }} step={0.01} precision={4} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="channel_height" label="通道高度" tooltip="进场当日日线振幅，用于计算总得分（自动填写）">
                <InputNumber style={{ width: '100%' }} min={0} step={0.01} precision={4} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="actual_stop_loss" label="实际止损价">
                <InputNumber style={{ width: '100%' }} min={0} step={0.01} precision={4} />
              </Form.Item>
            </Col>
          </Row>

          {/* ---- 评分 & 等级（原著公式自动计算） ---- */}
          <Row gutter={16}>
            <Col span={6}>
              <Form.Item
                name="entry_score"
                label="进场得分"
                tooltip="越低越好，≤50为合格（原著公式自动计算）"
              >
                <InputNumber style={{ width: '100%' }} step={0.1} precision={1} />
              </Form.Item>
            </Col>
            <Col span={6}>
              <Form.Item
                name="exit_score"
                label="出场得分"
                tooltip="越高越好，≥50为合格（原著公式自动计算）"
              >
                <InputNumber style={{ width: '100%' }} step={0.1} precision={1} />
              </Form.Item>
            </Col>
            <Col span={6}>
              <Form.Item
                name="trade_score"
                label="总得分"
                tooltip="负数=亏损，A>30 B≥10 C<10（原著公式自动计算，>100封顶）"
              >
                <InputNumber style={{ width: '100%' }} step={0.1} precision={1} />
              </Form.Item>
            </Col>
            <Col span={6}>
              <Form.Item name="trade_grade" label="等级">
                <Select allowClear placeholder="自动" options={TRADE_GRADE_OPTIONS} />
              </Form.Item>
            </Col>
          </Row>

          <Form.Item name="trigger_source" label="触发来源">
            <Select allowClear placeholder="选择触发来源" options={TRIGGER_SOURCE_OPTIONS} />
          </Form.Item>
        </Form>
      </Modal>

      {/* ---- 新增/编辑卖出记录弹窗（委托子组件） ---- */}
      <ExitSlipModal
        open={exitSlipModalOpen}
        editingSlip={editingSlip}
        snapshotMaxSellQty={snapshotMaxSellQty}
        code={code || ''}
        onSave={saveExitSlip}
        onCancel={() => setExitSlipModalOpen(false)}
      />
    </>
  );
};

export default TradingRecordForm;