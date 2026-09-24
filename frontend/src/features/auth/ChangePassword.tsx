/**
 * ChangePassword.tsx — 修改密码页（多用户账号体系）
 *
 * 功能（方案 §5）：
 * - 校验旧密码（后端 401 bad_old_password）+ 新密码 ≥8 位 + 两次输入一致
 * - 成功后后端 token_version+1（其它设备会话同时失效），当前会话需重新登录
 * - 故成功后清理本地会话并跳转登录页
 */
import React, { useState } from 'react';
import { Input, Button, Typography, message, Card } from 'antd';
import { LockOutlined, SafetyOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useAuth } from './AuthContext';
import { changePassword, parseAuthError } from './api';

const { Title, Text } = Typography;

/** 与后端 password_meets_policy 一致的最小长度 */
const MIN_PASSWORD_LENGTH = 8;

const ChangePassword: React.FC = () => {
  const [oldPassword, setOldPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const { logout } = useAuth();

  const reportError = (err: unknown) => {
    const { code, message: msg } = parseAuthError(err);
    switch (code) {
      case 'bad_old_password':
        message.error('旧密码错误');
        break;
      case 'weak_password':
        message.error(`新密码至少 ${MIN_PASSWORD_LENGTH} 位`);
        break;
      default:
        message.error('修改失败：' + msg);
    }
  };

  const handleSubmit = async () => {
    if (!oldPassword) {
      message.warning('请输入旧密码');
      return;
    }
    if (newPassword.length < MIN_PASSWORD_LENGTH) {
      message.warning(`新密码至少 ${MIN_PASSWORD_LENGTH} 位`);
      return;
    }
    if (newPassword !== confirm) {
      message.warning('两次输入的新密码不一致');
      return;
    }

    setLoading(true);
    try {
      await changePassword(oldPassword, newPassword);
      message.success('密码已修改，请使用新密码重新登录');
      // 改密后 token_version 已变更，当前会话失效 → 清态回登录页
      await logout();
      navigate('/login', { replace: true });
    } catch (err: unknown) {
      reportError(err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="h-full flex items-center justify-center bg-bg-base">
      <Card className="w-96 shadow-lg" styles={{ body: { padding: '32px' } }}>
        <div className="text-center mb-6">
          <SafetyOutlined className="text-3xl text-color-accent mb-3" />
          <Title level={4} className="!mb-1">修改密码</Title>
          <Text type="secondary">修改后其它设备的登录将失效</Text>
        </div>

        <div className="flex flex-col gap-4">
          <Input.Password
            size="large"
            prefix={<LockOutlined />}
            placeholder="旧密码"
            value={oldPassword}
            onChange={(e) => setOldPassword(e.target.value)}
            autoFocus
            data-testid="change-pwd-old"
          />
          <Input.Password
            size="large"
            prefix={<LockOutlined />}
            placeholder={`新密码（至少 ${MIN_PASSWORD_LENGTH} 位）`}
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            data-testid="change-pwd-new"
          />
          <Input.Password
            size="large"
            prefix={<LockOutlined />}
            placeholder="确认新密码"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleSubmit();
            }}
            data-testid="change-pwd-confirm"
          />
          <Button
            type="primary"
            size="large"
            block
            loading={loading}
            onClick={handleSubmit}
            data-testid="change-pwd-submit"
          >
            {loading ? '提交中...' : '确认修改'}
          </Button>
          <div className="text-center">
            <Button type="link" size="small" onClick={() => navigate(-1)} data-testid="change-pwd-cancel">
              返回
            </Button>
          </div>
        </div>
      </Card>
    </div>
  );
};

export default ChangePassword;