#!/bin/bash
# ============================================
# 量化交易系统 - 快速启动脚本
# ============================================

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 获取脚本所在目录
PROJECT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
FRONTEND_DIR="$PROJECT_DIR/quant-trading-frontend"

echo "============================================"
echo -e "${YELLOW}🚀 量化交易系统启动脚本${NC}"
echo "============================================"
echo ""

# 检查前端目录
if [ ! -d "$FRONTEND_DIR" ]; then
    echo -e "${RED}❌ 错误：前端目录不存在${NC}"
    echo "   路径: $FRONTEND_DIR"
    exit 1
fi

# 进入前端目录
cd "$FRONTEND_DIR" || exit 1

# 检查 node_modules
if [ ! -d "node_modules" ]; then
    echo -e "${YELLOW}📦 首次启动，正在安装依赖...${NC}"
    npm install
    if [ $? -ne 0 ]; then
        echo -e "${RED}❌ 依赖安装失败${NC}"
        exit 1
    fi
    echo ""
fi

# 启动前端服务
echo -e "${YELLOW}🌐 启动前端开发服务器...${NC}"
echo -e "${GREEN}✅ 访问地址: http://localhost:3000${NC}"
echo ""
echo -e "${YELLOW}提示: 按 Ctrl+C 停止服务${NC}"
echo "============================================"
echo ""

npm run dev