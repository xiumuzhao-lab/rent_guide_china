#!/usr/bin/env node

/**
 * SEO 预渲染脚本: 为每个城市×工作地生成独立 HTML 文件.
 *
 * 读取 dist/index.html 作为模板, 替换 meta 标签后输出到
 * dist/{city}/{workplaceName}/index.html, 供搜索引擎直接抓取.
 *
 * 用户访问时, 内嵌 JS 检测 path URL 并重定向到查询参数形式.
 *
 * 用法: node scripts/prerender.js
 * 前置: 需要先执行 vite build 生成 dist/index.html
 */

const fs = require('fs');
const path = require('path');

const DIST_DIR = path.join(__dirname, '..', 'frontend', 'dist');
const SITE_ORIGIN = 'https://www.scoreless.top';

// 内联城市配置 (避免 ESM/CJS 兼容问题)
const PAGES = [
  {
    city: 'shanghai', cityName: '上海',
    workplaces: [
      { name: '上海中心大厦', address: '浦东新区陆家嘴' },
      { name: '上海环球金融中心', address: '浦东新区陆家嘴' },
      { name: '上海国金中心', address: '浦东新区陆家嘴' },
      { name: '上海恒隆广场', address: '静安区南京西路' },
      { name: '上海会德丰国际广场', address: '静安区南京西路' },
      { name: '上海BFC外滩金融中心', address: '黄浦区外滩' },
      { name: '上海陆家嘴世纪金融广场', address: '浦东新区陆家嘴' },
      { name: '上海张江科学之门', address: '浦东新区张江' },
      { name: '上海创智天地', address: '杨浦区五角场' },
      { name: '上海漕河泾科技绿洲', address: '闵行区漕河泾' },
    ],
  },
  {
    city: 'beijing', cityName: '北京',
    workplaces: [
      { name: '北京中信大厦', address: '朝阳区CBD' },
      { name: '北京国贸三期', address: '朝阳区国贸' },
      { name: '北京中国尊', address: '朝阳区CBD' },
      { name: '北京银泰中心', address: '朝阳区国贸' },
      { name: '北京华贸中心', address: '朝阳区华贸' },
      { name: '北京环球金融中心', address: '朝阳区CBD' },
      { name: '北京财富中心', address: '朝阳区CBD' },
      { name: '北京嘉里中心', address: '朝阳区国贸' },
      { name: '北京金融街英蓝国际金融中心', address: '西城区金融街' },
      { name: '北京融科资讯中心', address: '海淀区中关村' },
    ],
  },
  {
    city: 'hangzhou', cityName: '杭州',
    workplaces: [
      { name: '杭州来福士中心', address: '上城区钱江新城' },
      { name: '杭州平安金融中心', address: '上城区钱江新城' },
      { name: '杭州华润大厦', address: '上城区钱江新城' },
      { name: '杭州钱江新城核心区', address: '上城区钱江新城' },
      { name: '杭州EFC欧美金融城', address: '余杭区未来科技城' },
      { name: '杭州阿里西溪园区', address: '余杭区西溪' },
      { name: '杭州网易杭州园区', address: '滨江区网商路' },
      { name: '杭州海康威视总部', address: '滨江区阡陌路' },
      { name: '杭州滨江物联网小镇', address: '滨江区物联网街' },
      { name: '杭州云栖小镇', address: '西湖区云栖小镇' },
    ],
  },
  {
    city: 'shenzhen', cityName: '深圳',
    workplaces: [
      { name: '深圳平安金融中心', address: '福田区福田CBD' },
      { name: '深圳腾讯滨海大厦', address: '南山区科技园' },
      { name: '深圳华润春笋', address: '南山区后海' },
      { name: '深圳科兴科学园', address: '南山区科技园' },
      { name: '深圳深圳湾科技生态园', address: '南山区科技园' },
      { name: '深圳腾讯大厦', address: '南山区科技园' },
      { name: '深圳百度国际大厦', address: '南山区科技园' },
      { name: '深圳大疆天空之城', address: '南山区留仙洞' },
      { name: '深圳创维半导体设计大厦', address: '南山区科技园' },
      { name: '深圳中粮科技园', address: '宝安区中粮科技创新园' },
    ],
  },
];

/**
 * 为单个页面生成 SEO 内容.
 *
 * @param {string} cityName 城市中文名
 * @param {string} wpName 工作地名称
 * @param {string} wpAddress 工作地地址
 * @param {string} cityKey 城市英文 key
 * @returns {{title:string, description:string, keywords:string, canonical:string,
 *   ogTitle:string, ogDescription:string, ogUrl:string,
 *   jsonLd:object, noscript:string}} SEO 字段
 */
function buildSEO(cityName, wpName, wpAddress, cityKey) {
  const urlPath = `/${cityKey}/${wpName}/`;
  const canonical = `${SITE_ORIGIN}${urlPath}`;
  const queryUrl = `${SITE_ORIGIN}/?city=${cityKey}&wp=${encodeURIComponent(wpName)}&dist=5`;

  const title = `租房雷达 — ${cityName}${wpName}周边5公里租房数据 | 单价地图·性价比排行`;
  const description = `${cityName}${wpName}周边5公里租房数据分析：小区单价热力图、距离环性价比排行、户型统计、面积与价格分析。覆盖${wpAddress}等区域的租房价格，帮您找到性价比最高的租房选择。`;
  const keywords = `${cityName}租房,${wpName}租房,${cityName}租房价格,${cityName}租房地图,${wpName}周边租房,租房单价,性价比租房,${cityName}${wpAddress}租房`;

  const jsonLd = {
    '@context': 'https://schema.org',
    '@type': 'WebPage',
    name: title,
    description: description,
    url: canonical,
    breadcrumb: {
      '@type': 'BreadcrumbList',
      itemListElement: [
        { '@type': 'ListItem', position: 1, name: '首页', item: SITE_ORIGIN },
        { '@type': 'ListItem', position: 2, name: cityName, item: `${SITE_ORIGIN}/?city=${cityKey}` },
        { '@type': 'ListItem', position: 3, name: wpName, item: canonical },
      ],
    },
    mainEntity: {
      '@type': 'RealEstateListing',
      name: `${cityName}${wpName}周边租房`,
      description: description,
      address: {
        '@type': 'PostalAddress',
        addressLocality: cityName,
        streetAddress: wpAddress,
      },
    },
  };

  const noscript = [
    `<h1>租房雷达 — ${cityName}${wpName}周边5公里租房数据分析</h1>`,
    `<p>${cityName}${wpName}周边5公里租房数据分析平台，提供小区单价热力图、距离环性价比排行、户型统计。</p>`,
    `<h2>覆盖区域</h2>`,
    `<p>${cityName}${wpAddress}周边5公里范围内的租房小区。</p>`,
    `<h2>主要功能</h2>`,
    `<ul>`,
    `<li>租房价格热力地图 — 可视化展示各小区单价分布</li>`,
    `<li>距离环排行 — 按通勤距离筛选性价比最高的租房小区</li>`,
    `<li>交互式地图 — 支持自定义工作地点，实时计算通勤距离</li>`,
    `<li>数据分析报告 — 租金分布、户型统计、面积与价格关系分析</li>`,
    `</ul>`,
  ].join('\n      ');

  return { title, description, keywords, canonical, ogTitle: title, ogDescription: description, ogUrl: canonical, jsonLd, noscript, queryUrl };
}

/**
 * 替换模板 HTML 中的 SEO 占位内容.
 *
 * @param {string} template 模板 HTML 字符串
 * @param {object} seo buildSEO 返回的 SEO 字段
 * @returns {string} 替换后的 HTML
 */
function renderPage(template, seo) {
  let html = template;

  // 重定向脚本: 在所有其他脚本之前插入, 检测 path URL 并跳转到查询参数形式
  const redirectScript = `<script>
  // SEO path URL -> query params redirect (executed before SPA)
  (function() {
    var m = location.pathname.match(/^\\/(shanghai|beijing|hangzhou|shenzhen)\\/([^/]+)\\/?$/);
    if (m) location.replace('/?city=' + m[1] + '&wp=' + encodeURIComponent(decodeURIComponent(m[2])) + '&dist=5');
  })();
  </script>`;

  // 在 HTTP->HTTPS 脚本之后插入重定向
  html = html.replace(
    /(<script>\s*\n\s*if \(location\.protocol)/,
    `${redirectScript}\n    $1`,
  );

  // 替换 title
  html = html.replace(
    /<title>[^<]*<\/title>/,
    `<title>${seo.title}</title>`,
  );

  // 替换 meta description
  html = html.replace(
    /<meta\s+name="description"\s+content="[^"]*"\s*\/?>/,
    `<meta name="description" content="${seo.description}" />`,
  );

  // 替换 meta keywords
  html = html.replace(
    /<meta\s+name="keywords"\s+content="[^"]*"\s*\/?>/,
    `<meta name="keywords" content="${seo.keywords}" />`,
  );

  // 替换 canonical
  html = html.replace(
    /<link\s+rel="canonical"\s+href="[^"]*"\s*\/?>/,
    `<link rel="canonical" href="${seo.canonical}" />`,
  );

  // 替换 OG tags
  html = html.replace(
    /<meta\s+property="og:title"\s+content="[^"]*"\s*\/?>/,
    `<meta property="og:title" content="${seo.ogTitle}" />`,
  );
  html = html.replace(
    /<meta\s+property="og:description"\s+content="[^"]*"\s*\/?>/,
    `<meta property="og:description" content="${seo.ogDescription}" />`,
  );
  html = html.replace(
    /<meta\s+property="og:url"\s+content="[^"]*"\s*\/?>/,
    `<meta property="og:url" content="${seo.ogUrl}" />`,
  );

  // 替换 JSON-LD
  html = html.replace(
    /<script\s+type="application\/ld\+json">[\s\S]*?<\/script>/,
    `<script type="application/ld+json">\n    ${JSON.stringify(seo.jsonLd, null, 2).split('\n').join('\n    ')}\n    </script>`,
  );

  // 替换 noscript
  html = html.replace(
    /<noscript>[\s\S]*?<\/noscript>/,
    `<noscript>\n      ${seo.noscript}\n    </noscript>`,
  );

  return html;
}

function main() {
  const templatePath = path.join(DIST_DIR, 'index.html');
  if (!fs.existsSync(templatePath)) {
    console.error('错误: dist/index.html 不存在, 请先执行 vite build');
    process.exit(1);
  }

  const template = fs.readFileSync(templatePath, 'utf-8');
  let count = 0;

  for (const { city, cityName, workplaces } of PAGES) {
    for (const wp of workplaces) {
      const seo = buildSEO(cityName, wp.name, wp.address, city);
      const html = renderPage(template, seo);

      const outDir = path.join(DIST_DIR, city, wp.name);
      fs.mkdirSync(outDir, { recursive: true });
      fs.writeFileSync(path.join(outDir, 'index.html'), html);
      count++;
    }
  }

  console.log(`预渲染完成: ${count} 个页面`);
  console.log(`  输出目录: ${path.relative(process.cwd(), DIST_DIR)}/`);
}

main();
