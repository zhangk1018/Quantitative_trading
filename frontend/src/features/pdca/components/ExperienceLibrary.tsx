/**
 * ExperienceLibrary.tsx — 经验知识库（只读浏览）
 *
 * 功能：
 * - 展示冻结经验条目（标题 / 标签 / 创建时间 / 正文详情）
 * - 标签筛选（服务端 tags 全部命中）
 * - 关键词搜索（标题/内容模糊匹配）
 * - 分页浏览
 *
 * 数据来源：GET /api/pdca/experiences（协作单 [21.0]，量量实现中）
 * 经验由 Act 模块「冻结经验」自动落库，本模块只读，不提供编辑/删除。
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  Card, Button, Spin, Empty, message, Tag, Input, Space, Typography,
  List, Select, Pagination, Collapse,
} from 'antd';
import { ReloadOutlined, BulbOutlined } from '@ant-design/icons';
import type { TradeExperience } from '../types';
import { fetchExperiences } from '../services/experience';
import { extractErrorMessage } from '../services/client';

const { Title, Text } = Typography;
const { Search } = Input;

const PAGE_SIZE = 10;

/** 经验正文节标题（与后端 act_record._sync_trade_experience 的拼装格式一致） */
const SECTION_TITLES = ['问题清单', '改进计划', '下一周期目标'] as const;
type SectionTitle = (typeof SECTION_TITLES)[number];

interface ContentSection {
  title: SectionTitle | '';
  body: string;
}

/** 按【节标题】行拆分经验正文为节数组；节外行归入当前节 */
function parseContentSections(content: string): ContentSection[] {
  const sections: ContentSection[] = [];
  let current: ContentSection | null = null;
  for (const line of content.split('\n')) {
    const m = line.match(/^【(.+?)】$/);
    if (m && (SECTION_TITLES as readonly string[]).includes(m[1])) {
      current = { title: m[1] as SectionTitle, body: '' };
      sections.push(current);
    } else if (current) {
      current.body += (current.body ? '\n' : '') + line;
    }
  }
  // 兜底：正文不以任何【节标题】开头（历史/异常数据），整体归为一段
  return sections.length > 0 ? sections : [{ title: '', body: content }];
}

/** 格式化 ISO 时间为本地可读字符串（YYYY-MM-DD HH:mm） */
function formatTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

const ExperienceLibrary: React.FC = () => {
  const [items, setItems] = useState<TradeExperience[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [keyword, setKeyword] = useState('');
  const [selectedTags, setSelectedTags] = useState<string[]>([]);

  // 标签候选（从当前已加载数据汇总，供下拉选择；也可手动输入）
  const [tagOptions, setTagOptions] = useState<{ label: string; value: string }[]>([]);

  // 竞态防护：递增请求序号，仅最新一次请求的结果被采纳
  const seqRef = useRef(0);

  const load = useCallback(async (p: number, kw: string, tags: string[]) => {
    const seq = ++seqRef.current;
    setLoading(true);
    try {
      const result = await fetchExperiences({
        page: p,
        page_size: PAGE_SIZE,
        keyword: kw || undefined,
        tags: tags.length > 0 ? tags : undefined,
      });
      if (seq !== seqRef.current) return;  // 过期请求，丢弃
      setItems(result.items);
      setTotal(result.total);
      // 汇总标签候选（去重）
      const tagSet = new Set<string>();
      result.items.forEach((item) => (item.tags || []).forEach((t) => tagSet.add(t)));
      setTagOptions(Array.from(tagSet).map((t) => ({ label: t, value: t })));
    } catch (err: unknown) {
      if (seq !== seqRef.current) return;  // 过期请求，丢弃错误
      message.error('加载经验失败: ' + extractErrorMessage(err));
    } finally {
      if (seq === seqRef.current) setLoading(false);
    }
  }, []);

  // 初始加载
  useEffect(() => {
    load(1, '', []);
  }, [load]);

  const handleSearch = (value: string) => {
    const kw = value.trim();
    setKeyword(kw);
    setPage(1);
    load(1, kw, selectedTags);
  };

  const handleTagsChange = (tags: string[]) => {
    setSelectedTags(tags);
    setPage(1);
    load(1, keyword, tags);
  };

  const handlePageChange = (p: number) => {
    setPage(p);
    load(p, keyword, selectedTags);
  };

  const handleRefresh = () => {
    load(page, keyword, selectedTags);
  };

  return (
    <div className="p-4">
      {/* 顶部操作栏 */}
      <div className="flex items-center justify-between mb-4">
        <Title level={5} className="!mb-0">
          <BulbOutlined className="mr-2" />经验知识库
        </Title>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={handleRefresh} size="small">刷新</Button>
        </Space>
      </div>

      {/* 筛选区：关键词搜索 + 标签筛选 */}
      <div className="mb-4 flex items-center gap-3 flex-wrap">
        <Search
          placeholder="搜索经验标题/内容..."
          allowClear
          enterButton
          onSearch={handleSearch}
          style={{ width: 280 }}
        />
        <Select
          mode="multiple"
          allowClear
          placeholder="按标签筛选（可输入自定义标签）"
          value={selectedTags}
          onChange={handleTagsChange}
          options={tagOptions}
          tokenSeparators={[',']}
          maxTagCount="responsive"
          style={{ minWidth: 260, maxWidth: 420 }}
        />
        {total > 0 && <Text type="secondary">共 {total} 条经验</Text>}
      </div>

      {loading ? (
        <div className="flex justify-center py-16"><Spin tip="加载中..." /></div>
      ) : items.length === 0 ? (
        <Empty description={keyword || selectedTags.length > 0 ? '没有匹配的经验，调整筛选条件试试' : '暂无冻结经验，在「改进措施」中开启冻结经验后自动沉淀于此'} />
      ) : (
        <div>
          <List
            dataSource={items}
            renderItem={(item) => (
              <List.Item className="!block mb-3">
                <Card size="small" className="mb-2">
                  <div className="flex items-start justify-between gap-3 mb-2">
                    <div className="flex-1 min-w-0">
                      <Text strong className="text-base">{item.title}</Text>
                    </div>
                    <Text type="secondary" className="text-xs whitespace-nowrap">{formatTime(item.created_at)}</Text>
                  </div>

                  {item.tags && item.tags.length > 0 && (
                    <div className="mb-2 flex flex-wrap gap-1.5">
                      {item.tags.map((tag, idx) => (
                        <Tag key={idx} color="blue">{tag}</Tag>
                      ))}
                    </div>
                  )}

                  <Collapse
                    ghost
                    className="!bg-transparent"
                    items={[
                      {
                        key: 'detail',
                        label: <Text type="secondary" className="text-xs">查看详情</Text>,
                        children: (
                          <div className="text-sm text-text-primary">
                            {parseContentSections(item.content || '').map((sec, idx) => (
                              <div key={idx} className={idx > 0 ? 'mt-3' : ''}>
                                {sec.title && <Text strong className="block mb-1">{sec.title}</Text>}
                                <div className="whitespace-pre-wrap">{sec.body}</div>
                              </div>
                            ))}
                          </div>
                        ),
                      },
                    ]}
                  />
                </Card>
              </List.Item>
            )}
          />

          {/* 分页 */}
          <div className="flex justify-end mt-2">
            <Pagination
              current={page}
              pageSize={PAGE_SIZE}
              total={total}
              showSizeChanger={false}
              showTotal={(t) => `共 ${t} 条`}
              onChange={handlePageChange}
            />
          </div>
        </div>
      )}
    </div>
  );
};

export default ExperienceLibrary;
