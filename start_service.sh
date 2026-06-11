#!/bin/bash
# ============================================
# 量化系统服务启停脚本
# 支持：start / stop / restart / status / install / check 命令
# ============================================

# 配置参数
PROJECT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
BACKEND_DIR="$PROJECT_DIR/backend"
FRONTEND_DIR="$PROJECT_DIR/frontend"

# PID 文件路径
BACKEND_PID_FILE="/tmp/quant_backend.pid"
FRONTEND_PID_FILE="/tmp/quant_frontend.pid"
MONITOR_PID_FILE="/tmp/quant_monitor.pid"

# 端口配置
BACKEND_PORT=8000
FRONTEND_PORT=5173
MONITOR_PORT=9000

# 日志文件路径
BACKEND_LOG="/tmp/quant_backend.log"
FRONTEND_LOG="/tmp/quant_frontend.log"
MONITOR_LOG="/tmp/quant_monitor.log"

# 虚拟环境路径
VENV_DIR="$PROJECT_DIR/venv"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# ============================================
# 函数定义
# ============================================

# 通过端口查找进程PID（比PID文件更可靠）
find_pid_by_port() {
    local port=$1
    lsof -t -i :"$port" -sTCP:LISTEN 2>/dev/null | head -1
}

# 检查端口是否被占用
is_port_in_use() {
    local port=$1
    lsof -i :"$port" -sTCP:LISTEN >/dev/null 2>&1
}

# 检查进程是否存活（兼容PID文件和端口两种方式）
check_pid() {
    local pid_file=$1
    local port=$2  # 可选：额外检查端口

    # 方式1：通过PID文件检查
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if kill -0 "$pid" 2>/dev/null; then
            echo "$pid"
            return 0
        fi
        # PID文件存在但进程已死，清理
        rm -f "$pid_file"
    fi

    # 方式2：通过端口检查（兜底）
    if [ -n "$port" ]; then
        local pid=$(find_pid_by_port "$port")
        if [ -n "$pid" ]; then
            echo "$pid"
            return 0
        fi
    fi

    return 1
}

install_backend() {
    echo -e "${YELLOW}🔄 安装后端依赖...${NC}"
    
    # 检查是否已安装虚拟环境
    if [ -d "$VENV_DIR" ]; then
        echo -e "${YELLOW}⚠️ 虚拟环境已存在，跳过创建${NC}"
    else
        echo -e "${YELLOW}📦 创建虚拟环境...${NC}"
        python3 -m venv "$VENV_DIR"
        if [ $? -ne 0 ]; then
            echo -e "${RED}❌ 创建虚拟环境失败${NC}"
            return 1
        fi
    fi
    
    # 激活虚拟环境并安装依赖
    source "$VENV_DIR/bin/activate"
    
    # 检查 requirements.txt
    if [ ! -f "$BACKEND_DIR/requirements.txt" ]; then
        echo -e "${RED}❌ 未找到 requirements.txt: $BACKEND_DIR/requirements.txt${NC}"
        return 1
    fi
    
    echo -e "${YELLOW}📦 安装 Python 依赖...${NC}"
    pip install -r "$BACKEND_DIR/requirements.txt" -q
    if [ $? -ne 0 ]; then
        echo -e "${RED}❌ 依赖安装失败${NC}"
        return 1
    fi
    
    echo -e "${GREEN}✅ 后端依赖安装成功${NC}"
    return 0
}

install_frontend() {
    echo -e "${YELLOW}🔄 安装前端依赖...${NC}"
    
    # 检查 npm 是否安装
    if ! command -v npm &> /dev/null; then
        echo -e "${RED}❌ npm 未安装，请先安装 Node.js${NC}"
        return 1
    fi
    
    # 检查前端目录
    if [ ! -d "$FRONTEND_DIR" ]; then
        echo -e "${RED}❌ 前端目录不存在: $FRONTEND_DIR${NC}"
        return 1
    fi
    
    # 检查是否已安装依赖
    if [ -d "$FRONTEND_DIR/node_modules" ]; then
        echo -e "${YELLOW}⚠️ 前端依赖已安装，跳过${NC}"
        return 0
    fi
    
    echo -e "${YELLOW}📦 安装 npm 依赖...${NC}"
    cd "$FRONTEND_DIR" || exit 1
    npm install -q
    if [ $? -ne 0 ]; then
        echo -e "${RED}❌ 前端依赖安装失败${NC}"
        return 1
    fi
    
    echo -e "${GREEN}✅ 前端依赖安装成功${NC}"
    return 0
}

check_env() {
    echo -e "${YELLOW}🔍 检查运行环境...${NC}"
    echo ""
    
    # 检查 Python
    if command -v python3 &> /dev/null; then
        echo -e "${GREEN}✅ Python3: $(python3 --version | cut -d' ' -f2)${NC}"
    else
        echo -e "${RED}❌ Python3 未安装${NC}"
    fi
    
    # 检查 Node.js
    if command -v node &> /dev/null; then
        echo -e "${GREEN}✅ Node.js: $(node --version)${NC}"
    else
        echo -e "${RED}❌ Node.js 未安装${NC}"
    fi
    
    # 检查虚拟环境
    if [ -d "$VENV_DIR" ]; then
        echo -e "${GREEN}✅ 虚拟环境: 已创建${NC}"
    else
        echo -e "${YELLOW}⚠️ 虚拟环境: 未创建${NC}"
    fi
    
    # 检查后端目录
    if [ -d "$BACKEND_DIR" ]; then
        echo -e "${GREEN}✅ 后端目录: 存在${NC}"
    else
        echo -e "${RED}❌ 后端目录: 不存在${NC}"
    fi
    
    # 检查前端目录
    if [ -d "$FRONTEND_DIR" ]; then
        echo -e "${GREEN}✅ 前端目录: 存在${NC}"
    else
        echo -e "${RED}❌ 前端目录: 不存在${NC}"
    fi
    
    # 检查后端入口文件
    if [ -f "$BACKEND_DIR/core/api/main.py" ]; then
        echo -e "${GREEN}✅ 后端入口: core/api/main.py${NC}"
    else
        echo -e "${RED}❌ 后端入口: 不存在${NC}"
    fi
    
    # 检查端口占用
    echo ""
    echo -e "${YELLOW}📡 端口检查:${NC}"
    if lsof -i :"$BACKEND_PORT" &> /dev/null; then
        echo -e "${RED}❌ 端口 $BACKEND_PORT 已被占用${NC}"
    else
        echo -e "${GREEN}✅ 端口 $BACKEND_PORT: 可用${NC}"
    fi
    
    if lsof -i :"$FRONTEND_PORT" &> /dev/null; then
        echo -e "${RED}❌ 端口 $FRONTEND_PORT 已被占用${NC}"
    else
        echo -e "${GREEN}✅ 端口 $FRONTEND_PORT: 可用${NC}"
    fi
    
    echo ""
}

start_backend() {
    echo -e "${YELLOW}🔄 启动后端服务...${NC}"

    # 检查是否已运行（通过PID文件 + 端口双重检查）
    if check_pid "$BACKEND_PID_FILE" "$BACKEND_PORT"; then
        echo -e "${GREEN}✅ 后端服务已在运行 (端口: $BACKEND_PORT)${NC}"
        return 0
    fi

    # 端口被占用但PID不匹配（僵尸进程或手动启动的）
    if is_port_in_use "$BACKEND_PORT"; then
        local old_pid=$(find_pid_by_port "$BACKEND_PORT")
        echo -e "${YELLOW}⚠️ 端口 $BACKEND_PORT 被占用 (PID: ${old_pid:-unknown})，正在清理...${NC}"
        if [ -n "$old_pid" ]; then
            kill "$old_pid" 2>/dev/null
            sleep 2
            kill -9 "$old_pid" 2>/dev/null
        fi
        rm -f "$BACKEND_PID_FILE"
        # 再次确认端口释放
        if is_port_in_use "$BACKEND_PORT"; then
            echo -e "${RED}❌ 端口 $BACKEND_PORT 仍被占用，无法启动${NC}"
            return 1
        fi
    fi

    # 检查虚拟环境
    if [ ! -d "$VENV_DIR" ]; then
        echo -e "${RED}❌ 虚拟环境不存在，请先执行: $0 install${NC}"
        return 1
    fi

    # 检查后端入口
    if [ ! -f "$BACKEND_DIR/core/api/main.py" ]; then
        echo -e "${RED}❌ 后端入口文件不存在: core/api/main.py${NC}"
        return 1
    fi

    # 启动后端服务（使用venv中的python）
    cd "$BACKEND_DIR" || exit 1
    export PYTHONPATH="$PROJECT_DIR"
    nohup "$VENV_DIR/bin/python" -m uvicorn core.api.main:app --host 0.0.0.0 --port "$BACKEND_PORT" > "$BACKEND_LOG" 2>&1 &
    local new_pid=$!
    echo "$new_pid" > "$BACKEND_PID_FILE"

    # 等待启动并验证
    for i in $(seq 1 10); do
        sleep 1
        if is_port_in_use "$BACKEND_PORT"; then
            echo -e "${GREEN}✅ 后端服务启动成功 (PID: $new_pid, 端口: $BACKEND_PORT)${NC}"
            return 0
        fi
    done

    # 超时未启动
    echo -e "${RED}❌ 后端服务启动失败（10秒超时），查看日志: $BACKEND_LOG${NC}"
    rm -f "$BACKEND_PID_FILE"
    return 1
}

stop_backend() {
    echo -e "${YELLOW}🔄 停止后端服务...${NC}"

    local stopped=0

    # 方式1：通过PID文件停止
    if [ -f "$BACKEND_PID_FILE" ]; then
        local pid=$(cat "$BACKEND_PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null
            sleep 2
            if kill -0 "$pid" 2>/dev/null; then
                kill -9 "$pid" 2>/dev/null
            fi
            stopped=1
        fi
        rm -f "$BACKEND_PID_FILE"
    fi

    # 方式2：通过端口清理残留进程
    if is_port_in_use "$BACKEND_PORT"; then
        local port_pid=$(find_pid_by_port "$BACKEND_PORT")
        if [ -n "$port_pid" ]; then
            echo -e "${YELLOW}⚠️ 发现端口 $BACKEND_PORT 残留进程 (PID: $port_pid)，正在终止...${NC}"
            kill "$port_pid" 2>/dev/null
            sleep 2
            kill -9 "$port_pid" 2>/dev/null
            stopped=1
        fi
    fi

    if [ $stopped -eq 1 ]; then
        echo -e "${GREEN}✅ 后端服务已停止${NC}"
    else
        echo -e "${YELLOW}⏸ 后端服务未运行${NC}"
    fi
}

start_frontend() {
    echo -e "${YELLOW}🔄 启动前端服务...${NC}"

    # 检查是否已运行（PID文件 + 端口）
    if check_pid "$FRONTEND_PID_FILE" "$FRONTEND_PORT"; then
        echo -e "${GREEN}✅ 前端服务已在运行 (端口: $FRONTEND_PORT)${NC}"
        return 0
    fi

    # 端口被占用，清理
    if is_port_in_use "$FRONTEND_PORT"; then
        local old_pid=$(find_pid_by_port "$FRONTEND_PORT")
        echo -e "${YELLOW}⚠️ 端口 $FRONTEND_PORT 被占用 (PID: ${old_pid:-unknown})，正在清理...${NC}"
        if [ -n "$old_pid" ]; then
            kill "$old_pid" 2>/dev/null; sleep 2; kill -9 "$old_pid" 2>/dev/null
        fi
        rm -f "$FRONTEND_PID_FILE"
        if is_port_in_use "$FRONTEND_PORT"; then
            echo -e "${RED}❌ 端口 $FRONTEND_PORT 仍被占用${NC}"
            return 1
        fi
    fi

    # 检查 npm
    if ! command -v npm &> /dev/null; then
        echo -e "${RED}❌ npm 未安装，请先安装 Node.js${NC}"
        return 1
    fi

    # 检查前端目录
    if [ ! -d "$FRONTEND_DIR" ]; then
        echo -e "${RED}❌ 前端目录不存在: $FRONTEND_DIR${NC}"
        return 1
    fi

    # 安装依赖（如需要）
    if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
        echo -e "${YELLOW}📦 安装前端依赖...${NC}"
        cd "$FRONTEND_DIR" && npm install -q
        if [ $? -ne 0 ]; then
            echo -e "${RED}❌ 前端依赖安装失败${NC}"
            return 1
        fi
    fi

    # 启动前端
    cd "$FRONTEND_DIR" || exit 1
    nohup npm run dev -- --host 0.0.0.0 --port "$FRONTEND_PORT" > "$FRONTEND_LOG" 2>&1 &
    local new_pid=$!
    echo "$new_pid" > "$FRONTEND_PID_FILE"

    # 等待启动并验证
    for i in $(seq 1 8); do
        sleep 1
        if is_port_in_use "$FRONTEND_PORT"; then
            echo -e "${GREEN}✅ 前端服务启动成功 (PID: $new_pid, 端口: $FRONTEND_PORT)${NC}"
            return 0
        fi
    done

    echo -e "${RED}❌ 前端服务启动失败（8秒超时），查看日志: $FRONTEND_LOG${NC}"
    rm -f "$FRONTEND_PID_FILE"
    return 1
}

stop_frontend() {
    echo -e "${YELLOW}🔄 停止前端服务...${NC}"

    local stopped=0
    if [ -f "$FRONTEND_PID_FILE" ]; then
        local pid=$(cat "$FRONTEND_PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null; sleep 2; kill -9 "$pid" 2>/dev/null
            stopped=1
        fi
        rm -f "$FRONTEND_PID_FILE"
    fi

    if is_port_in_use "$FRONTEND_PORT"; then
        local port_pid=$(find_pid_by_port "$FRONTEND_PORT")
        if [ -n "$port_pid" ]; then
            echo -e "${YELLOW}⚠️ 发现端口 $FRONTEND_PORT 残留进程 (PID: $port_pid)，正在终止...${NC}"
            kill "$port_pid" 2>/dev/null; sleep 2; kill -9 "$port_pid" 2>/dev/null
            stopped=1
        fi
    fi

    if [ $stopped -eq 1 ]; then
        echo -e "${GREEN}✅ 前端服务已停止${NC}"
    else
        echo -e "${YELLOW}⏸ 前端服务未运行${NC}"
    fi
}

start_monitor() {
    echo -e "${YELLOW}🔄 启动管理员数据监控看板...${NC}"
    
    # 检查是否已运行
    if check_pid "$MONITOR_PID_FILE"; then
        echo -e "${YELLOW}⚠️ 管理员数据监控看板已在运行 (PID: $(cat $MONITOR_PID_FILE))${NC}"
        return 0
    fi
    
    # 检查后端是否运行 - 监控看板依赖后端 API
    if ! check_pid "$BACKEND_PID_FILE"; then
        echo -e "${YELLOW}⚠️ 后端服务未运行，请先启动后端服务${NC}"
        return 1
    fi
    
    # 启动监控看板 - 使用内置的静态文件服务
    cd "$BACKEND_DIR" || exit 1
    nohup python3 -m http.server "$MONITOR_PORT" --directory static > "$MONITOR_LOG" 2>&1 &
    echo $! > "$MONITOR_PID_FILE"
    
    # 等待启动
    sleep 2
    
    # 检查是否启动成功
    if check_pid "$MONITOR_PID_FILE"; then
        echo -e "${GREEN}✅ 管理员数据监控看板启动成功 (PID: $(cat $MONITOR_PID_FILE), 端口: $MONITOR_PORT)${NC}"
        echo -e "${GREEN}📊 访问地址: http://localhost:$BACKEND_PORT/admin 或 http://localhost:$MONITOR_PORT/monitor.html${NC}"
        return 0
    else
        echo -e "${RED}❌ 管理员数据监控看板启动失败，查看日志: $MONITOR_LOG${NC}"
        return 1
    fi
}

stop_monitor() {
    echo -e "${YELLOW}🔄 停止管理员数据监控看板...${NC}"
    
    if ! check_pid "$MONITOR_PID_FILE"; then
        echo -e "${YELLOW}⚠️ 管理员数据监控看板未运行${NC}"
        return 0
    fi
    
    local pid=$(cat "$MONITOR_PID_FILE")
    kill "$pid" 2>/dev/null
    
    # 等待进程退出
    sleep 2
    
    if kill -0 "$pid" 2>/dev/null; then
        echo -e "${YELLOW}⚠️ 强制终止管理员数据监控看板...${NC}"
        kill -9 "$pid" 2>/dev/null
    fi
    
    rm -f "$MONITOR_PID_FILE"
    echo -e "${GREEN}✅ 管理员数据监控看板已停止${NC}"
}

show_status() {
    echo "============================================"
    echo -e "${YELLOW}量化系统服务状态${NC}"
    echo "============================================"

    echo -n "后端服务: "
    if check_pid "$BACKEND_PID_FILE" "$BACKEND_PORT"; then
        local bp=$(check_pid "$BACKEND_PID_FILE" "$BACKEND_PORT")
        echo -e "${GREEN}✅ 运行中 (PID: $bp, 端口: $BACKEND_PORT)${NC}"
    else
        echo -e "${RED}❌ 未运行${NC}"
    fi

    echo -n "前端服务: "
    if check_pid "$FRONTEND_PID_FILE" "$FRONTEND_PORT"; then
        local fp=$(check_pid "$FRONTEND_PID_FILE" "$FRONTEND_PORT")
        echo -e "${GREEN}✅ 运行中 (PID: $fp, 端口: $FRONTEND_PORT)${NC}"
    else
        echo -e "${RED}❌ 未运行${NC}"
    fi

    echo -n "管理员数据监控看板: "
    if check_pid "$MONITOR_PID_FILE" "$MONITOR_PORT"; then
        local mp=$(check_pid "$MONITOR_PID_FILE" "$MONITOR_PORT")
        echo -e "${GREEN}✅ 运行中 (PID: $mp, 端口: $MONITOR_PORT)${NC}"
    else
        echo -e "${YELLOW}⏸ 未运行${NC}"
    fi

    echo ""
    echo "访问地址:"
    echo "  - 前端页面: http://localhost:$FRONTEND_PORT"
    echo "  - 后端API:  http://localhost:$BACKEND_PORT/api"
    echo "  - API文档:  http://localhost:$BACKEND_PORT/docs"
    echo "  - 管理监控: http://localhost:$BACKEND_PORT/admin"
    echo "============================================"
}

# ============================================
# 主逻辑
# ============================================

case "$1" in
    start)
        echo "============================================"
        echo -e "${YELLOW}启动量化系统服务${NC}"
        echo "============================================"
        start_backend
        if [ $? -eq 0 ]; then
            start_frontend
        fi
        echo ""
        show_status
        ;;
    
    stop)
        echo "============================================"
        echo -e "${YELLOW}停止量化系统服务${NC}"
        echo "============================================"
        stop_backend
        stop_frontend
        stop_monitor
        ;;
    
    restart)
        echo "============================================"
        echo -e "${YELLOW}重启量化系统服务${NC}"
        echo "============================================"
        stop_backend
        stop_frontend
        stop_monitor
        sleep 1
        start_backend
        if [ $? -eq 0 ]; then
            start_frontend
        fi
        echo ""
        show_status
        ;;
    
    status)
        show_status
        ;;
    
    install)
        echo "============================================"
        echo -e "${YELLOW}安装系统依赖${NC}"
        echo "============================================"
        install_backend
        if [ $? -eq 0 ]; then
            install_frontend
        fi
        ;;
    
    check)
        check_env
        ;;
    
    admin-start)
        echo "============================================"
        echo -e "${YELLOW}启动管理员数据监控看板${NC}"
        echo "============================================"
        start_monitor
        echo ""
        show_status
        ;;
    
    admin-stop)
        echo "============================================"
        echo -e "${YELLOW}停止管理员数据监控看板${NC}"
        echo "============================================"
        stop_monitor
        echo ""
        show_status
        ;;
    
    admin-restart)
        echo "============================================"
        echo -e "${YELLOW}重启管理员数据监控看板${NC}"
        echo "============================================"
        stop_monitor
        sleep 1
        start_monitor
        echo ""
        show_status
        ;;
    
    all)
        echo "============================================"
        echo -e "${YELLOW}启动所有服务（包含管理员监控）${NC}"
        echo "============================================"
        start_backend
        if [ $? -eq 0 ]; then
            start_frontend
            start_monitor
        fi
        echo ""
        show_status
        ;;
    
    *)
        echo "用法: $0 {start|stop|restart|status|install|check|admin-start|admin-stop|admin-restart|all}"
        echo ""
        echo "命令说明:"
        echo "  start             - 启动后端和前端服务"
        echo "  stop              - 停止所有服务"
        echo "  restart           - 重启所有服务"
        echo "  status            - 查看服务状态"
        echo "  install           - 安装后端和前端依赖"
        echo "  check             - 检查运行环境"
        echo "  admin-start       - 启动管理员数据监控看板"
        echo "  admin-stop        - 停止管理员数据监控看板"
        echo "  admin-restart     - 重启管理员数据监控看板"
        echo "  all               - 启动所有服务（后端、前端、管理监控）"
        exit 1
        ;;
esac
