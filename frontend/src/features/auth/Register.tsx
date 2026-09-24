/**
 * Register.tsx — 自助注册页（多用户账号体系）
 *
 * 功能（方案 §5）：
 * - 仅当 `GET /api/auth/config` 的 auth_allow_register=true 时开放；开关关闭时展示提示并引导回登录
 * - 用户名（保留名 default 不可用）/ 显示名称（可选）/ 密码（≥8 位，两次一致）
 * - 按响应 code 提示：username_exists（409）/ weak_password、bad_format（400）/
 *   register_closed（403）/ rate_limited（429）
 */
import React, { useState } from 'react';
import { Input, Button, Typography, message, Card } from 'antd';
import { UserOutlined, LockOutlined, IdcardOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useAuth } from './AuthContext';
import { parseAuthError, register } from './api';

const { Title, Text } = Typography;

/** 与后端 password_meets_policy 一致的最小长度 */
const MIN_PASSWORD_LENGTH = 8;
/** 后端保留用户名（老自选股归属标记，禁止注册占用） */
const RESERVED_USERNAME = 'default';

const Register: React.FC = () => {
  const [username, setUsername] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const { allowRegister } = useAuth();

  const reportError = (err: unknown) => {
    const { code, message: msg } = parseAuthError(err);
    switch (code) {
      case 'username_exists':
        message.error('用户名已存在，请更换');
        break;
      case 'weak_password':
        message.error(`密码至少 ${MIN_PASSWORD_LENGTH} 位`);
        break;
      case 'bad_format':
        message.error(msg || '用户名格式不合法');
        break;
      case 'register_closed':
        message.error('未开放自助注册，请联系管理员');
        break;
      case 'rate_limited':
        message.error('注册过于频繁，请稍后再试');
        break;
      default:
        message.error('注册失败：' + msg);
    }
  };

  const handleRegister = async () => {
    if (!username.trim()) {
      message.warning('请输入用户名');
      return;
    }
    if (username.trim() === RESERVED_USERNAME) {
      message.warning(`用户名 ${RESERVED_USERNAME} 为保留名，不可使用`);
      return;
    }
    if (password.length < MIN_PASSWORD_LENGTH) {
      message.warning(`密码至少 ${MIN_PASSWORD_LENGTH} 位`);
      return;
    }
    if (password !== confirm) {
      message.warning('两次输入的密码不一致');
      return;
    }

    setLoading(true);
    try {
      await register(username.trim(), password, displayName.trim());
      message.success('注册成功，请登录');
      navigate('/login', { replace: true });
    } catch (err: unknown) {
      reportError(err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="h-screen w-screen flex items-center justify-center bg-bg-base">
      <Card className="w-96 shadow-lg" styles={{ body: { padding: '40px 32px' } }}>
        <div className="text-center mb-8">
          <IdcardOutlined className="text-4xl text-color-accent mb-4" />
          <Title level={3} className="!mb-1">注册账号</Title>
          <Text type="secondary">创建后可访问本系统</Text>
        </div>

        {!allowRegister ? (
          <div className="flex flex-col gap-4">
            <Text type="secondary">当前未开放自助注册，请联系管理员创建账号。</Text>
            <Button type="primary" size="large" block onClick={() => navigate('/login')} data-testid="register-back-login">
              返回登录
            </Button>
          </div>
        ) : (
          <div className="flex flex-col gap-4">
            <Input
              size="large"
              prefix={<UserOutlined />}
              placeholder="用户名"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoFocus
              data-testid="register-username"
            />
            <Input
              size="large"
              prefix={<IdcardOutlined />}
              placeholder="显示名称（可选）"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              data-testid="register-display-name"
            />
            <Input.Password
              size="large"
              prefix={<LockOutlined />}
              placeholder={`密码（至少 ${MIN_PASSWORD_LENGTH} 位）`}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              data-testid="register-password"
            />
            <Input.Password
              size="large"
              prefix={<LockOutlined />}
              placeholder="确认密码"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleRegister();
              }}
              data-testid="register-confirm"
            />
            <Button
              type="primary"
              size="large"
              block
              loading={loading}
              onClick={handleRegister}
              data-testid="register-submit"
            >
              {loading ? '注册中...' : '注 册'}
            </Button>
            <div className="text-center">
              <Button type="link" size="small" onClick={() => navigate('/login')} data-testid="register-back-login">
                已有账号？返回登录
              </Button>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
};

export default Register;