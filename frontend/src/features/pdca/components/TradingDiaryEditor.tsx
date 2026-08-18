/**
 * TradingDiaryEditor.tsx — 交易日记编辑器
 *
 * 功能：
 * - 绑定交易记录（选择关联的交易）
 * - 情绪记录 + 复盘文本
 * - 附件上传（图片 ≤10MB）
 * - 日记列表查看
 */

import React, { useState, useCallback, useEffect, useRef } from 'react';
import {
  Button, Input, Select, Upload, List, Typography, App, Space, Tag, Empty, Spin, Alert,
} from 'antd';
import { UploadOutlined, FileImageOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import type { TradingDiary, TradingDiaryFormData, TradingRecord, PDCACycle } from '../types';
import { fetchDiaries, createDiary, updateDiary, uploadDiaryAttachment } from '../services/diary';
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
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [selectedRecordId, setSelectedRecordId] = useState<number | null>(null);
  const [emotionNote, setEmotionNote] = useState('');
  const [reviewText, setReviewText] = useState('');
  const [editingDiaryId, setEditingDiaryId] = useState<number | null>(null);
  const [uploading, setUploading] = useState(false);
  const mountedRef = useRef(true);

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
    loadRecords();
    loadDiaries();
    return () => { mountedRef.current = false; };
  }, [loadActiveCycle, loadRecords, loadDiaries]);

  const handleSave = useCallback(async () => {
    if (!reviewText.trim()) {
      message.warning('请输入复盘内容');
      return;
    }
    setSaving(true);
    try {
      const data: TradingDiaryFormData = {
        review_text: reviewText.trim(),
        pdca_cycle_id: activeCycle?.id, // 从当前活跃周期获取，确保日记正确关联
      };
      if (selectedRecordId) data.trading_record_id = selectedRecordId;
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

  const handleEdit = useCallback((diary: TradingDiary) => {
    setEditingDiaryId(diary.id);
    setSelectedRecordId(diary.trading_record_id);
    setEmotionNote(diary.emotion_note || '');
    setReviewText(diary.review_text);
  }, []);

  const handleCancelEdit = useCallback(() => {
    setEditingDiaryId(null);
    setSelectedRecordId(null);
    setEmotionNote('');
    setReviewText('');
  }, []);

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
            renderItem={(diary) => (
              <List.Item
                className="cursor-pointer hover:bg-bg-card/50 px-3 rounded"
                onClick={() => handleEdit(diary)}
                actions={[
                  diary.attach_file_paths?.length > 0 ? (
                    <Tag icon={<FileImageOutlined />} color="blue">{diary.attach_file_paths.length}</Tag>
                  ) : null,
                ].filter(Boolean)}
              >
                <List.Item.Meta
                  title={
                    <Space>
                      <Text className="text-text-primary text-sm">
                        {diary.trading_record_id ? `关联交易 #${diary.trading_record_id}` : '独立日记'}
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
            )}
          />
        )}
      </div>

      {/* 右侧：编辑器 */}
      <div className="w-1/2 flex flex-col p-4">
        <Text className="text-text-primary font-semibold mb-3 block">
          {editingDiaryId ? '编辑日记' : '新建日记'}
        </Text>

        {activeCycle === null && (
          <Alert
            type="warning"
            message="当前无活跃周期，日记将保存为独立记录（不关联周期）"
            className="mb-3"
            showIcon
          />
        )}

        <div className="mb-3">
          <Text className="text-text-secondary text-xs mb-1 block">关联交易记录</Text>
          <Select
            placeholder="选择关联交易（可选）"
            value={selectedRecordId}
            onChange={setSelectedRecordId}
            allowClear
            showSearch
            optionFilterProp="label"
            style={{ width: '100%' }}
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
          />
        </div>

        {/* 附件上传（编辑模式下显示） */}
        {editingDiaryId && (
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

        <div className="flex gap-2">
          <Button type="primary" onClick={handleSave} loading={saving}>
            {editingDiaryId ? '更新' : '保存'}
          </Button>
          {editingDiaryId && (
            <Button onClick={handleCancelEdit}>取消</Button>
          )}
        </div>
      </div>
    </div>
  );
};

export default TradingDiaryEditor;