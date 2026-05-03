#!/usr/bin/env node

/**
 * 将 output/ 下最新的爬取数据和地理编码缓存复制到前端 public/data/ 目录.
 *
 * 支持新的目录结构 output/{city}/{YYYY-MM}/  和旧的 output/ 平铺结构.
 *
 * 用法:
 *   node scripts/prepare_data.js [--city shanghai]
 */

const fs = require('fs');
const path = require('path');

const PROJECT_DIR = path.join(__dirname, '..');
const OUTPUT_DIR = path.join(PROJECT_DIR, 'output');
const PUBLIC_DATA_DIR = path.join(PROJECT_DIR, 'frontend', 'public', 'data');

// 解析 --city 参数
const args = process.argv.slice(2);
let city = 'shanghai';
for (let i = 0; i < args.length; i++) {
  if (args[i] === '--city' && args[i + 1]) {
    city = args[i + 1];
    i++;
  }
}

/**
 * 递归搜索目录，返回所有匹配 prefix 的 JSON 文件，按文件名排序.
 */
function findLatest(prefix, searchDir) {
  searchDir = searchDir || OUTPUT_DIR;
  if (!fs.existsSync(searchDir)) return null;

  const candidates = [];
  _collectFiles(searchDir, prefix, candidates);

  if (candidates.length === 0) return null;

  // 按文件名倒序，取最新的
  candidates.sort().reverse();
  // 跳过 partial 和 merged_latest
  for (const f of candidates) {
    const base = path.basename(f);
    if (!base.includes('.partial.') && !base.includes('merged_latest')) {
      return f;
    }
  }
  return null;
}

function _collectFiles(dir, prefix, results) {
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      _collectFiles(fullPath, prefix, results);
    } else if (entry.name.startsWith(prefix) && entry.name.endsWith('.json')) {
      results.push(fullPath);
    }
  }
}

/**
 * 查找城市的 geo cache 文件.
 */
function findGeoCache(cityDir) {
  // 新路径: output/{city}/community_geo_cache.json
  if (cityDir) {
    const p = path.join(cityDir, 'community_geo_cache.json');
    if (fs.existsSync(p)) return p;
  }
  // 旧路径: output/community_geo_cache.json
  const fallback = path.join(OUTPUT_DIR, 'community_geo_cache.json');
  if (fs.existsSync(fallback)) return fallback;
  return null;
}

function copyFile(srcPath, destName, destDir) {
  destDir = destDir || PUBLIC_DATA_DIR;
  const dest = path.join(destDir, destName);
  fs.copyFileSync(srcPath, dest);
  const size = (fs.statSync(dest).size / 1024).toFixed(1);
  console.log(`  ${destName} (${size} KB)`);
}

/**
 * 合并 partial 文件为单个 all 文件 (用于北京等非上海城市).
 */
function mergePartials(cityName, cityDir, timestamp) {
  if (!cityDir || !fs.existsSync(cityDir)) return null;

  // 递归搜索 partial 文件
  const partials = [];
  _collectPartialFiles(cityDir, partials);
  if (partials.length === 0) return null;

  const allListings = [];
  for (const pf of partials) {
    try {
      const raw = JSON.parse(fs.readFileSync(pf, 'utf-8'));
      const items = Array.isArray(raw) ? raw : (raw.data || []);
      allListings.push(...items);
    } catch (e) {
      // skip broken files
    }
  }

  if (allListings.length === 0) return null;

  // 写入合并文件
  const outFile = path.join(cityDir, `lianjia_all_${timestamp}.json`);
  fs.writeFileSync(outFile, JSON.stringify(allListings, null, 2));
  console.log(`  合并 ${partials.length} 个 partial 文件 -> ${allListings.length} 条房源`);
  return outFile;
}

function _collectPartialFiles(dir, results) {
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      _collectPartialFiles(fullPath, results);
    } else if (entry.name.endsWith('.partial.json')) {
      results.push(fullPath);
    }
  }
}

function formatTimestamp(date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  const h = String(date.getHours()).padStart(2, '0');
  const min = String(date.getMinutes()).padStart(2, '0');
  const s = String(date.getSeconds()).padStart(2, '0');
  return `${y}${m}${d}_${h}${min}${s}`;
}

function main() {
  const timestamp = formatTimestamp(new Date());
  const cityDir = path.join(OUTPUT_DIR, city);

  // 北京等非上海城市: 输出到 data/{city}/ 子目录
  const isDefaultCity = city === 'shanghai';
  const destDir = isDefaultCity ? PUBLIC_DATA_DIR : path.join(PUBLIC_DATA_DIR, city);
  fs.mkdirSync(destDir, { recursive: true });

  // 找最新数据文件 (优先城市目录，再 fallback 根目录)
  // 北京数据在 partial 文件里，需要合并
  let dataFile = null;
  if (city !== 'shanghai') {
    // 合并 partial 文件为 all 文件
    dataFile = mergePartials(city, cityDir, timestamp);
  }
  if (!dataFile) {
    dataFile = findLatest('lianjia_all_', cityDir);
  }
  if (!dataFile) {
    dataFile = findLatest('lianjia_all_', OUTPUT_DIR);
  }
  if (!dataFile) {
    dataFile = findLatest('lianjia_', cityDir);
  }
  if (!dataFile) {
    dataFile = findLatest('lianjia_', OUTPUT_DIR);
  }
  if (!dataFile) {
    console.error(`错误: 未找到 ${city} 的爬取数据`);
    process.exit(1);
  }

  const dataFileName = path.basename(dataFile);
  console.log(`准备前端数据 (城市: ${city}):`);
  console.log(`  数据源: ${path.relative(OUTPUT_DIR, dataFile)}`);

  copyFile(dataFile, `listings_${timestamp}.json`, destDir);
  copyFile(dataFile, 'listings.json', destDir);

  // 地理编码缓存
  const geoPath = findGeoCache(cityDir);
  if (geoPath) {
    copyFile(geoPath, `geo_cache_${timestamp}.json`, destDir);
    copyFile(geoPath, 'geo_cache.json', destDir);
  } else {
    console.log('  geo_cache.json (未找到，跳过)');
  }

  // 写入版本映射文件
  const versionMap = {
    city,
    listings: `listings_${timestamp}.json`,
    geo_cache: `geo_cache_${timestamp}.json`,
    timestamp,
  };
  fs.writeFileSync(
    path.join(destDir, 'versions.json'),
    JSON.stringify(versionMap, null, 2),
  );
  console.log(`  versions.json (${timestamp})`);

  console.log('\n完成!');
  if (isDefaultCity) {
    console.log('');
    console.log('下一步:');
    console.log('  git add frontend/public/data/');
    console.log('  git commit -m "Update rental data"');
    console.log('  git push   # 触发 GitHub Actions 自动部署');
  }
}

main();
