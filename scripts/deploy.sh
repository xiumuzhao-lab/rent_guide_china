#!/bin/bash
#
# 安全部署脚本 — 在独立临时目录操作 gh-pages，完全不碰工作目录
#
# 用法:
#   bash scripts/deploy.sh
#
# 前提:
#   1. frontend/ 下 npm install 已完成

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BRANCH="gh-pages"

echo "=== 链家租房 — 安全部署到 GitHub Pages ==="
echo ""

# Step 1: 构建前端
echo "[1/3] 构建前端..."
cd "$PROJECT_DIR/frontend"
if [ ! -d node_modules ]; then
  echo "  安装依赖..."
  npm install
fi
npm run build
echo "  构建完成: dist/"
echo ""

# Step 2: 准备数据（如果还没有）
if [ ! -f "$PROJECT_DIR/frontend/public/data/listings.json" ]; then
  echo "[2/3] 准备数据..."
  node "$PROJECT_DIR/scripts/prepare_data.js"
else
  echo "[2/3] 数据已就绪，跳过"
fi
echo ""

# Step 3: 在临时目录克隆 gh-pages 并更新
DEPLOY_DIR="$(mktemp -d)"
echo "[3/3] 部署到 gh-pages 分支（临时目录: ${DEPLOY_DIR}）..."

cd "${DEPLOY_DIR}"

# 克隆 gh-pages 分支（如果不存在则创建空仓库）
if git clone --branch "$BRANCH" --single-branch "$PROJECT_DIR" . 2>/dev/null; then
  echo "  已克隆 gh-pages 分支"
else
  echo "  gh-pages 分支不存在，创建新的孤儿提交"
  git init .
fi

# 清空并复制新内容
rm -rf ./*
cp -r "$PROJECT_DIR/frontend/dist/"* .

# 复制数据文件（确保 dist 中包含数据）
if [ -d "$PROJECT_DIR/frontend/public/data" ]; then
  mkdir -p data
  cp "$PROJECT_DIR/frontend/public/data/"* ./data/ 2>/dev/null || true
fi

# 提交并推送
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
git add -A
if git diff --cached --quiet; then
  echo "  没有变更，跳过部署"
else
  git commit -m "Deploy $TIMESTAMP"

  # 从项目配置获取 remote URL
  REMOTE_URL=$(cd "$PROJECT_DIR" && git remote get-url origin)
  git remote remove origin 2>/dev/null || true
  git remote add origin "$REMOTE_URL"
  git push origin "$BRANCH" --force
  echo "  已推送到 gh-pages"
fi
echo ""

# 清理
echo "清理临时目录..."
cd "$PROJECT_DIR"
rm -rf "${DEPLOY_DIR}"
echo ""

echo "=== 部署完成 ==="
echo "  https://rent.scoreless.top/"
