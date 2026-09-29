#!/bin/bash
# FreeNodeMailer v2.0 - 每日自动运行脚本
# 用法: ./run.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 加载环境变量
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

echo "=== FreeNodeMailer 开始运行 ==="
echo "时间: $(date)"

# 步骤1: 抓取节点
echo ">>> 正在抓取 Clash 节点..."
python scripts/fetch.py

# 步骤2: 发送邮件
echo ">>> 正在发送邮件..."
python scripts/send_email.py

echo "=== 运行完成 ==="
echo "时间: $(date)"
