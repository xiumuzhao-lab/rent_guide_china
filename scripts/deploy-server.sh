#!/bin/bash
#
# 一键部署 server/ 到远程服务器
#
# 用法: bash scripts/deploy-server.sh
#
# 环境变量（在 .env 中配置）:
#   DEPLOY_HOST     — 服务器地址（必填）
#   DEPLOY_USER     — SSH 用户名（必填）
#   DEPLOY_PORT     — SSH 端口（默认 22）
#   DEPLOY_PASSWORD — SSH 密码（与 DEPLOY_KEY 二选一）
#   DEPLOY_KEY      — SSH 私钥路径（与 DEPLOY_PASSWORD 二选一）
#   DEPLOY_PATH     — 远程部署目录（默认 /opt/rent-radar）

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SERVER_DIR="$PROJECT_DIR/server"

# 从 .env 加载变量
ENV_FILE="$PROJECT_DIR/.env"
if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  source <(grep -E '^\s*(DEPLOY_|TENCENT_MAP)' "$ENV_FILE")
  set +a
fi

# 校验必填变量
: "${DEPLOY_HOST:?DEPLOY_HOST 未配置，请在 .env 中设置}"
: "${DEPLOY_USER:?DEPLOY_USER 未配置，请在 .env 中设置}"
DEPLOY_PORT="${DEPLOY_PORT:-22}"
DEPLOY_PATH="${DEPLOY_PATH:-/opt/rent-radar}"
IMAGE_NAME="rent-radar-server"
CONTAINER_NAME="rent-radar-server"

# 构建 SSH 命令
SSH_OPTS="-o StrictHostKeyChecking=no -p $DEPLOY_PORT"
if [ -n "${DEPLOY_KEY:-}" ]; then
  SSH_CMD="ssh $SSH_OPTS -i $DEPLOY_KEY"
  SCP_CMD="scp $SSH_OPTS -i $DEPLOY_KEY"
else
  if ! command -v sshpass &>/dev/null; then
    echo "错误: 使用密码部署需要 sshpass，请安装或改用 DEPLOY_KEY"
    echo "  apt install sshpass  或  brew install sshpass"
    exit 1
  fi
  : "${DEPLOY_PASSWORD:?DEPLOY_PASSWORD 未配置}"
  SSH_CMD="sshpass -e ssh $SSH_OPTS"
  SCP_CMD="sshpass -e scp $SSH_OPTS"
fi
export SSHPASS="${DEPLOY_PASSWORD:-}"

echo "=== 部署 RentRadar Server 到 $DEPLOY_HOST ==="
echo ""

# Step 1: 传输文件
echo "[1/3] 传输文件到 $DEPLOY_USER@$DEPLOY_HOST:$DEPLOY_PATH ..."
$SSH_CMD "$DEPLOY_USER@$DEPLOY_HOST" "mkdir -p $DEPLOY_PATH"
$SCP_CMD -r "$SERVER_DIR/"* "$DEPLOY_USER@$DEPLOY_HOST:$DEPLOY_PATH/"
echo "  文件传输完成"
echo ""

# Step 2: 远程构建镜像并启动
echo "[2/3] 远程构建并启动容器 ..."
$SSH_CMD "$DEPLOY_USER@$DEPLOY_HOST" /bin/bash <<REMOTE_SCRIPT
set -euo pipefail
cd $DEPLOY_PATH

# 停止旧容器
docker rm -f $CONTAINER_NAME 2>/dev/null || true

# 构建新镜像
docker build -t $IMAGE_NAME .

# 启动容器
docker run -d \
  --name $CONTAINER_NAME \
  --restart unless-stopped \
  -p 8900:8900 \
  -e TENCENT_MAP_KEY="$TENCENT_MAP_KEY" \
  -e TENCENT_MAP_SK="$TENCENT_MAP_SK" \
  $IMAGE_NAME

# 清理旧镜像
docker image prune -f --filter "label!=keep" 2>/dev/null || true

echo "容器已启动"
REMOTE_SCRIPT
echo ""

# Step 3: 健康检查
echo "[3/3] 健康检查 ..."
sleep 2
if $SSH_CMD "$DEPLOY_USER@$DEPLOY_HOST" "curl -sf http://localhost:8900/api/tmap?keyword=test >/dev/null"; then
  echo "  服务运行正常"
else
  echo "  警告: 健康检查未通过，请手动确认: docker logs $CONTAINER_NAME"
fi
echo ""

echo "=== 部署完成 ==="
echo "  服务地址: http://$DEPLOY_HOST:8900/api/tmap?keyword=张江"
