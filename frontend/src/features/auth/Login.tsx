/**
 * Login.tsx — 多用户账号体系登录页
 *
 * 功能（方案 §5）：
 * - 用户名 + 密码登录，调 POST /api/auth/login（成功下发 HttpOnly Cookie）
 * - 按响应 code 区分提示：bad_credentials（密码错）/ disabled（已禁用）/ db_unavailable（服务不可用）
 * - 注册入口按 `GET /api/auth/config` 的 auth_allow_register 显隐
 * - 登录成功后进入主页；已登录时直接跳转主页
 */
import React, { useEffect, useState } from 'react';
import { Input, Button, Typography, message, Card } from 'antd';
import { UserOutlined, LockOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useAuth } from './AuthContext';
import { parseAuthError } from './api';

const { Title, Text } = Typography;

const Login: React.FC = () => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const { user, allowRegister, login } = useAuth();

  // 已登录（含改密后重新进入）直接回主页
  useEffect(() => {
    if (user) navigate('/', { replace: true });
  }, [user, navigate]);

  const reportError = (err: unknown) => {
    const { code, message: msg } = parseAuthError(err);
    switch (code) {
      case 'bad_credentials':
        message.error('用户名或密码错误');
        break;
      case 'disabled':
        message.error('账号已被禁用，请联系管理员');
        break;
      case 'db_unavailable':
        message.error('认证服务暂时不可用，请稍后重试');
        break;
      default:
        message.error('登录失败：' + msg);
    }
  };

  const handleLogin = async () => {
    if (!username.trim()) {
      message.warning('请输入用户名');
      return;
    }
    if (!password) {
      message.warning('请输入密码');
      return;
    }

    setLoading(true);
    try {
      await login(username.trim(), password);
      message.success('登录成功');
      navigate('/', { replace: true });
    } catch (err: unknown) {
      reportError(err);
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
          <Text type="secondary">请登录后继续</Text>
        </div>

        <div className="flex flex-col gap-4">
          <Input
            size="large"
            prefix={<UserOutlined />}
            placeholder="用户名"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            onKeyDown={handleKeyDown}
            autoFocus
            data-testid="login-username"
          />
          <Input.Password
            size="large"
            prefix={<LockOutlined />}
            placeholder="密码"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            onKeyDown={handleKeyDown}
            data-testid="login-password"
          />
          <Button
            type="primary"
            size="large"
            block
            loading={loading}
            onClick={handleLogin}
            data-testid="login-submit"
          >
            {loading ? '登录中...' : '登 录'}
          </Button>

          {allowRegister && (
            <div className="text-center">
              <Text type="secondary" className="text-xs">还没有账号？</Text>
              <Button
                type="link"
                size="small"
                onClick={() => navigate('/register')}
                data-testid="login-register-link"
              >
                注册新账号
              </Button>
            </div>
          )}
        </div>
      </Card>
    </div>
  );
};

export default Login;