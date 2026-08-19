/**
 * Login.tsx — 单密钥门禁登录页
 *
 * 功能：
 * - 输入门禁密码（access_key），调 /api/auth/login
 * - 登录成功后跳转主页（Cookie 由浏览器自动携带）
 * - 无 UI 框架依赖，纯 Ant Design + 全屏居中布局
 */
import React, { useState } from 'react';
import { Input, Button, Typography, message, Card } from 'antd';
import { KeyOutlined, LockOutlined } from '@ant-design/icons';
import axios from 'axios';

const { Title, Text } = Typography;

const Login: React.FC = () => {
  const [accessKey, setAccessKey] = useState('');
  const [loading, setLoading] = useState(false);

  const handleLogin = async () => {
    if (!accessKey.trim()) {
      message.warning('请输入门禁密码');
      return;
    }

    setLoading(true);
    try {
      const res = await axios.post('/api/auth/login', { access_key: accessKey.trim() }, {
        withCredentials: true,
      });
      const body = res.data;
      if (body.code === 200) {
        message.success('登录成功');
        // 登录成功后跳转主页，Cookie 由浏览器自动携带
        window.location.href = '/';
      } else {
        message.error(body.message || '登录失败');
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '网络连接失败';
      message.error('登录失败: ' + msg);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleLogin();
    }
  };

  return (
    <div className="h-screen w-screen flex items-center justify-center bg-bg-base">
      <Card
        className="w-96 shadow-lg"
        styles={{ body: { padding: '40px 32px' } }}
      >
        <div className="text-center mb-8">
          <LockOutlined className="text-4xl text-color-accent mb-4" />
          <Title level={3} className="!mb-1">QuantPro</Title>
          <Text type="secondary">请输入门禁密码以继续</Text>
        </div>

        <div className="flex flex-col gap-4">
          <Input.Password
            size="large"
            prefix={<KeyOutlined />}
            placeholder="门禁密码"
            value={accessKey}
            onChange={(e) => setAccessKey(e.target.value)}
            onKeyDown={handleKeyDown}
            autoFocus
          />
          <Button
            type="primary"
            size="large"
            block
            loading={loading}
            onClick={handleLogin}
          >
            {loading ? '验证中...' : '登 录'}
          </Button>
        </div>
      </Card>
    </div>
  );
};

export default Login;