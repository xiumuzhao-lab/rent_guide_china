#!/bin/bash
#
# 一键部署 frontend/ 到阿里云 OSS
#
# 用法: bash scripts/deploy-oss.sh [--skip-build]
#
# 参数:
#   --skip-build  跳过构建步骤，直接上传已有的 dist 目录
#
# 环境变量（在 .env 中配置）:
#   OSS_BUCKET    — OSS Bucket 名称（默认 rent-radar-static）
#   OSS_REGION    — OSS 区域（默认 cn-shanghai）
#   OSS_ENDPOINT  — OSS Endpoint（默认 oss-cn-shanghai.aliyuncs.com）
#
# 注意: OSS 认证信息需要在 ~/.ossutilconfig 中配置
#   ossutil config
#   输入 AccessKeyID 和 AccessKeySecret

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
FRONTEND_DIR="$PROJECT_DIR/frontend"
DIST_DIR="$FRONTEND_DIR/dist"

# 从 .env 加载变量
ENV_FILE="$PROJECT_DIR/.env"
if [ -f "$ENV_FILE" ]; then
  while IFS='=' read -r key val; do
    key=$(echo "$key" | xargs)
    val=$(echo "$val" | xargs)
    if [[ "$key" =~ ^OSS_ ]] && [[ ! "$key" =~ ^# ]]; then
      export "$key=$val"
    fi
  done < <(grep -E '^\s*OSS_[A-Z_]+\s*=' "$ENV_FILE" 2>/dev/null || true)
fi

# 默认配置
OSS_BUCKET="${OSS_BUCKET:-rent-radar-static}"
OSS_REGION="${OSS_REGION:-cn-shanghai}"
OSS_ENDPOINT="${OSS_ENDPOINT:-oss-cn-shanghai.aliyuncs.com}"
OSS_PATH="oss://$OSS_BUCKET/"

# 检查 ossutil
if ! command -v ossutil &>/dev/null; then
  echo "错误: ossutil 未安装"
  echo "  安装方法: https://help.aliyun.com/document_detail/120075.html"
  exit 1
fi

# 检查 ossutil 配置
if [ ! -f ~/.ossutilconfig ]; then
  echo "错误: ~/.ossutilconfig 不存在，请先配置 ossutil"
  echo "  运行: ossutil config"
  echo "  输入 AccessKeyID 和 AccessKeySecret"
  exit 1
fi

echo "=== 部署 RentRadar Frontend 到 OSS ==="
echo "  Bucket: $OSS_BUCKET"
echo "  Region: $OSS_REGION"
echo ""

# Step 0: 应用安全策略
echo "[0/4] 应用安全策略..."

# Bucket Policy: 允许 HTTPS 公开读取，允许 HTTP 访问 index.html（用于重定向），拒绝 HTTP 访问其他资源
POLICY_FILE=$(mktemp)
cat > "$POLICY_FILE" << 'POLICY'
{
  "Version": "1",
  "Statement": [
    {
      "Sid": "AllowPublicRead",
      "Effect": "Allow",
      "Action": ["oss:GetObject"],
      "Principal": ["*"],
      "Resource": ["REPLACE_RESOURCE/*"]
    },
    {
      "Sid": "DenyHTTPNonHtml",
      "Effect": "Deny",
      "Action": ["oss:GetObject"],
      "Principal": ["*"],
      "Resource": [
        "REPLACE_RESOURCE/assets/*",
        "REPLACE_RESOURCE/data/*",
        "REPLACE_RESOURCE/favicon.svg",
        "REPLACE_RESOURCE/robots.txt",
        "REPLACE_RESOURCE/sitemap.xml",
        "REPLACE_RESOURCE/CNAME"
      ],
      "Condition": {
        "Bool": {
          "acs:SecureTransport": ["false"]
        }
      }
    }
  ]
}
POLICY
sed -i '' "s|REPLACE_RESOURCE|acs:oss:*:*:$OSS_BUCKET|g" "$POLICY_FILE"
ossutil api put-bucket-policy --bucket "$OSS_BUCKET" --body "file://$POLICY_FILE" 2>/dev/null
rm -f "$POLICY_FILE"
echo "  ✓ Bucket Policy 已应用（HTTP 仅允许 index.html）"

echo ""

# Step 1: 构建（可选）
SKIP_BUILD=false
if [[ "${1:-}" == "--skip-build" ]]; then
  SKIP_BUILD=true
fi

if [ "$SKIP_BUILD" = false ]; then
  echo "[1/4] 构建前端..."
  cd "$FRONTEND_DIR"

  # 先运行数据准备脚本
  node ../scripts/prepare_data.js

  # 构建
  npm run build

  echo "  构建完成"
  echo ""
else
  echo "[1/4] 跳过构建 (--skip-build)"
  if [ ! -d "$DIST_DIR" ]; then
    echo "错误: dist 目录不存在，请先构建或去掉 --skip-build 参数"
    exit 1
  fi
  echo ""
fi

# Step 2: 上传到 OSS
echo "[2/4] 上传到 OSS..."

# 清理旧文件（保留 data 目录，因为数据文件可能很大）
echo "  清理旧文件..."
ossutil rm "$OSS_PATH" -r -f --exclude "data/*" 2>/dev/null || true

# 上传新文件
echo "  上传新文件..."
ossutil cp "$DIST_DIR/" "$OSS_PATH" -r -f \
  --update \
  -j 5 \
  --parallel 5

echo "  上传完成"
echo ""

# Step 3: 验证上传
echo "[3/4] 验证上传..."
sleep 1

# 检查关键文件
CHECK_FILES=("index.html" "favicon.svg" "robots.txt")
ALL_OK=true
for file in "${CHECK_FILES[@]}"; do
  count=$(ossutil ls "$OSS_PATH$file" 2>/dev/null | grep -c "Object Number is: 1" || true)
  if [ "$count" -ge 1 ]; then
    echo "  ✓ $file"
  else
    echo "  ✗ $file (缺失)"
    ALL_OK=false
  fi
done

if [ "$ALL_OK" = true ]; then
  echo "  ✓ 所有关键文件已上传"
else
  echo "  ✗ 有文件缺失，请检查"
fi
echo ""

# Step 4: 安全验证
echo "[4/4] 安全验证..."

echo "  检查 HTTPS 访问..."
HTTPS_STATUS=$(curl -sI "https://www.scoreless.top/index.html" 2>/dev/null | head -1 | awk '{print $2}')
if [ "$HTTPS_STATUS" = "200" ]; then
  echo "  ✓ HTTPS 访问正常"
else
  echo "  ✗ HTTPS 访问异常 (状态码: $HTTPS_STATUS)"
fi

echo "  检查 HTTP 重定向..."
HTTP_REDIRECT=$(curl -s -o /dev/null -w "%{http_code} %{redirect_url}" "http://www.scoreless.top/" 2>/dev/null)
if echo "$HTTP_REDIRECT" | grep -q "200\|30"; then
  echo "  ✓ HTTP 访问 index.html 正常（JS 重定向到 HTTPS）"
else
  echo "  ~ HTTP 返回: $HTTP_REDIRECT"
fi

echo ""
echo "=== 部署完成 ==="

# Step 5: 百度主动推送（配置了 token 时自动执行）
if grep -qE '^\s*BAIDU_PUSH_TOKEN\s*=\s*\S' "$PROJECT_DIR/.env" 2>/dev/null; then
  echo ""
  bash "$PROJECT_DIR/scripts/baidu-push.sh"
fi