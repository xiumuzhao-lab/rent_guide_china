#!/bin/bash
#
# 百度搜索资源平台 - 主动推送 URL
# 每次部署后调用，加快百度收录速度
#
# 用法: bash scripts/baidu-push.sh
#
# 环境变量（在 .env 中配置）:
#   BAIDU_PUSH_TOKEN  — 百度搜索资源平台 API 推送 token
#   SITE_URL          — 站点 URL（默认 https://www.scoreless.top）
#
# 获取 token:
#   百度搜索资源平台 → 普通收录 → API提交 → 查看接口调用地址中的 token 参数

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$PROJECT_DIR/.env"

# 从 .env 加载变量
if [ -f "$ENV_FILE" ]; then
  while IFS='=' read -r key val; do
    key=$(echo "$key" | xargs)
    val=$(echo "$val" | xargs)
    if [[ "$key" =~ ^(BAIDU_|SITE_) ]] && [[ ! "$key" =~ ^# ]]; then
      export "$key=$val"
    fi
  done < <(grep -E '^\s*(BAIDU_|SITE_)[A-Z_]+\s*=' "$ENV_FILE" 2>/dev/null || true)
fi

SITE_URL="${SITE_URL:-https://www.scoreless.top}"
TOKEN="${BAIDU_PUSH_TOKEN:-}"

if [ -z "$TOKEN" ]; then
  echo "错误: 未配置 BAIDU_PUSH_TOKEN"
  echo ""
  echo "请在 .env 中添加:"
  echo "  BAIDU_PUSH_TOKEN=你的token"
  echo ""
  echo "获取方式: 百度搜索资源平台 → 普通收录 → API提交 → 接口地址中的 token 参数"
  exit 1
fi

# 收集要推送的 URL
URLS=()

# 1. 首页
URLS+=("$SITE_URL/")

# 2. 从 sitemap.xml 提取 URL
SITEMAP="$PROJECT_DIR/frontend/public/sitemap.xml"
if [ -f "$SITEMAP" ]; then
  while IFS= read -r loc; do
    URLS+=("$loc")
  done < <(grep -oP '(?<=<loc>)[^<]+' "$SITEMAP" 2>/dev/null | sort -u)
fi

# 3. 带常用查询参数的页面（帮百度发现核心页面）
COMMUNITIES="张江金桥唐镇川沙惠南周浦康桥三林北蔡曹路高行花木陆家嘴世博洋泾"
for c in $COMMUNITIES; do
  URLS+=("$SITE_URL/?wp=${c}")
done

# 去重
UNIQUE_URLS=($(echo "${URLS[@]}" | tr ' ' '\n' | sort -u))

echo "=== 百度主动推送 ==="
echo "  站点: $SITE_URL"
echo "  URL 数量: ${#UNIQUE_URLS[@]}"
echo ""

# 推送到百度
RESPONSE=$(curl -s -H "Content-Type:text/plain" \
  --data-urlencode "list=${UNIQUE_URLS[*]}" \
  "http://data.zz.baidu.com/urls?site=$SITE_URL&token=$TOKEN")

echo "  百度返回: $RESPONSE"

# 解析结果
SUCCESS=$(echo "$RESPONSE" | grep -o '"success":[0-9]*' | grep -o '[0-9]*' || echo "0")
REMAIN=$(echo "$RESPONSE" | grep -o '"remain":[0-9]*' | grep -o '[0-9]*' || echo "?")

if [ "$SUCCESS" = "0" ] && echo "$RESPONSE" | grep -q '"error"'; then
  ERROR_MSG=$(echo "$RESPONSE" | grep -oP '(?<="message":")[^"]*' || echo "未知错误")
  echo ""
  echo "  推送失败: $ERROR_MSG"
  exit 1
fi

echo ""
echo "  成功推送: ${SUCCESS} 条"
echo "  今日剩余额度: ${REMAIN} 条"
