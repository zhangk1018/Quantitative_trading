/**
 * UsersAdmin.tsx — 管理员页（用户管理）
 *
 * 功能（方案 §5）：
 * - 用户列表：用户名 / 显示名称 / 角色 / 状态 / 创建时间 / 最近登录
 * - 建号（POST /auth/users）、重置密码、禁用/启用、改角色（PUT /auth/users/{id}）
 * - 每次操作均有确认弹窗与结果反馈（409 重名 / 403 无权限 / 404 不存在 / 503 服务不可用）
 * - 仅 admin 可见（路由侧另有 AdminGuard 兜底）
 */
import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Form,
  Input,
  Modal,
  Popconfirm,
  Radio,
  Select,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd';
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import {
  AuthUserItem,
  createUser,
  fetchUsers,
  parseAuthError,
  updateUser,
} from './api';
import { useAuth } from './AuthContext';

const { Title, Text } = Typography;

/** 与后端 password_meets_policy 一致的最小长度 */
const MIN_PASSWORD_LENGTH = 8;

const roleLabel = (role: string) => (role === 'admin' ? '管理员' : '普通用户');

const UsersAdmin: React.FC = () => {
  const { user: currentUser } = useAuth();
  const [users, setUsers] = useState<AuthUserItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const [createOpen, setCreateOpen] = useState(false);
  const [createForm] = Form.useForm();

  const [resetTarget, setResetTarget] = useState<AuthUserItem | null>(null);
  const [resetForm] = Form.useForm();

  const [roleTarget, setRoleTarget] = useState<AuthUserItem | null>(null);
  const [roleValue, setRoleValue] = useState<'admin' | 'user'>('user');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const list = await fetchUsers();
      setUsers(list);
      setError(null);
    } catch (e) {
      const info = parseAuthError(e);
      setError(info.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const reportError = (e: unknown) => {
    const { code, message: msg } = parseAuthError(e);
    switch (code) {
      case 'username_exists':
        message.error('用户名已存在，请更换');
        break;
      case 'weak_password':
        message.error(`密码至少 ${MIN_PASSWORD_LENGTH} 位`);
        break;
      case 'forbidden':
        message.error('无管理员权限');
        break;
      case 'not_found':
        message.error('用户不存在，请刷新列表');
        break;
      default:
        message.error('操作失败：' + msg);
    }
  };

  // ── 建号 ──
  const handleCreate = async () => {
    try {
      const values = await createForm.validateFields();
      setSubmitting(true);
      await createUser({
        username: values.username.trim(),
        password: values.password,
        display_name: values.display_name?.trim() || undefined,
        role: values.role,
      });
      message.success(`账号 ${values.username.trim()} 创建成功`);
      setCreateOpen(false);
      createForm.resetFields();
      await load();
    } catch (e) {
      if (e && typeof e === 'object' && 'errorFields' in e) return; // 表单校验失败
      reportError(e);
    } finally {
      setSubmitting(false);
    }
  };

  // ── 重置密码 ──
  const handleResetPassword = async () => {
    if (!resetTarget) return;
    try {
      const values = await resetForm.validateFields();
      setSubmitting(true);
      await updateUser(resetTarget.id, { password: values.password });
      message.success(`已重置 ${resetTarget.username} 的密码（该账号其它登录已失效）`);
      setResetTarget(null);
      resetForm.resetFields();
      await load();
    } catch (e) {
      if (e && typeof e === 'object' && 'errorFields' in e) return;
      reportError(e);
    } finally {
      setSubmitting(false);
    }
  };

  // ── 禁用 / 启用 ──
  const handleToggleActive = async (record: AuthUserItem) => {
    try {
      await updateUser(record.id, { is_active: !record.is_active });
      message.success(
        record.is_active
          ? `已禁用 ${record.username}，其登录会话已失效`
          : `已启用 ${record.username}`,
      );
      await load();
    } catch (e) {
      reportError(e);
    }
  };

  // ── 改角色 ──
  const handleChangeRole = async () => {
    if (!roleTarget) return;
    try {
      setSubmitting(true);
      await updateUser(roleTarget.id, { role: roleValue });
      message.success(`已将 ${roleTarget.username} 的角色改为${roleLabel(roleValue)}`);
      setRoleTarget(null);
      await load();
    } catch (e) {
      reportError(e);
    } finally {
      setSubmitting(false);
    }
  };

  const columns: ColumnsType<AuthUserItem> = [
    { title: 'ID', dataIndex: 'id', width: 70 },
    {
      title: '用户名',
      dataIndex: 'username',
      render: (value: string) => (
        <span className="text-text-primary">
          {value}
          {value === currentUser?.username && (
            <Text type="secondary" className="ml-2 text-xs">（当前登录）</Text>
          )}
        </span>
      ),
    },
    { title: '显示名称', dataIndex: 'display_name', render: (v: string | null) => v || '-' },
    {
      title: '角色',
      dataIndex: 'role',
      width: 110,
      render: (role: string) => (
        <Tag color={role === 'admin' ? 'blue' : 'default'}>{roleLabel(role)}</Tag>
      ),
    },
    {
      title: '状态',
      dataIndex: 'is_active',
      width: 100,
      render: (active: boolean) => (
        <Tag color={active ? 'green' : 'red'}>{active ? '启用' : '已禁用'}</Tag>
      ),
    },
    {
      title: '最近登录',
      dataIndex: 'last_login_at',
      width: 190,
      render: (v: string | null) => v || '从未登录',
    },
    {
      title: '操作',
      key: 'action',
      width: 260,
      render: (_: unknown, record: AuthUserItem) => {
        // 防自锁：不允许对自己的账号禁用/改角色（否则会立刻失去管理员权限）
        const isSelf = record.username === currentUser?.username;
        return (
          <Space size="small">
            <Button
              size="small"
              onClick={() => {
                setResetTarget(record);
                resetForm.resetFields();
              }}
              data-testid={`user-reset-${record.id}`}
            >
              重置密码
            </Button>
            <Tooltip title={isSelf ? '不能修改自己的角色（防自锁）' : ''}>
              <Button
                size="small"
                disabled={isSelf}
                onClick={() => {
                  setRoleTarget(record);
                  setRoleValue(record.role === 'admin' ? 'admin' : 'user');
                }}
                data-testid={`user-role-${record.id}`}
              >
                改角色
              </Button>
            </Tooltip>
            <Tooltip title={isSelf ? '不能禁用当前登录账号（防自锁）' : ''}>
              <Popconfirm
                title={record.is_active ? '禁用该账号？' : '启用该账号？'}
                description={
                  record.is_active
                    ? '禁用后该账号所有登录会话立即失效，需重新登录（禁用状态无法登录）。'
                    : '启用后该账号可正常登录。'
                }
                okText="确认"
                cancelText="取消"
                onConfirm={() => handleToggleActive(record)}
              >
                <Button
                  size="small"
                  danger={record.is_active}
                  disabled={isSelf}
                  data-testid={`user-toggle-${record.id}`}
                >
                  {record.is_active ? '禁用' : '启用'}
                </Button>
              </Popconfirm>
            </Tooltip>
          </Space>
        );
      },
    },
  ];

  return (
    <div className="h-full overflow-auto p-6 bg-bg-base">
      <Card className="bg-bg-panel border-border-color" styles={{ body: { padding: '20px 24px' } }}>
        <div className="flex items-center justify-between mb-4">
          <div>
            <Title level={4} className="!mb-1">用户管理</Title>
            <Text type="secondary">建号 / 重置密码 / 禁用启用 / 调整角色</Text>
          </div>
          <Space>
            <Button icon={<ReloadOutlined />} onClick={() => void load()} data-testid="users-refresh">
              刷新
            </Button>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => {
                setCreateOpen(true);
                createForm.resetFields();
              }}
              data-testid="users-create"
            >
              新建用户
            </Button>
          </Space>
        </div>

        {error && (
          <Alert
            type="error"
            showIcon
            className="mb-4"
            message={error}
            action={<Button size="small" onClick={() => void load()}>重试</Button>}
          />
        )}

        <Table<AuthUserItem>
          rowKey="id"
          size="small"
          loading={loading}
          columns={columns}
          dataSource={users}
          pagination={false}
          data-testid="users-table"
        />
      </Card>

      {/* 建号 */}
      <Modal
        title="新建用户"
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onOk={handleCreate}
        confirmLoading={submitting}
        okText="创建"
        cancelText="取消"
        destroyOnClose
      >
        <Form form={createForm} layout="vertical" initialValues={{ role: 'user' }}>
          <Form.Item
            name="username"
            label="用户名"
            rules={[{ required: true, message: '请输入用户名' }]}
          >
            <Input placeholder="登录名" data-testid="create-username" />
          </Form.Item>
          <Form.Item name="display_name" label="显示名称">
            <Input placeholder="可选，默认同用户名" data-testid="create-display-name" />
          </Form.Item>
          <Form.Item
            name="password"
            label="初始密码"
            rules={[
              { required: true, message: '请输入初始密码' },
              { min: MIN_PASSWORD_LENGTH, message: `密码至少 ${MIN_PASSWORD_LENGTH} 位` },
            ]}
          >
            <Input.Password placeholder={`至少 ${MIN_PASSWORD_LENGTH} 位`} data-testid="create-password" />
          </Form.Item>
          <Form.Item name="role" label="角色">
            <Select
              options={[
                { value: 'user', label: '普通用户' },
                { value: 'admin', label: '管理员' },
              ]}
              data-testid="create-role"
            />
          </Form.Item>
        </Form>
      </Modal>

      {/* 重置密码 */}
      <Modal
        title={resetTarget ? `重置密码：${resetTarget.username}` : '重置密码'}
        open={!!resetTarget}
        onCancel={() => setResetTarget(null)}
        onOk={handleResetPassword}
        confirmLoading={submitting}
        okText="确认重置"
        cancelText="取消"
        destroyOnClose
      >
        <Text type="secondary">重置后该账号的所有登录会话立即失效，需用新密码重新登录。</Text>
        <Form form={resetForm} layout="vertical" className="mt-4">
          <Form.Item
            name="password"
            label="新密码"
            rules={[
              { required: true, message: '请输入新密码' },
              { min: MIN_PASSWORD_LENGTH, message: `密码至少 ${MIN_PASSWORD_LENGTH} 位` },
            ]}
          >
            <Input.Password placeholder={`至少 ${MIN_PASSWORD_LENGTH} 位`} data-testid="reset-password" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 改角色 */}
      <Modal
        title={roleTarget ? `修改角色：${roleTarget.username}` : '修改角色'}
        open={!!roleTarget}
        onCancel={() => setRoleTarget(null)}
        onOk={handleChangeRole}
        confirmLoading={submitting}
        okText="确认"
        cancelText="取消"
        destroyOnClose
      >
        <Radio.Group
          value={roleValue}
          onChange={(e) => setRoleValue(e.target.value)}
          data-testid="role-radio"
        >
          <Radio.Button value="user">普通用户</Radio.Button>
          <Radio.Button value="admin">管理员</Radio.Button>
        </Radio.Group>
      </Modal>
    </div>
  );
};

export default UsersAdmin;