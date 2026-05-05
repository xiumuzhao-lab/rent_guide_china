#!/usr/bin/env node

/**
 * 生成 sitemap.xml: 首页 + 所有预渲染页面.
 *
 * 扫描 dist/ 下的城市/工作地目录结构, 生成标准 sitemap.xml.
 * 包含 lastmod 时间戳和 URL 编码.
 *
 * 用法: node scripts/generate-sitemap.js
 * 前置: 需要先执行 prerender.js
 */

const fs = require('fs');
const path = require('path');

const DIST_DIR = path.join(__dirname, '..', 'frontend', 'dist');
const DATA_DIR = path.join(__dirname, '..', 'frontend', 'public', 'data');
const SITE_ORIGIN = 'https://www.scoreless.top';

const CITIES = ['shanghai', 'beijing', 'hangzhou', 'shenzhen'];

/** 对 URL 中的非 ASCII 字符进行 percent-encoding (保留 / 和结构字符). */
function encodeUrl(url) {
  try {
    const u = new URL(url);
    // 仅编码 pathname 部分, 保留查询参数
    const segments = u.pathname.split('/');
    const encoded = segments.map((s) => encodeURIComponent(decodeURIComponent(s))).join('/');
    return `${u.origin}${encoded}${u.search}`;
  } catch {
    return url;
  }
}

/** 读取城市数据的最后更新时间. */
function getLastmod(cityKey) {
  const verPath = path.join(DATA_DIR, cityKey, 'versions.json');
  if (fs.existsSync(verPath)) {
    try {
      const ver = JSON.parse(fs.readFileSync(verPath, 'utf-8'));
      if (ver.listings) {
        // 从文件名提取日期: listings_20260505_100441.json → 2026-05-05
        const m = ver.listings.match(/(\d{4})(\d{2})(\d{2})/);
        if (m) return `${m[1]}-${m[2]}-${m[3]}`;
      }
    } catch { /* fallback */ }
  }
  // 回退: 读取 listings.json 的修改时间
  const listingsPath = path.join(DATA_DIR, cityKey, 'listings.json');
  if (fs.existsSync(listingsPath)) {
    const stat = fs.statSync(listingsPath);
    return stat.mtime.toISOString().split('T')[0];
  }
  return new Date().toISOString().split('T')[0];
}

function main() {
  const urls = [];

  // 首页
  urls.push({
    loc: `${SITE_ORIGIN}/`,
    lastmod: new Date().toISOString().split('T')[0],
    changefreq: 'daily',
    priority: '1.0',
  });

  // 各城市×工作地页面
  const lastmodCache = {};
  for (const city of CITIES) {
    lastmodCache[city] = getLastmod(city);
  }

  for (const city of CITIES) {
    const cityDir = path.join(DIST_DIR, city);
    if (!fs.existsSync(cityDir)) continue;

    const workplaces = fs.readdirSync(cityDir).filter((name) => {
      return fs.existsSync(path.join(cityDir, name, 'index.html'));
    });

    for (const wp of workplaces) {
      const rawLoc = `${SITE_ORIGIN}/${city}/${wp}/`;
      urls.push({
        loc: encodeUrl(rawLoc),
        lastmod: lastmodCache[city],
        changefreq: 'daily',
        priority: '0.8',
      });
    }
  }

  // 生成 XML
  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${urls.map((u) => `  <url>
    <loc>${escapeXml(u.loc)}</loc>
    <lastmod>${u.lastmod}</lastmod>
    <changefreq>${u.changefreq}</changefreq>
    <priority>${u.priority}</priority>
  </url>`).join('\n')}
</urlset>
`;

  const outPath = path.join(DIST_DIR, 'sitemap.xml');
  fs.writeFileSync(outPath, xml);
  console.log(`sitemap.xml 生成完成: ${urls.length} 个 URL`);
  console.log(`  输出: ${path.relative(process.cwd(), outPath)}`);
  console.log(`  URL 已进行 percent-encoding`);
  console.log(`  包含 lastmod 时间戳`);
}

function escapeXml(str) {
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&apos;');
}

main();
