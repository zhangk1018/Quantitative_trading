/**
 * TradingDiaryEditor.tsx — 交易日记编辑器
 *
 * 功能：
 * - 绑定交易记录（选择关联的交易）
 * - 情绪记录 + 复盘文本
 * - 附件上传（图片 ≤10MB）
 * - 日记列表查看
 */

import React, { useState, useCallback, useEffect, useMemo, useRef } from 'react';
import {
  Button, Input, Select, Upload, List, Typography, App, Space, Tag, Empty, Spin, Alert, Popconfirm,
} from 'antd';
import { UploadOutlined, FileImageOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import type { TradingDiary, TradingDiaryFormData, TradingRecord, PDCACycle } from '../types';
import { fetchDiaries, createDiary, updateDiary, deleteDiary, uploadDiaryAttachment } from '../services/diary';
import { fetchRecords } from '../services/record';
import { fetchCycles } from '../services/cycle';
import { DEFAULT_PAGE_SIZE } from '@/config/constants';

const { TextArea } = Input;
const { Text } = Typography;

const TradingDiaryEditor: React.FC = () => {
  const { message } = App.useApp();
  const [diaries, setDiaries] = useState<TradingDiary[]>([]);
  const [records, setRecords] = useState<TradingRecord[]>([]);
  const [activeCycle, setActiveCycle] = useState<PDCACycle | null>(null);
  const [cycles, setCycles] = useState<PDCACycle[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [selectedRecordId, setSelectedRecordId] = useState<number | null>(null);
  const [emotionNote, setEmotionNote] = useState('');
  const [reviewText, setReviewText] = useState('');
  const [editingDiaryId, setEditingDiaryId] = useState<number | null>(null);
  const [uploading, setUploading] = useState(false);
  const [isViewOnly, setIsViewOnly] = useState(false); // 已闭环周期日记 → 只读查看模式
  const mountedRef = useRef(true);

  // 周期 id → 状态 映射：用于「未闭环才可删改」判断（协作单 [27.0]）
  const cycleStatusMap = useMemo(() => new Map(cycles.map((c) => [c.id, c.status])), [cycles]);

  // 获取当前活跃周期（DO 状态），用于日记关联
  const loadActiveCycle = useCallback(async () => {
    try {
      const items = await fetchCycles({ status: 'DO' });
      if (!mountedRef.current) return;
      if (items.length > 0) setActiveCycle(items[0]);
    } catch (err) {
      if (!mountedRef.current) return;
      message.error(err instanceof Error ? err.message : '获取当前周期失败');
    }
  }, [message]);

  // 加载全部周期（含历史），用于判断日记所属周期是否已闭环
  const loadCycles = useCallback(async () => {
    try {
      const items = await fetchCycles({});
      if (!mountedRef.current) return;
      setCycles(items);
    } catch (err) {
      if (!mountedRef.current) return;
      message.error(err instanceof Error ? err.message : '加载周期列表失败');
    }
  }, [message]);

  // 加载交易记录列表（用于下拉选择）
  const loadRecords = useCallback(async () => {
    try {
      const result = await fetchRecords({ page_size: DEFAULT_PAGE_SIZE, sort_by: 'entry_date', sort_asc: false });
      if (!mountedRef.current) return;
      setRecords(result.items || []);
    } catch (err) {
      if (!mountedRef.current) return;
      message.error(err instanceof Error ? err.message : '加载交易记录失败');
    }
  }, [message]);

  // 加载日记列表
  const loadDiaries = useCallback(async () => {
    setLoading(true);
    try {
      const result = await fetchDiaries({});
      if (!mountedRef.current) return;
      setDiaries(result.items || []);
    } catch (err) {
      if (!mountedRef.current) return;
      message.error(err instanceof Error ? err.message : '加载日记列表失败');
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, [message]);

  useEffect(() => {
    mountedRef.current = true;
    loadActiveCycle();
    loadCycles();
    loadRecords();
    loadDiaries();
    return () => { mountedRef.current = false; };
  }, [loadActiveCycle, loadCycles, loadRecords, loadDiaries]);

  const handleSave = useCallback(async () => {
    if (!reviewText.trim()) {
      message.warning('请输入复盘内容');
      return;
    }
    // 需求①：日记必须关联交易，不允许「独立日记」（协作单 [27.0]）
    if (!selectedRecordId) {
      message.warning('请先选择关联的交易记录（日记必须关联交易）');
      return;
    }
    if (!editingDiaryId && !activeCycle) {
      message.warning('当前无活跃周期，无法新建日记，请先在周期总览新建周期');
      return;
    }
    setSaving(true);
    try {
      const data: TradingDiaryFormData = {
        review_text: reviewText.trim(),
        pdca_cycle_id: activeCycle?.id, // 从当前活跃周期获取，确保日记正确关联
      };
      data.trading_record_id = selectedRecordId;
      if (emotionNote.trim()) data.emotion_note = emotionNote.trim();

      if (editingDiaryId) {
        await updateDiary(editingDiaryId, data);
      } else {
        await createDiary(data);
      }
      message.success(editingDiaryId ? '更新成功' : '保存成功');
      setReviewText('');
      setEmotionNote('');
      setSelectedRecordId(null);
      setEditingDiaryId(null);
      loadDiaries();
    } catch (err) {
      message.error(err instanceof Error ? err.message : '保存失败');
    } finally {
      setSaving(false);
    }
  }, [reviewText, emotionNote, selectedRecordId, editingDiaryId, message, loadDiaries, activeCycle]);

  // 当前右侧正在查看/编辑的日记（用于右侧「删除」按钮）
  const currentDiary = useMemo(
    () => diaries.find((d) => d.id === editingDiaryId) || null,
    [diaries, editingDiaryId],
  );

  // 点击左侧列表项：将日记展示到右侧。已闭环周期 → 只读查看，未闭环 → 进入编辑
  const handleSelect = useCallback((diary: TradingDiary) => {
    const closed = cycleStatusMap.get(diary.pdca_cycle_id) === 'DONE';
    setEditingDiaryId(diary.id);
    setSelectedRecordId(diary.trading_record_id);
    setEmotionNote(diary.emotion_note || '');
    setReviewText(diary.review_text);
    setIsViewOnly(closed);
  }, [cycleStatusMap]);

  // 需求③：左侧「编辑」按钮（仅未闭环显示），已闭环周期仅可查看
  const handleEdit = useCallback((diary: TradingDiary) => {
    if (cycleStatusMap.get(diary.pdca_cycle_id) === 'DONE') {
      message.warning('该日记所属周期已闭环，仅可查看，不可修改');
      return;
    }
    setEditingDiaryId(diary.id);
    setSelectedRecordId(diary.trading_record_id);
    setEmotionNote(diary.emotion_note || '');
    setReviewText(diary.review_text);
    setIsViewOnly(false);
  }, [cycleStatusMap, message]);

  // 需求②：选择关联交易时，若该交易已有日记则自动带出（编辑既有日记）
  // 与左侧列表逻辑一致：所属周期已闭环 → 只读查看（仅「关闭」按钮）
  const handleRecordChange = useCallback((recordId: number | null) => {
    setSelectedRecordId(recordId);
    if (recordId == null) {
      setIsViewOnly(false);
      return;
    }
    const existing = diaries
      .filter((d) => d.trading_record_id === recordId)
      .sort((a, b) => dayjs(b.created_at).valueOf() - dayjs(a.created_at).valueOf())[0];
    if (existing) {
      const closed = cycleStatusMap.get(existing.pdca_cycle_id) === 'DONE';
      setEditingDiaryId(existing.id);
      setEmotionNote(existing.emotion_note || '');
      setReviewText(existing.review_text);
      setIsViewOnly(closed);
      message.info(closed
        ? '已带出该交易关联的既有日记（所属周期已闭环，仅可查看）'
        : '已带出该交易关联的既有日记，可直接编辑');
    } else {
      // 该交易无既有日记：清空编辑态，进入「新建」模式
      setEditingDiaryId(null);
      setEmotionNote('');
      setReviewText('');
      setIsViewOnly(false);
    }
  }, [diaries, cycleStatusMap, message]);

  const handleCancelEdit = useCallback(() => {
    setEditingDiaryId(null);
    setSelectedRecordId(null);
    setEmotionNote('');
    setReviewText('');
    setIsViewOnly(false);
  }, []);

  // 需求③：删除日记（未闭环才允许），软删除（协作单 [27.0]）
  const handleDelete = useCallback(async (diary: TradingDiary) => {
    if (cycleStatusMap.get(diary.pdca_cycle_id) === 'DONE') {
      message.warning('该日记所属周期已闭环，仅可查看，不可删除');
      return;
    }
    try {
      await deleteDiary(diary.id);
      message.success('删除成功');
      if (editingDiaryId === diary.id) handleCancelEdit();
      loadDiaries();
    } catch (err) {
      message.error(err instanceof Error ? err.message : '删除失败');
    }
  }, [cycleStatusMap, editingDiaryId, handleCancelEdit, loadDiaries, message]);

  const handleUpload = useCallback(async (diaryId: number, file: File) => {
    setUploading(true);
    try {
      await uploadDiaryAttachment(diaryId, file);
      message.success('上传成功');
      loadDiaries();
    } catch (err) {
      message.error(err instanceof Error ? err.message : '上传失败');
    } finally {
      setUploading(false);
    }
  }, [message, loadDiaries]);

  return (
    <div className="h-full flex">
      {/* 左侧：日记列表 */}
      <div className="w-1/2 border-r border-border-color overflow-auto p-4">
        <Text className="text-text-primary font-semibold mb-3 block">交易日记列表</Text>
        {loading ? (
          <div className="flex justify-center py-8"><Spin /></div>
        ) : diaries.length === 0 ? (
          <Empty description="暂无日记" />
        ) : (
          <List
            dataSource={diaries}
            renderItem={(diary) => {
              const isClosed = cycleStatusMap.get(diary.pdca_cycle_id) === 'DONE';
              return (
                <List.Item
                  className="cursor-pointer hover:bg-bg-card/50 px-3 rounded"
                  onClick={() => handleSelect(diary)}
                  actions={[
                    diary.attach_file_paths?.length > 0 ? (
                      <Tag icon={<FileImageOutlined />} color="blue">{diary.attach_file_paths.length}</Tag>
                    ) : null,
                    // 需求③：未闭环才显示「编辑」按钮
                    !isClosed ? (
                      <Button
                        key="edit"
                        type="text"
                        size="small"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleEdit(diary);
                        }}
                      >
                        编辑
                      </Button>
                    ) : null,
                    // 需求③：未闭环才显示「删除」按钮，闭环周期不渲染
                    !isClosed ? (
                      <Popconfirm
                        key="del"
                        title="确认删除该日记？"
                        description="删除后不可恢复"
                        onConfirm={() => handleDelete(diary)}
                        okText="删除"
                        cancelText="取消"
                      >
                        <Button
                          type="text"
                          danger
                          size="small"
                          onClick={(e) => e.stopPropagation()}
                        >
                          删除
                        </Button>
                      </Popconfirm>
                    ) : null,
                  ].filter(Boolean)}
                >
                  <List.Item.Meta
                    title={
                      <Space>
                        <Text className="text-text-primary text-sm">
                          {diary.trading_record_id ? `关联交易 #${diary.trading_record_id}` : '未关联交易'}
                        </Text>
                        <Text className="text-text-secondary text-xs">
                          {dayjs(diary.created_at).format('MM-DD HH:mm')}
                        </Text>
                      </Space>
                    }
                    description={
                      <Text className="text-text-secondary text-xs" style={{ display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 300 }}>
                        {diary.review_text}
                      </Text>
                    }
                  />
                </List.Item>
              );
            }}
          />
        )}
      </div>

      {/* 右侧：编辑器/查看器 */}
      <div className="w-1/2 flex flex-col p-4">
        <Text className="text-text-primary font-semibold mb-3 block">
          {isViewOnly ? '查看日记' : (editingDiaryId ? '编辑日记' : '新建日记')}
        </Text>

        {activeCycle === null && !isViewOnly && (
          <Alert
            type="warning"
            message="当前无活跃周期，无法新建日记；请先在周期总览新建周期（未闭环）"
            className="mb-3"
            showIcon
          />
        )}

        <div className="mb-3">
          <Text className="text-text-secondary text-xs mb-1 block">关联交易记录 *</Text>
          <Select
            placeholder="请选择关联的交易记录（必选，日记必须关联交易）"
            value={selectedRecordId}
            onChange={handleRecordChange}
            showSearch
            optionFilterProp="label"
            style={{ width: '100%' }}
            disabled={isViewOnly}
            options={records.map((r) => ({
              value: r.id,
              label: `${r.code} ${r.security_name} | ${r.entry_date} ${r.long_short === 'long' ? '做多' : '做空'}`,
            }))}
          />
        </div>

        <div className="mb-3">
          <Text className="text-text-secondary text-xs mb-1 block">情绪记录</Text>
          <Input
            placeholder="记录交易时的情绪状态..."
            value={emotionNote}
            onChange={(e) => setEmotionNote(e.target.value)}
            maxLength={500}
            disabled={isViewOnly}
          />
        </div>

        <div className="flex-1 mb-3 flex flex-col min-h-0">
          <Text className="text-text-secondary text-xs mb-1 block">复盘内容 *</Text>
          <TextArea
            className="flex-1"
            placeholder="写下游击手的复盘总结..."
            value={reviewText}
            onChange={(e) => setReviewText(e.target.value)}
            maxLength={5000}
            showCount
            disabled={isViewOnly}
            autoSize={{ minRows: 12, maxRows: 30 }} // 需求④：复盘窗口高度提升至原来的约3倍
          />
        </div>

        {/* 附件上传（编辑模式下显示） */}
        {editingDiaryId && !isViewOnly && (
          <div className="mb-3">
            <Upload
              beforeUpload={(file) => {
                const isImage = file.type.startsWith('image/');
                const isLt10M = file.size / 1024 / 1024 < 10;
                if (!isImage) {
                  message.error('仅支持图片文件');
                  return false;
                }
                if (!isLt10M) {
                  message.error('文件大小不超过 10MB');
                  return false;
                }
                handleUpload(editingDiaryId, file);
                return false;
              }}
              showUploadList={false}
              disabled={uploading}
            >
              <Button icon={<UploadOutlined />} loading={uploading}>上传附件</Button>
            </Upload>
          </div>
        )}

        {/* 需求⑥：保存/取消/删除 置于右下角；需求⑤：按钮统一为「保存」+ 独立「删除」 */}
        <div className="flex justify-end gap-2 mt-auto pt-2">
          <Button onClick={handleCancelEdit}>{isViewOnly ? '关闭' : '取消'}</Button>
          {!isViewOnly && editingDiaryId && currentDiary && (
            <Button danger onClick={() => handleDelete(currentDiary)}>删除</Button>
          )}
          {!isViewOnly && (
            <Button type="primary" onClick={handleSave} loading={saving}>
              保存
            </Button>
          )}
        </div>
      </div>
    </div>
  );
};

export default TradingDiaryEditor;