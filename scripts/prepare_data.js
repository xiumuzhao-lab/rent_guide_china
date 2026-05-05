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
const crypto = require('crypto');

const PROJECT_DIR = path.join(__dirname, '..');
const OUTPUT_DIR = path.join(PROJECT_DIR, 'output');
const PUBLIC_DATA_DIR = path.join(PROJECT_DIR, 'frontend', 'public', 'data');

// 城市边界 (与 scraper/geo/validation.py 保持一致)
const CITY_BOUNDARIES = {
  beijing:  { latMin: 39.40, latMax: 41.10, lngMin: 115.40, lngMax: 117.60 },
  shanghai: { latMin: 30.65, latMax: 31.95, lngMin: 120.70, lngMax: 122.10 },
  shenzhen: { latMin: 22.40, latMax: 22.90, lngMin: 113.70, lngMax: 114.70 },
  hangzhou: { latMin: 29.90, latMax: 30.60, lngMin: 119.80, lngMax: 120.70 },
};

// 板块 slug -> 中文名映射
const REGION_SLUG_MAP = {
  shanghai: {}, // 上海数据已用中文
  beijing: {}, // 北京数据已用中文
  hangzhou: {aoti: '奥体', baimahu: '白马湖', banshan: '半山', binjiangquzhengfu: '滨江区政府', caihe1: '采荷', caihongcheng: '彩虹城', changhe: '长河', changqing1112: '长庆', chaohui: '朝晖', chaoming11: '潮鸣', chengdongxincheng: '城东新城', chengzhan: '城站', chongxian: '崇贤', daguan: '大关', dajiangdong: '大江东', desheng: '德胜', deshengdong: '德胜东', dingqiao: '丁桥', donghu6: '东湖', daxuechengbei: '大学城北', feicuicheng1: '翡翠城', fuxing: '复兴', gaojiaoyuanqudong: '高教园区东', gaojiaoyuanquxi: '高教园区西', gongchenqiao: '拱宸桥', gongyeyuanbei: '工业园北', gongyeyuannan: '工业园南', gouzhuang: '勾庄', gulou2: '鼓楼', guali: '瓜沥', hemu: '和睦', heping2: '和平', hubin1: '湖滨', huajiachi: '华家池', huochedongzhan: '火车东站', hushu1: '湖墅', jianguobeilu: '建国北路', jianqiao: '笕桥', jinhua2: '进化', jinshahu: '金沙湖', jinjiang1: '近江', jingfang1: '景芳', jiubao: '九堡', liangzhu: '良渚', liuxia1: '留下', linpingxincheng: '临平新城', linpingyunhe: '临平运河', linpu: '临浦', liushuiyuan: '流水苑', laoyuhang: '老余杭', nanbuwocheng: '南部卧城', nanxing: '南星', nanxiaobu: '南肖埠', pingyao: '瓶窑', puyan: '浦沿', qibao1: '七堡', qianjiangshijicheng: '钱江世纪城', qianjiangxincheng: '钱江新城', qiaosi: '乔司', qiaoxi1: '桥西', qingbo: '清波', qingtai: '清泰', renhe2: '仁和', sanliting: '三里亭', sandun: '三墩', santang: '三塘', shenhua: '申花', shiqiao: '石桥', sichoucheng1: '丝绸城', sijiqing1: '四季青', tangqi1: '塘栖', tiyuchanglu: '体育场路', tianshui1: '天水', wandaguangchang2: '万达广场', wangjiang: '望江', weilaikejicheng: '未来科技城', wenyan: '闻堰', xianlin1: '闲林', xianghu: '湘湖', xiaoheshan: '小和山', xiaoshankaifaqu: '萧山开发区', xiaoshankejicheng: '萧山科技城', xiaoshanshiqu: '萧山市区', xiaoshanxinchengqu: '萧山新城区', xihujingqu: '西湖景区', xingqiao: '星桥', xiongzhenlou: '雄镇楼', xixi: '西溪', xixing: '西兴', xinyifang: '信义坊', yanjiangbei: '沿江北', yanjiangnan: '沿江南', yiqiao: '义桥', yunhexincheng: '运河新城', zhanongkou: '闸弄口', zhonganqiao: '众安桥', zhongtai: '中泰', wulin11: '武林'},
  shenzhen: {
    bagualing: '八卦岭', baihua: '百花', baishida: '百仕达',
    baishizhou: '白石洲', bantian: '坂田', baoanzhongxin: '宝安中心',
    bihai1: '碧海', bujidafen: '布吉大芬', bujiguan: '布吉关',
    bujijie: '布吉街', bujinanling: '布吉南岭', bujishiyaling: '布吉石牙岭',
    bujishuijing: '布吉水径', buxin: '布心', chegongmiao: '车公庙',
    chiwei: '赤尾', chunfenglu: '春风路', cuizhu: '翠竹',
    danzhutou: '丹竹头', daxuecheng3: '大学城', dayunxincheng: '大运新城',
    diwang: '地王', dongmen: '东门', fanshen: '翻身',
    futianbaoshuiqu: '福田保税区', futianzhongxin: '福田中心',
    fuyong: '福永', gongming: '公明', guangming1: '光明',
    guanlan: '观澜', hangcheng: '航城', henggang: '横岗',
    honghu: '洪湖', hongshan6: '红山', hongshuwan: '红树湾',
    houhai: '后海', huangbeiling: '黄贝岭', huanggang: '皇岗',
    huangmugang: '黄木岗', huaqiangbei: '华强北', huaqiangnan: '华强南',
    huaqiaocheng1: '华侨城', jingtian: '景田', kejiyuan: '科技园',
    lianhua: '莲花', liantang: '莲塘', longgangbaohe: '龙岗宝荷',
    longgangshuanglong: '龙岗双龙', longgangzhongxincheng: '龙岗中心城',
    longhuaxinqu: '龙华新区', longhuazhongxin: '龙华中心',
    luohukouan: '罗湖口岸', luoling: '螺岭', meilin: '梅林',
    meilinguan: '梅林关', meisha: '梅沙', minzhi: '民治',
    nanshanzhongxin: '南山中心', nantou: '南头', pingdi: '坪地',
    pinghu: '平湖', qianhai: '前海', qingshuihe: '清水河',
    shajing: '沙井', shangbu: '上步', shangtang: '上塘',
    shangxiasha: '上下沙', shatoujiao: '沙头角', shawei: '沙尾',
    shekou: '蛇口', shenzhenwan: '深圳湾', shixia: '石厦',
    shiyan: '石岩', songgang: '松岗', sungang: '笋岗',
    taoyuanju: '桃源居', wanxiangcheng: '万象城', xiangmeibei: '香梅北',
    xiangmihu: '香蜜湖', xicheng1: '西城', xili1: '西丽',
    xinan: '西乡', xinxiu: '新秀', xinzhou1: '新洲',
    xixiang: '西乡', yantiangang: '盐田港', yinhu: '银湖',
    yuanling: '园岭', zhuzilin: '竹子林',
  },
};

function isInCity(lat, lng, cityName) {
  const b = CITY_BOUNDARIES[cityName];
  if (!b) return true;
  return lat >= b.latMin && lat <= b.latMax && lng >= b.lngMin && lng <= b.lngMax;
}

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
 * 用 geo_cache 补全 listings 中缺失的 lat/lng.
 * 同时校验已有坐标是否在城市边界内，越界坐标会被清除.
 */
function enrichWithGeoCache(listings, geoCachePath, cityName) {
  if (!geoCachePath || !fs.existsSync(geoCachePath)) return { enriched: 0, cleared: 0 };

  const cache = JSON.parse(fs.readFileSync(geoCachePath, 'utf-8'));
  let enriched = 0;
  let cleared = 0;
  for (const item of listings) {
    // 清除越界坐标
    if (item.lat && item.lng && !isInCity(item.lat, item.lng, cityName)) {
      item.lat = null;
      item.lng = null;
      cleared++;
    }
    if (item.lat && item.lng) continue;
    const community = (item.community || '').trim();
    const entry = cache[community];
    if (entry && entry.lat && entry.lng && isInCity(entry.lat, entry.lng, cityName)) {
      item.lat = Math.round(entry.lat * 1000000) / 1000000;
      item.lng = Math.round(entry.lng * 1000000) / 1000000;
      enriched++;
    }
  }
  return { enriched, cleared };
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

  // 所有城市: 输出到 data/{city}/ 子目录
  const destDir = path.join(PUBLIC_DATA_DIR, city);
  fs.mkdirSync(destDir, { recursive: true });

  // 找最新数据文件 (优先城市目录)
  // 优先级: merged_latest (Python 管道输出，已清洗+补全) > partial 合并 > 任意最新
  const mergedLatest = path.join(cityDir, 'lianjia_merged_latest.json');
  let dataFile = fs.existsSync(mergedLatest) ? mergedLatest : null;
  if (!dataFile) {
    dataFile = mergePartials(city, cityDir, timestamp);
  }
  if (!dataFile) {
    dataFile = findLatest('lianjia_all_', cityDir);
  }
  if (!dataFile) {
    dataFile = findLatest('lianjia_', cityDir);
  }
  if (!dataFile) {
    console.error(`错误: 未找到 ${city} 的爬取数据`);
    process.exit(1);
  }

  // 读取数据并用 geo_cache 补全坐标
  const rawData = fs.readFileSync(dataFile, 'utf-8');
  const listings = JSON.parse(rawData);
  const geoPath = findGeoCache(cityDir);
  const { enriched, cleared } = enrichWithGeoCache(listings, geoPath, city);

  // 将 region slug 转为中文名
  const slugMap = REGION_SLUG_MAP[city] || {};
  if (Object.keys(slugMap).length > 0) {
    let converted = 0;
    for (const item of listings) {
      const cn = slugMap[item.region];
      if (cn) { item.region = cn; converted++; }
    }
    if (converted > 0) console.log(`  板块名转中文: ${converted} 条`);
  }

  const dataFileName = path.basename(dataFile);
  const beforeWith = listings.filter(it => it.lat && it.lng).length;
  console.log(`准备前端数据 (城市: ${city}):`);
  console.log(`  数据源: ${path.relative(OUTPUT_DIR, dataFile)}`);
  if (cleared > 0) {
    console.log(`  越界坐标清除: ${cleared} 条`);
  }
  if (enriched > 0) {
    console.log(`  geo 补全: ${enriched} 条 (${beforeWith}/${listings.length} 有坐标)`);
  }

  const outputJson = JSON.stringify(listings, null, 2);
  const contentHash = (data) => {
    const buf = typeof data === 'string' ? Buffer.from(data) : data;
    return crypto.createHash('md5').update(buf).digest('hex').slice(0, 8);
  };
  const listingsHash = contentHash(outputJson);

  const writeListings = (destName) => {
    const dest = path.join(destDir, destName);
    fs.writeFileSync(dest, outputJson);
    const size = (Buffer.byteLength(outputJson) / 1024).toFixed(1);
    console.log(`  ${destName} (${size} KB)`);
  };
  writeListings(`listings_${listingsHash}.json`);

  // 地理编码缓存
  let geoHash = '';
  if (geoPath) {
    const geoRaw = fs.readFileSync(geoPath);
    geoHash = contentHash(geoRaw);
    const hashedName = `geo_cache_${geoHash}.json`;
    const dest = path.join(destDir, hashedName);
    fs.writeFileSync(dest, geoRaw);
    const size = (geoRaw.length / 1024).toFixed(1);
    console.log(`  ${hashedName} (${size} KB)`);
  } else {
    console.log('  geo_cache.json (未找到，跳过)');
  }

  // 写入版本映射文件
  const versionMap = {
    city,
    listings: `listings_${listingsHash}.json`,
    geo_cache: geoHash ? `geo_cache_${geoHash}.json` : '',
    timestamp,
  };
  fs.writeFileSync(
    path.join(destDir, 'versions.json'),
    JSON.stringify(versionMap, null, 2),
  );
  console.log(`  versions.json (listings=${listingsHash}, geo=${geoHash || 'n/a'})`);

  console.log('\n完成!');
  console.log('');
  console.log('下一步:');
  console.log('  git add frontend/public/data/');
  console.log('  git commit -m "Update rental data"');
  console.log('  git push   # 触发 GitHub Actions 自动部署');
}

main();
