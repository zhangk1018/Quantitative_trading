#!/usr/bin/env python3
"""一键启动所有服务（后台运行）"""
import subprocess
import time
import os
import socket

def check_port(port):
    """检查端口是否被占用"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(('127.0.0.1', port))
    sock.close()
    return result == 0

def kill_port(port):
    """杀死占用端口的进程"""
    try:
        result = subprocess.run(['lsof', '-ti', f':{port}'], capture_output=True, text=True)
        if result.stdout.strip():
            pids = result.stdout.strip().split('\n')
            for pid in pids:
                if pid:
                    subprocess.run(['kill', '-9', pid], capture_output=True)
            time.sleep(1)
    except:
        pass

# 清理所有端口
for port in [8000, 5173, 9000]:
    if check_port(port):
        print(f"清理端口 {port}...")
        kill_port(port)

print("=" * 50)
print("🚀 启动量化交易系统服务")
print("=" * 50)

# 启动后端
print("\n[1/3] 启动后端服务...")
os.chdir('/Users/zhangk/workspace/Quantitative_trading/backend')
env = os.environ.copy()
env['PYTHONPATH'] = '/Users/zhangk/workspace/Quantitative_trading'

backend_proc = subprocess.Popen(
    ['/Users/zhangk/workspace/Quantitative_trading/venv/bin/python', '-m', 'uvicorn', 
     'core.api.main:app', '--host', '0.0.0.0', '--port', '8000'],
    env=env,
    stdout=open('/tmp/quant_backend.log', 'w'),
    stderr=subprocess.STDOUT
)

# 等待后端启动
time.sleep(5)
if check_port(8000):
    print("✅ 后端服务启动成功！端口: 8000")
else:
    print("❌ 后端服务启动失败")
    with open('/tmp/quant_backend.log', 'r') as f:
        print(f.read())
    exit(1)

# 保存后端PID
with open('/tmp/quant_backend.pid', 'w') as f:
    f.write(str(backend_proc.pid))

# 启动前端
print("\n[2/3] 启动前端服务...")
os.chdir('/Users/zhangk/workspace/Quantitative_trading/frontend')
frontend_proc = subprocess.Popen(
    ['npm', 'run', 'dev', '--', '--host', '0.0.0.0', '--port', '5173'],
    stdout=open('/tmp/quant_frontend.log', 'w'),
    stderr=subprocess.STDOUT
)

time.sleep(6)
frontend_port = 5173
if check_port(5173):
    print("✅ 前端服务启动成功！端口: 5173")
else:
    # 检查是否启动在其他端口
    print("⚠️  检查前端是否启动在其他端口...")
    frontend_port = None

# 保存前端PID
with open('/tmp/quant_frontend.pid', 'w') as f:
    f.write(str(frontend_proc.pid))

# 完成
print("\n[3/3] 管理员监控看板已就绪")

print("\n" + "=" * 50)
print("🎉 所有服务已启动！")
print("=" * 50)
print("访问地址:")
print("  - 前端页面: http://localhost:5173")
print("  - 后端API:  http://localhost:8000/api")
print("  - API文档:  http://localhost:8000/docs")
print("  - 管理监控: http://localhost:8000/admin")
print("\n日志文件:")
print("  - 后端日志: /tmp/quant_backend.log")
print("  - 前端日志: /tmp/quant_frontend.log")
print("\n停止服务: 运行 ./start_service.sh stop")
print("=" * 50)
