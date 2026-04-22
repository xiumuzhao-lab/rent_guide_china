#!/usr/bin/env node

/**
 * 将 output/ 下最新的爬取数据和地理编码缓存复制到前端 public/data/ 目录.
 *
 * 用法:
 *   node scripts/prepare_data.js
 */

const fs = require('fs');
const path = require('path');

const PROJECT_DIR = path.join(__dirname, '..');
const OUTPUT_DIR = path.join(PROJECT_DIR, 'output');
const PUBLIC_DATA_DIR = path.join(PROJECT_DIR, 'frontend', 'public', 'data');

function findLatest(prefix) {
  if (!fs.existsSync(OUTPUT_DIR)) return null;
  const files = fs.readdirSync(OUTPUT_DIR)
    .filter((f) => f.startsWith(prefix) && f.endsWith('.json'))
    .sort()
    .reverse();
  return files[0] || null;
}

function copyFile(srcName, destName) {
  const src = path.join(OUTPUT_DIR, srcName);
  const dest = path.join(PUBLIC_DATA_DIR, destName);
  if (fs.existsSync(src)) {
    fs.copyFileSync(src, dest);
    const size = (fs.statSync(dest).size / 1024).toFixed(1);
    console.log(`  ${destName} (${size} KB)`);
    return true;
  }
  return false;
}

function main() {
  fs.mkdirSync(PUBLIC_DATA_DIR, { recursive: true });

  // 找最新数据文件
  let dataFile = findLatest('lianjia_all_');
  if (!dataFile) {
    dataFile = findLatest('lianjia_');
  }
  if (!dataFile) {
    console.error('错误: 未找到爬取数据，请先运行: python3.10 lianjia_scraper.py --areas all');
    process.exit(1);
  }

  console.log('准备前端数据:');
  copyFile(dataFile, 'listings.json');

  // 地理编码缓存
  if (fs.existsSync(path.join(OUTPUT_DIR, 'community_geo_cache.json'))) {
    copyFile('community_geo_cache.json', 'geo_cache.json');
  } else {
    console.log('  geo_cache.json (未找到，跳过)');
  }

  console.log('\n完成! 运行 cd frontend && npm run dev 启动前端');
}

main();
