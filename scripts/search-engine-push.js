#!/usr/bin/env node

/**
 * 多搜索引擎推送: Baidu API + Bing IndexNow.
 *
 * 从 .env 读取 token, 推送 sitemap.xml 中的所有 URL.
 *
 * 用法: node scripts/search-engine-push.js
 * 前置: 需要先执行 generate-sitemap.js
 *
 * 环境变量:
 *   BAIDU_PUSH_TOKEN    — 百度搜索资源平台 API 推送 token
 *   BING_INDEXNOW_KEY   — Bing IndexNow 密钥 (可选, 配置后启用 Bing 推送)
 */

const fs = require('fs');
const path = require('path');

const PROJECT_DIR = path.join(__dirname, '..');
const SITE_ORIGIN = 'https://www.scoreless.top';
const SITEMAP_PATH = path.join(PROJECT_DIR, 'frontend', 'dist', 'sitemap.xml');
const ENV_FILE = path.join(PROJECT_DIR, '.env');

/**
 * 从 .env 加载环境变量.
 *
 * @param {string} envPath .env 文件路径
 * @returns {object} 解析出的键值对
 */
function loadEnv(envPath) {
  const env = {};
  if (!fs.existsSync(envPath)) return env;
  const content = fs.readFileSync(envPath, 'utf-8');
  for (const line of content.split('\n')) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const eqIdx = trimmed.indexOf('=');
    if (eqIdx < 0) continue;
    const key = trimmed.slice(0, eqIdx).trim();
    const val = trimmed.slice(eqIdx + 1).trim();
    env[key] = val;
  }
  return env;
}

/**
 * 从 sitemap.xml 中提取所有 URL.
 *
 * @param {string} sitemapPath sitemap.xml 文件路径
 * @returns {string[]} URL 列表
 */
function parseSitemap(sitemapPath) {
  if (!fs.existsSync(sitemapPath)) {
    console.error('错误: sitemap.xml 不存在, 请先执行 generate-sitemap.js');
    process.exit(1);
  }
  const xml = fs.readFileSync(sitemapPath, 'utf-8');
  const urls = [];
  const re = /<loc>([^<]+)<\/loc>/g;
  let match;
  while ((match = re.exec(xml)) !== null) {
    urls.push(match[1]);
  }
  return urls;
}

/**
 * 推送 URL 到百度搜索资源平台.
 *
 * @param {string[]} urls URL 列表
 * @param {string} token 百度推送 token
 */
async function pushBaidu(urls, token) {
  if (!token) {
    console.log('[百度] 跳过: 未配置 BAIDU_PUSH_TOKEN');
    return;
  }

  console.log(`[百度] 推送 ${urls.length} 个 URL...`);

  const body = urls.join('\n');
  const res = await fetch(
    `http://data.zz.baidu.com/urls?site=${SITE_ORIGIN}&token=${token}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'text/plain' },
      body,
    },
  );

  const data = await res.json();
  if (data.error) {
    console.log(`[百度] 推送失败: ${data.message || data.error}`);
  } else {
    console.log(`[百度] 成功: ${data.success || 0} 条, 剩余额度: ${data.remain || '?'}`);
  }
}

/**
 * 通过 IndexNow 协议推送 URL 到 Bing (及所有 IndexNow 参与引擎).
 *
 * @param {string[]} urls URL 列表
 * @param {string} key IndexNow 密钥
 */
async function pushBing(urls, key) {
  if (!key) {
    console.log('[Bing] 跳过: 未配置 BING_INDEXNOW_KEY');
    return;
  }

  console.log(`[Bing] IndexNow 推送 ${urls.length} 个 URL...`);

  const payload = {
    host: new URL(SITE_ORIGIN).host,
    key,
    keyLocation: `${SITE_ORIGIN}/${key}.txt`,
    urlList: urls,
  };

  const res = await fetch('https://api.indexnow.org/indexnow', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (res.ok) {
    console.log(`[Bing] 推送成功 (HTTP ${res.status})`);
  } else {
    const text = await res.text();
    console.log(`[Bing] 推送失败 (HTTP ${res.status}): ${text.slice(0, 200)}`);
  }
}

async function main() {
  const env = loadEnv(ENV_FILE);
  const urls = parseSitemap(SITEMAP_PATH);

  console.log(`=== 搜索引擎推送 ===`);
  console.log(`  URL 数量: ${urls.length}`);
  console.log('');

  await Promise.all([
    pushBaidu(urls, env.BAIDU_PUSH_TOKEN),
    pushBing(urls, env.BING_INDEXNOW_KEY),
  ]);

  console.log('');
  console.log('推送完成');
}

main().catch((err) => {
  console.error('推送失败:', err.message);
  process.exit(1);
});
