import React from 'react';
import { Card, Radio, Space, Typography, Divider, Tag } from 'antd';
import { BgColorsOutlined } from '@ant-design/icons';
import { useSettings, COLOR_SCHEMES, ColorScheme } from '@/shared/contexts/SettingsContext';

const { Title, Text } = Typography;

const Config: React.FC = () => {
  const { colorScheme, setColorScheme, colors } = useSettings();

  return (
    <div className="h-full overflow-auto bg-bg-base p-6">
      <div className="max-w-3xl mx-auto">
        <Title level={3} className="!text-text-primary !mb-2">
          <BgColorsOutlined className="mr-2" />
          系统设置
        </Title>
        <Text className="text-text-secondary">
          个性化配置项，设置会保存在浏览器本地，跨会话生效。
        </Text>

        <Divider className="!border-border-color" />

        <Card
          className="!bg-bg-panel !border-border-color"
          title={<span className="!text-text-primary">涨跌颜色方案</span>}
          extra={
            <Tag color="blue" className="!border-0">
              当前：{COLOR_SCHEMES[colorScheme].label}
            </Tag>
          }
        >
          <Text className="!text-text-secondary block mb-3">
            控制股票列表中价格和涨跌幅的显示颜色：
          </Text>

          <Radio.Group
            value={colorScheme}
            onChange={(e) => setColorScheme(e.target.value as ColorScheme)}
            className="w-full"
          >
            <Space direction="vertical" size="middle" className="w-full">
              {(Object.keys(COLOR_SCHEMES) as ColorScheme[]).map((key) => {
                const opt = COLOR_SCHEMES[key];
                const checked = colorScheme === key;
                return (
                  <div
                    key={key}
                    data-testid={`color-scheme-${key}`}
                    className={`flex items-center justify-between p-3 rounded border cursor-pointer transition-colors ${
                      checked
                        ? 'border-color-accent bg-color-accent/5'
                        : 'border-border-color hover:border-text-secondary'
                    }`}
                    onClick={() => setColorScheme(key)}
                  >
                    <div className="flex items-center gap-3">
                      <Radio value={key} />
                      <div>
                        <div className="text-text-primary font-medium">{opt.label}</div>
                        <Text className="!text-text-secondary text-xs">
                          {opt.description}
                        </Text>
                      </div>
                    </div>
                    <Space size="small">
                      <span
                        data-testid={`scheme-${key}-up-block`}
                        className="px-3 py-1 rounded font-mono text-sm text-white"
                        style={{ backgroundColor: opt.colors.up }}
                      >
                        涨
                      </span>
                      <span
                        data-testid={`scheme-${key}-down-block`}
                        className="px-3 py-1 rounded font-mono text-sm text-white"
                        style={{ backgroundColor: opt.colors.down }}
                      >
                        跌
                      </span>
                    </Space>
                  </div>
                );
              })}
            </Space>
          </Radio.Group>

          <Divider className="!my-4 !border-border-color" />

          <div className="flex items-center text-text-secondary text-sm">
            <span>预览：</span>
            <span
              data-testid="preview-up-block"
              className="px-3 py-1 rounded font-mono text-sm text-white ml-2"
              style={{ backgroundColor: colors.up }}
            >
              涨 ↑
            </span>
            <span
              data-testid="preview-down-block"
              className="px-3 py-1 rounded font-mono text-sm text-white ml-2"
              style={{ backgroundColor: colors.down }}
            >
              跌 ↓
            </span>
          </div>
        </Card>
      </div>
    </div>
  );
};

export default Config;
