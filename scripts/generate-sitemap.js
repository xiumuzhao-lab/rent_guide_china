#!/usr/bin/env node

/**
 * 生成 sitemap.xml: 首页 + 所有预渲染页面.
 *
 * 扫描 dist/ 下的城市/工作地目录结构, 生成标准 sitemap.xml.
 *
 * 用法: node scripts/generate-sitemap.js
 * 前置: 需要先执行 prerender.js
 */

const fs = require('fs');
const path = require('path');

const DIST_DIR = path.join(__dirname, '..', 'frontend', 'dist');
const SITE_ORIGIN = 'https://www.scoreless.top';

const CITIES = ['shanghai', 'beijing', 'hangzhou', 'shenzhen'];

function main() {
  const urls = [];

  // 首页
  urls.push({
    loc: `${SITE_ORIGIN}/`,
    changefreq: 'daily',
    priority: '1.0',
  });

  // 各城市×工作地页面
  for (const city of CITIES) {
    const cityDir = path.join(DIST_DIR, city);
    if (!fs.existsSync(cityDir)) continue;

    const workplaces = fs.readdirSync(cityDir).filter((name) => {
      return fs.existsSync(path.join(cityDir, name, 'index.html'));
    });

    for (const wp of workplaces) {
      urls.push({
        loc: `${SITE_ORIGIN}/${city}/${wp}/`,
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
    <changefreq>${u.changefreq}</changefreq>
    <priority>${u.priority}</priority>
  </url>`).join('\n')}
</urlset>
`;

  const outPath = path.join(DIST_DIR, 'sitemap.xml');
  fs.writeFileSync(outPath, xml);
  console.log(`sitemap.xml 生成完成: ${urls.length} 个 URL`);
  console.log(`  输出: ${path.relative(process.cwd(), outPath)}`);
}

function escapeXml(str) {
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&apos;');
}

main();
