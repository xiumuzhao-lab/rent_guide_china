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

# Bucket Policy: 公开读取（HTTPS 强制由 CDN 层负责，不在 OSS 层限制，避免 CDN 回源 HTTP 被 403）
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
    }
  ]
}
POLICY
sed -i '' "s|REPLACE_RESOURCE|acs:oss:*:*:$OSS_BUCKET|g" "$POLICY_FILE"
ossutil api put-bucket-policy --bucket "$OSS_BUCKET" --body "file://$POLICY_FILE" 2>/dev/null
rm -f "$POLICY_FILE"
echo "  ✓ Bucket Policy 已应用（公开读取）"

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

  # SEO 预渲染
  echo "  预渲染 SEO 页面..."
  node ../scripts/prerender.js

  # 生成 sitemap
  node ../scripts/generate-sitemap.js

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

# 上传 index.html (不缓存)
echo "  上传 index.html (no-cache)..."
ossutil cp "$DIST_DIR/index.html" "${OSS_PATH}index.html" -f \
  --meta-header "Cache-Control: no-cache"

# 上传 hashed 静态资源 (长缓存)
echo "  上传静态资源 (长缓存 365 天)..."
ossutil cp "$DIST_DIR/assets/" "${OSS_PATH}assets/" -r -f \
  --update \
  -j 5 \
  --parallel 5 \
  --meta-header "Cache-Control: public, max-age=31536000, immutable"

# 上传其他根目录文件 (长缓存)
for f in favicon.svg robots.txt; do
  if [ -f "$DIST_DIR/$f" ]; then
    ossutil cp "$DIST_DIR/$f" "${OSS_PATH}$f" -f \
      --meta-header "Cache-Control: public, max-age=604800"
  fi
done

# 上传 sitemap.xml
if [ -f "$DIST_DIR/sitemap.xml" ]; then
  echo "  上传 sitemap.xml..."
  ossutil cp "$DIST_DIR/sitemap.xml" "${OSS_PATH}sitemap.xml" -f \
    --meta-header "Cache-Control: public, max-age=86400"
fi

# 上传预渲染页面: dist/{city}/{workplace}/index.html -> OSS
for city_dir in "$DIST_DIR"/*/; do
  city_name=$(basename "$city_dir")
  # 跳过非城市目录
  if [[ ! "$city_name" =~ ^(shanghai|beijing|hangzhou|shenzhen)$ ]]; then
    continue
  fi
  for wp_dir in "$city_dir"*/; do
    wp_name=$(basename "$wp_dir")
    if [ -f "$wp_dir/index.html" ]; then
      ossutil cp "$wp_dir/index.html" "${OSS_PATH}${city_name}/${wp_name}/index.html" -f \
        --meta-header "Cache-Control: no-cache" 2>/dev/null
    fi
  done
  echo "  上传预渲染页面 ${city_name}/ 完成"
done

# 上传数据文件: versions.json 不缓存，带 hash 的数据文件长缓存
for city_dir in "$DIST_DIR"/data/*/; do
  city_name=$(basename "$city_dir")
  echo "  上传 data/$city_name/ ..."

  # versions.json: 短缓存
  if [ -f "$city_dir/versions.json" ]; then
    ossutil cp "$city_dir/versions.json" "${OSS_PATH}data/$city_name/versions.json" -f \
      --meta-header "Cache-Control: no-cache"
  fi

  # 带 hash 的数据文件: 长缓存
  ossutil cp "$city_dir" "${OSS_PATH}data/$city_name/" -r -f \
    --update \
    --include "listings_*.json" \
    --include "geo_cache_*.json" \
    -j 5 \
    --parallel 5 \
    --meta-header "Cache-Control: public, max-age=31536000, immutable"
done

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

# Step 5: 搜索引擎推送（配置了 token 时自动执行）
if grep -qE '^\s*(BAIDU_PUSH_TOKEN|BING_INDEXNOW_KEY)\s*=\s*\S' "$PROJECT_DIR/.env" 2>/dev/null; then
  echo ""
  node "$PROJECT_DIR/scripts/search-engine-push.js"
fi