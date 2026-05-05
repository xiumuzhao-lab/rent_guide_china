#!/usr/bin/env node

/**
 * SEO 预渲染脚本: 为每个城市×工作地生成独立 HTML 文件.
 *
 * 读取 dist/index.html 作为模板, 替换 meta 标签后输出到
 * dist/{city}/{workplaceName}/index.html, 供搜索引擎直接抓取.
 *
 * 用户访问时, SPA 自动识别 path URL 并用 replaceState 转换.
 *
 * 用法: node scripts/prerender.js
 * 前置: 需要先执行 vite build 生成 dist/index.html
 */

const fs = require('fs');
const path = require('path');

const DIST_DIR = path.join(__dirname, '..', 'frontend', 'dist');
const DATA_DIR = path.join(__dirname, '..', 'frontend', 'public', 'data');
const SITE_ORIGIN = 'https://www.scoreless.top';

// 内联城市配置 (避免 ESM/CJS 兼容问题)
const PAGES = [
  {
    city: 'shanghai', cityName: '上海',
    workplaces: [
      { name: '上海中心大厦', lat: 31.2335, lng: 121.5054, address: '浦东新区陆家嘴' },
      { name: '上海环球金融中心', lat: 31.2343, lng: 121.5078, address: '浦东新区陆家嘴' },
      { name: '上海国金中心', lat: 31.2364, lng: 121.5022, address: '浦东新区陆家嘴' },
      { name: '上海恒隆广场', lat: 31.2277, lng: 121.4536, address: '静安区南京西路' },
      { name: '上海会德丰国际广场', lat: 31.2216, lng: 121.4448, address: '静安区南京西路' },
      { name: '上海BFC外滩金融中心', lat: 31.2267, lng: 121.4979, address: '黄浦区外滩' },
      { name: '上海陆家嘴世纪金融广场', lat: 31.2128, lng: 121.5353, address: '浦东新区陆家嘴' },
      { name: '上海张江科学之门', lat: 31.1865, lng: 121.6175, address: '浦东新区张江' },
      { name: '上海创智天地', lat: 31.3060, lng: 121.5123, address: '杨浦区五角场' },
      { name: '上海漕河泾科技绿洲', lat: 31.1661, lng: 121.3904, address: '闵行区漕河泾' },
    ],
  },
  {
    city: 'beijing', cityName: '北京',
    workplaces: [
      { name: '北京中信大厦', lat: 39.9129, lng: 116.4663, address: '朝阳区CBD' },
      { name: '北京国贸三期', lat: 39.9125, lng: 116.4598, address: '朝阳区国贸' },
      { name: '北京中国尊', lat: 39.9129, lng: 116.4663, address: '朝阳区CBD' },
      { name: '北京银泰中心', lat: 39.9074, lng: 116.4593, address: '朝阳区国贸' },
      { name: '北京华贸中心', lat: 39.9092, lng: 116.4808, address: '朝阳区华贸' },
      { name: '北京环球金融中心', lat: 39.9187, lng: 116.4590, address: '朝阳区CBD' },
      { name: '北京财富中心', lat: 39.9161, lng: 116.4601, address: '朝阳区CBD' },
      { name: '北京嘉里中心', lat: 39.9141, lng: 116.4593, address: '朝阳区国贸' },
      { name: '北京金融街英蓝国际金融中心', lat: 39.9206, lng: 116.3579, address: '西城区金融街' },
      { name: '北京融科资讯中心', lat: 39.9835, lng: 116.3261, address: '海淀区中关村' },
    ],
  },
  {
    city: 'hangzhou', cityName: '杭州',
    workplaces: [
      { name: '杭州来福士中心', lat: 30.2487, lng: 120.2131, address: '上城区钱江新城' },
      { name: '杭州平安金融中心', lat: 30.2510, lng: 120.2130, address: '上城区钱江新城' },
      { name: '杭州华润大厦', lat: 30.2538, lng: 120.2150, address: '上城区钱江新城' },
      { name: '杭州钱江新城核心区', lat: 30.2520, lng: 120.2050, address: '上城区钱江新城' },
      { name: '杭州EFC欧美金融城', lat: 30.2811, lng: 120.0031, address: '余杭区未来科技城' },
      { name: '杭州阿里西溪园区', lat: 30.2782, lng: 120.0311, address: '余杭区西溪' },
      { name: '杭州网易杭州园区', lat: 30.1520, lng: 120.2017, address: '滨江区网商路' },
      { name: '杭州海康威视总部', lat: 30.2100, lng: 120.2211, address: '滨江区阡陌路' },
      { name: '杭州滨江物联网小镇', lat: 30.2122, lng: 120.2290, address: '滨江区物联网街' },
      { name: '杭州云栖小镇', lat: 30.1277, lng: 120.0849, address: '西湖区云栖小镇' },
    ],
  },
  {
    city: 'shenzhen', cityName: '深圳',
    workplaces: [
      { name: '深圳平安金融中心', lat: 22.5332, lng: 114.0556, address: '福田区福田CBD' },
      { name: '深圳腾讯滨海大厦', lat: 22.5228, lng: 113.9353, address: '南山区科技园' },
      { name: '深圳华润春笋', lat: 22.5150, lng: 113.9465, address: '南山区后海' },
      { name: '深圳科兴科学园', lat: 22.5482, lng: 113.9436, address: '南山区科技园' },
      { name: '深圳深圳湾科技生态园', lat: 22.5299, lng: 113.9525, address: '南山区科技园' },
      { name: '深圳腾讯大厦', lat: 22.5404, lng: 113.9346, address: '南山区科技园' },
      { name: '深圳百度国际大厦', lat: 22.5246, lng: 113.9422, address: '南山区科技园' },
      { name: '深圳大疆天空之城', lat: 22.5775, lng: 113.9429, address: '南山区留仙洞' },
      { name: '深圳创维半导体设计大厦', lat: 22.5373, lng: 113.9536, address: '南山区科技园' },
      { name: '深圳中粮科技园', lat: 22.5760, lng: 113.9230, address: '宝安区中粮科技创新园' },
    ],
  },
];

/** Haversine 公式计算两点间距离 (km). */
function haversine(lat1, lon1, lat2, lon2) {
  const R = 6371.0;
  const toRad = (deg) => (deg * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

/**
 * 加载城市房源数据.
 *
 * @param {string} cityKey 城市英文 key
 * @returns {object[]|null} 房源列表, 加载失败返回 null
 */
function loadListings(cityKey) {
  const filePath = path.join(DATA_DIR, cityKey, 'listings.json');
  if (!fs.existsSync(filePath)) {
    console.warn(`  警告: ${filePath} 不存在, 跳过数据注入`);
    return null;
  }
  return JSON.parse(fs.readFileSync(filePath, 'utf-8'));
}

/**
 * 计算工作地周边 5km 内的房源统计信息.
 *
 * @param {object[]} listings 房源列表
 * @param {object} wp 工作地 { lat, lng }
 * @param {number} radius 搜索半径 (km), 默认 5
 * @returns {{totalCount:number, communityCount:number, avgPrice:number,
 *   minPrice:number, maxPrice:number, topCommunities:object[],
 *   regionList:string[], scrapedAt:string}} 统计结果
 */
function computeStats(listings, wp, radius = 5) {
  const nearby = listings.filter((l) => {
    if (!l.lat || !l.lng) return false;
    return haversine(wp.lat, wp.lng, l.lat, l.lng) <= radius;
  });

  if (!nearby.length) {
    return { totalCount: 0, communityCount: 0, avgPrice: 0, minPrice: 0, maxPrice: 0, topCommunities: [], regionList: [], scrapedAt: '' };
  }

  // 小区级聚合
  const commMap = {};
  const regionSet = new Set();
  for (const l of nearby) {
    const name = (l.community || '').trim();
    if (!name) continue;
    if (!commMap[name]) {
      commMap[name] = { name, count: 0, totalPrice: 0, minUP: Infinity, maxUP: 0 };
    }
    const c = commMap[name];
    c.count++;
    const price = parseFloat(l.price) || 0;
    c.totalPrice += price;
    const up = parseFloat(l.unit_price) || 0;
    if (up > 0) {
      c.minUP = Math.min(c.minUP, up);
      c.maxUP = Math.max(c.maxUP, up);
    }
    // 从 location 字段提取中文板块名: "杨浦-鞍山-通华大楼" → "鞍山"
    if (l.location) {
      const parts = l.location.split('-');
      if (parts.length >= 2) regionSet.add(parts[1]);
    }
  }

  // 排序取 top 15
  const topCommunities = Object.values(commMap)
    .sort((a, b) => a.count - b.count || a.minUP - b.minUP)
    .slice(0, 15)
    .map((c) => ({
      name: c.name,
      count: c.count,
      avgPrice: Math.round(c.totalPrice / c.count),
      unitPriceRange: c.minUP === Infinity ? '暂无' : `${Math.round(c.minUP)}-${Math.round(c.maxUP)}`,
    }));

  const prices = nearby.map((l) => parseFloat(l.price)).filter((p) => p > 0);
  const times = nearby.map((l) => l.scraped_at).filter(Boolean).sort();

  return {
    totalCount: nearby.length,
    communityCount: Object.keys(commMap).length,
    avgPrice: prices.length ? Math.round(prices.reduce((a, b) => a + b, 0) / prices.length) : 0,
    minPrice: prices.length ? Math.min(...prices) : 0,
    maxPrice: prices.length ? Math.max(...prices) : 0,
    topCommunities,
    regionList: [...regionSet].slice(0, 10),
    scrapedAt: times[times.length - 1] || '',
  };
}

/**
 * 为单个页面生成 SEO 内容.
 *
 * @param {string} cityName 城市中文名
 * @param {object} wp 工作地 { name, address, lat, lng }
 * @param {string} cityKey 城市英文 key
 * @param {object|null} stats computeStats 结果 (可能为空对象)
 * @returns {object} SEO 字段
 */
function buildSEO(cityName, wp, cityKey, stats) {
  const urlPath = `/${cityKey}/${wp.name}/`;
  const canonical = `${SITE_ORIGIN}${urlPath}`;

  // 修复城市名重复: "上海中心大厦" 已含 "上海", title 不再加城市前缀
  const displayName = wp.name.startsWith(cityName) ? wp.name : `${cityName}${wp.name}`;

  const title = `租房雷达 — ${displayName}周边5公里租房数据 | 单价地图·性价比排行`;
  const description = `${displayName}周边5公里租房数据分析：小区单价热力图、距离环性价比排行、户型统计、面积与价格分析。覆盖${wp.address}等区域的租房价格，帮您找到性价比最高的租房选择。`;
  const keywords = `${cityName}租房,${wp.name}租房,${cityName}租房价格,${cityName}租房地图,${wp.name}周边租房,租房单价,性价比租房,${wp.address}租房`;

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
        { '@type': 'ListItem', position: 3, name: wp.name, item: canonical },
      ],
    },
    mainEntity: {
      '@type': 'RealEstateListing',
      name: `${displayName}周边租房`,
      description: description,
      address: {
        '@type': 'PostalAddress',
        addressLocality: cityName,
        streetAddress: wp.address,
      },
    },
  };

  // 丰富 noscript 内容: 注入实际房源数据
  const lines = [
    `<h1>租房雷达 — ${displayName}周边5公里租房数据分析</h1>`,
    `<p>${displayName}(${wp.address})周边5公里租房数据分析平台，提供小区单价热力图、距离环性价比排行、户型统计。</p>`,
  ];

  if (stats && stats.totalCount > 0) {
    lines.push(`<h2>数据概览</h2>`);
    lines.push(`<p>周边5公里内共 <strong>${stats.totalCount}</strong> 套在租房源，覆盖 <strong>${stats.communityCount}</strong> 个小区，月租金 <strong>${stats.minPrice}-${stats.maxPrice}元</strong>，均价约 <strong>${stats.avgPrice}元/月</strong>。数据更新时间: ${stats.scrapedAt || '最近'}。</p>`);

    if (stats.topCommunities.length > 0) {
      lines.push(`<h2>热门小区排行 (按性价比)</h2>`);
      lines.push(`<table><thead><tr><th>小区名称</th><th>房源数</th><th>均价(元/月)</th><th>单价(元/㎡/月)</th></tr></thead><tbody>`);
      for (const c of stats.topCommunities) {
        lines.push(`<tr><td>${c.name}</td><td>${c.count}套</td><td>${c.avgPrice}</td><td>${c.unitPriceRange}</td></tr>`);
      }
      lines.push(`</tbody></table>`);
    }

    if (stats.regionList.length > 0) {
      lines.push(`<h2>覆盖板块</h2>`);
      lines.push(`<p>${stats.regionList.join('、')}等板块。</p>`);
    }
  }

  lines.push(`<h2>主要功能</h2>`);
  lines.push(`<ul>`);
  lines.push(`<li>租房价格热力地图 — 可视化展示各小区单价分布</li>`);
  lines.push(`<li>距离环排行 — 按通勤距离筛选性价比最高的租房小区</li>`);
  lines.push(`<li>交互式地图 — 支持自定义工作地点，实时计算通勤距离</li>`);
  lines.push(`<li>数据分析报告 — 租金分布、户型统计、面积与价格关系分析</li>`);
  lines.push(`</ul>`);

  const noscript = lines.join('\n      ');

  return {
    title, description, keywords, canonical,
    ogTitle: title, ogDescription: description, ogUrl: canonical,
    jsonLd, noscript,
  };
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

  // Fix 1: 不再插入重定向脚本. SPA (App.jsx readURLParams) 已内置 path URL 解析.
  // 百度蜘蛛无法执行 JS 重定向, 去掉后直接展示预渲染内容.

  // Fix 4: applicable-device 已在模板 index.html 中声明, 无需额外注入

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

  // 预加载各城市房源数据
  const listingsCache = {};
  for (const { city } of PAGES) {
    console.log(`加载 ${city} 房源数据...`);
    listingsCache[city] = loadListings(city);
  }

  for (const { city, cityName, workplaces } of PAGES) {
    const listings = listingsCache[city];
    for (const wp of workplaces) {
      const stats = listings ? computeStats(listings, wp) : null;
      const seo = buildSEO(cityName, wp, city, stats);
      const html = renderPage(template, seo);

      const outDir = path.join(DIST_DIR, city, wp.name);
      fs.mkdirSync(outDir, { recursive: true });
      fs.writeFileSync(path.join(outDir, 'index.html'), html);
      count++;

      if (stats) {
        console.log(`  ${wp.name}: ${stats.totalCount} 套房源, ${stats.communityCount} 个小区`);
      }
    }
  }

  console.log(`\n预渲染完成: ${count} 个页面`);
  console.log(`  输出目录: ${path.relative(process.cwd(), DIST_DIR)}/`);
}

main();
