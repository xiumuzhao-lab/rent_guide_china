import { haversine } from './haversine';
import { REGIONS } from './constants';

// 上海各区中心坐标 (近似值, 用于坐标校验)
const DISTRICT_CENTERS = {
  '浦东': [31.22, 121.54], '松江': [31.03, 121.23],
  '闵行': [31.11, 121.38], '徐汇': [31.18, 121.44],
  '长宁': [31.22, 121.42], '静安': [31.23, 121.45],
  '黄浦': [31.23, 121.47], '普陀': [31.25, 121.40],
  '虹口': [31.26, 121.49], '杨浦': [31.27, 121.52],
  '宝山': [31.35, 121.45], '嘉定': [31.38, 121.25],
  '金山': [30.74, 121.34], '崇明': [31.63, 121.40],
  '奉贤': [30.92, 121.47], '青浦': [31.15, 121.12],
  // 北京
  '东城区': [39.93, 116.42], '西城区': [39.91, 116.37],
  '朝阳区': [39.92, 116.49], '丰台区': [39.86, 116.29],
  '石景山区': [39.91, 116.22], '海淀区': [39.96, 116.30],
  '门头沟区': [39.94, 116.10], '房山区': [39.75, 116.14],
  '通州区': [39.90, 116.66], '顺义区': [40.13, 116.65],
  '昌平区': [40.22, 116.23], '大兴区': [39.73, 116.34],
  '怀柔区': [40.32, 116.63], '平谷区': [40.14, 117.12],
  '密云区': [40.38, 116.84], '延庆区': [40.47, 115.97],
};

// 板块中心坐标 (region slug -> [lat, lng]), 用于 region 级坐标校验
// 从 listings 中位数坐标生成, 覆盖所有 206 个板块
const REGION_CENTERS = {
  anshan: [31.28, 121.51],
  anting: [31.29, 121.18],
  baihe: [31.28, 121.13],
  beicai: [31.18, 121.54],
  beiwaitan: [31.25, 121.50],
  beixinjing: [31.22, 121.37],
  biyun: [31.24, 121.59],
  buyecheng: [31.25, 121.46],
  caohejing: [31.18, 121.41],
  caojiadu: [31.23, 121.44],
  caolu: [31.27, 121.67],
  caoyang: [31.24, 121.41],
  changfeng1: [31.24, 121.40],
  changqiao: [31.14, 121.44],
  changshoulu: [31.24, 121.44],
  changzheng: [31.24, 121.37],
  chedun: [30.98, 121.25],
  chonggu: [31.20, 121.19],
  chuansha: [31.18, 121.70],
  chunshen: [31.11, 121.41],
  dachangzhen: [31.30, 121.41],
  dahua: [31.28, 121.42],
  daning: [31.27, 121.45],
  dapuqiao: [31.20, 121.47],
  datuanzhen: [30.97, 121.75],
  dongjiadu: [31.21, 121.50],
  dongjing2: [31.09, 121.24],
  dongwaitan: [31.26, 121.53],
  fengcheng: [30.91, 121.66],
  fengxianjinhui: [30.96, 121.51],
  fengzhuang: [31.25, 121.36],
  ganquanyichuan: [31.26, 121.43],
  gaodong: [31.32, 121.62],
  gaohang: [31.29, 121.59],
  gaojing: [31.32, 121.48],
  geqing: [31.23, 121.72],
  gongfu: [31.35, 121.43],
  gongkang: [31.33, 121.44],
  guangxin: [31.25, 121.43],
  gucun: [31.36, 121.37],
  gumei: [31.14, 121.39],
  haiwan: [30.84, 121.51],
  hanghua: [31.17, 121.35],
  hangtou: [31.06, 121.59],
  hengshanlu: [31.20, 121.44],
  hongqiao1: [31.20, 121.41],
  huacao: [31.21, 121.31],
  huadongligong: [31.14, 121.42],
  huaihaizhonglu: [31.22, 121.46],
  huajing: [31.12, 121.45],
  huamu: [31.21, 121.55],
  huangpubinjiang: [31.22, 121.50],
  huangxinggongyuan: [31.29, 121.53],
  huaxin: [31.23, 121.23],
  huinan: [31.05, 121.76],
  jiadinglaocheng: [31.38, 121.25],
  jiadingxincheng: [31.34, 121.26],
  jiangninglu: [31.24, 121.45],
  jiangqiao: [31.25, 121.32],
  jianguoxilu: [31.21, 121.46],
  jiangwanzhen: [31.31, 121.47],
  jingansi: [31.22, 121.45],
  jinganxincheng: [31.16, 121.38],
  jinhongqiao: [31.19, 121.40],
  jinhui: [31.17, 121.38],
  jinqiao: [31.27, 121.59],
  jinshanxincheng: [30.74, 121.34],
  jinyang: [31.25, 121.57],
  jinze: [31.07, 120.92],
  jiuting: [31.14, 121.32],
  juyuanxinqu: [31.39, 121.24],
  kangjian: [31.16, 121.42],
  kangqiao: [31.13, 121.58],
  kongjianglu: [31.28, 121.53],
  laogangzhen: [30.99, 121.86],
  laominhang: [31.01, 121.41],
  laoximen: [31.22, 121.48],
  liangcheng: [31.28, 121.47],
  lianyang: [31.23, 121.57],
  lingangxincheng: [30.90, 121.91],
  linpinglu: [31.26, 121.50],
  longbai: [31.17, 121.37],
  longhua: [31.18, 121.45],
  lujiazui: [31.22, 121.51],
  luodian: [31.40, 121.35],
  luojing: [31.46, 121.34],
  luxungongyuan: [31.27, 121.48],
  malu: [31.37, 121.28],
  maqiao: [31.04, 121.36],
  meilong: [31.13, 121.41],
  meiyuan1: [31.24, 121.52],
  minpu: [31.05, 121.53],
  nanjingdonglu: [31.24, 121.48],
  nanjingxilu: [31.23, 121.46],
  nanmatou: [31.20, 121.51],
  nanqiao: [30.92, 121.47],
  nanxiang: [31.30, 121.32],
  nichengzhen: [30.90, 121.81],
  penglaigongyuan: [31.21, 121.49],
  pengpu: [31.31, 121.45],
  pujiang1: [31.08, 121.50],
  qibao: [31.15, 121.35],
  quyang: [31.28, 121.49],
  renminguangchang: [31.24, 121.47],
  sanlin: [31.14, 121.51],
  shangda: [31.32, 121.38],
  shanghainanzhan: [31.15, 121.43],
  sheshan: [31.13, 121.21],
  shibo: [31.18, 121.50],
  shibobinjiang: [31.20, 121.49],
  shihudang: [31.10, 121.25],
  shuyuanzhen: [30.98, 121.87],
  sichuanbeilu: [31.26, 121.48],
  sijing: [31.11, 121.25],
  situan: [30.90, 121.74],
  songbao: [31.40, 121.49],
  songjiangdaxuecheng: [31.06, 121.23],
  songjianglaocheng: [31.01, 121.22],
  songjiangxincheng: [31.03, 121.22],
  songnan: [31.34, 121.49],
  suhewan: [31.24, 121.47],
  tangqiao: [31.21, 121.52],
  tangzhen: [31.22, 121.66],
  taopu: [31.28, 121.36],
  tianlin: [31.17, 121.43],
  tianshan: [31.22, 121.39],
  tonghe: [31.33, 121.45],
  waigang: [31.37, 121.16],
  waigaoqiao: [31.34, 121.58],
  wanli: [31.27, 121.40],
  wantiguan: [31.17, 121.44],
  wanxiangzhen: [30.96, 121.81],
  weifang: [31.22, 121.52],
  wujiaochang: [31.30, 121.51],
  wujing: [31.04, 121.47],
  wuliqiao: [31.20, 121.48],
  wuning: [31.24, 121.42],
  xianghuaqiao: [31.17, 121.10],
  xianxia: [31.21, 121.39],
  xiaokunshan: [31.03, 121.17],
  xiayang: [31.15, 121.13],
  xidu: [30.99, 121.44],
  xietulu: [31.20, 121.46],
  xinchang: [31.03, 121.65],
  xinchenglu1: [31.38, 121.27],
  xinhualu: [31.20, 121.42],
  xinjiangwancheng: [31.33, 121.51],
  xinminbieshu: [31.09, 121.35],
  xinqiao: [31.07, 121.32],
  xintiandi: [31.22, 121.48],
  xinzhuangbeiguangchang: [31.12, 121.37],
  xinzhuangnanguangchang: [31.10, 121.39],
  xizangbeilu: [31.25, 121.47],
  xuanqiao: [31.06, 121.71],
  xuhuibinjiang: [31.18, 121.46],
  xujiahui: [31.19, 121.44],
  xujing: [31.18, 121.28],
  xuxing: [31.41, 121.20],
  yangcheng: [31.28, 121.43],
  yangdong: [31.20, 121.54],
  yanghang: [31.38, 121.44],
  yangjing: [31.24, 121.55],
  yangsiqiantan: [31.16, 121.49],
  yingpu: [31.15, 121.09],
  yonghe: [31.29, 121.43],
  yuanshen: [31.23, 121.53],
  yuepu: [31.42, 121.41],
  yuqiao1: [31.15, 121.57],
  yuyuan: [31.22, 121.49],
  zhabeigongyuan: [31.27, 121.47],
  zhangjiang: [31.20, 121.61],
  zhangmiao: [31.34, 121.45],
  zhaoxiang: [31.14, 121.22],
  zhelin: [30.84, 121.48],
  zhenguang: [31.26, 121.38],
  zhenninglu: [31.21, 121.43],
  zhenru: [31.25, 121.41],
  zhiwuyuan: [31.14, 121.45],
  zhongshangongyuan: [31.22, 121.42],
  zhongyuan1: [31.26, 121.53],
  zhongyuanliangwancheng: [31.25, 121.44],
  zhoujiazuilu: [31.27, 121.53],
  zhoupu: [31.11, 121.59],
  zhuanghang: [30.91, 121.42],
  zhuanqiao: [31.07, 121.41],
  zhujiajiao: [31.12, 121.04],
  zhuqiao: [31.11, 121.76],
};
const REGION_TOLERANCE_KM = 20;

/**
 * 校验坐标是否在预期区的合理范围内.
 * 先按 location 字段做区级校验，再按 region 字段做板块级校验.
 */
function isValidCoord(lat, lng, location, region) {
  // 区级校验 (via location)
  if (location) {
    const district = location.split('-')[0];
    const center = DISTRICT_CENTERS[district];
    if (center) {
      const dist = haversine(lat, lng, center[0], center[1]);
      const tolerance = (district === '浦东' || district.endsWith('区')) ? 50 : 25;
      if (dist > tolerance) return false;
    }
  }
  // 板块级校验 (via region) — 防止 location 为空时坐标偏移
  if (region) {
    const center = REGION_CENTERS[region];
    if (center) {
      const dist = haversine(lat, lng, center[0], center[1]);
      if (dist > REGION_TOLERANCE_KM) return false;
    }
  }
  return true;
}

/**
 * 按小区聚合统计信息 (含平均经纬度 + 坐标校验).
 */
export function buildCommunityStats(data) {
  const grouped = {};
  for (const item of data) {
    const community = (item.community || '').trim();
    if (!community) continue;
    if (!grouped[community]) grouped[community] = [];
    grouped[community].push(item);
  }

  // 先按板块计算中位数坐标 (用于板块级校验)
  const boardCoords = {};
  for (const items of Object.values(grouped)) {
    for (const it of items) {
      const region = it.region || '';
      const lat = parseFloat(it.lat);
      const lng = parseFloat(it.lng);
      if (!region || isNaN(lat) || isNaN(lng) || lat === 0) continue;
      if (!boardCoords[region]) boardCoords[region] = [];
      boardCoords[region].push([lat, lng]);
    }
  }
  const boardMedians = {};
  for (const [region, coords] of Object.entries(boardCoords)) {
    if (coords.length < 3) continue;
    const sortedLats = coords.map((c) => c[0]).sort((a, b) => a - b);
    const sortedLngs = coords.map((c) => c[1]).sort((a, b) => a - b);
    const mid = Math.floor(sortedLats.length / 2);
    boardMedians[region] = [sortedLats[mid], sortedLngs[mid]];
  }

  const stats = {};
  for (const [name, items] of Object.entries(grouped)) {
    const prices = items
      .map((it) => parseInt(it.price, 10))
      .filter((p) => !isNaN(p) && p > 0);
    const areas = items
      .map((it) => parseFloat(it.area))
      .filter((a) => !isNaN(a) && a > 0);
    if (prices.length === 0) continue;

    const sumPrice = prices.reduce((s, p) => s + p, 0);
    const sumArea = areas.reduce((s, a) => s + a, 0);
    const avgPrice = Math.round(sumPrice / prices.length);
    const avgArea = areas.length > 0 ? sumArea / areas.length : 0;

    // 从 listings 计算平均经纬度
    const latLngs = items
      .map((it) => ({ lat: parseFloat(it.lat), lng: parseFloat(it.lng) }))
      .filter((it) => !isNaN(it.lat) && !isNaN(it.lng) && it.lat !== 0);
    let avgLat = latLngs.length > 0 ? latLngs.reduce((s, it) => s + it.lat, 0) / latLngs.length : null;
    let avgLng = latLngs.length > 0 ? latLngs.reduce((s, it) => s + it.lng, 0) / latLngs.length : null;

    // 坐标校验: 区级 + 板块级
    const location = items[0]?.location || '';
    const region = items[0]?.region || '';
    let coordValid = true;
    if (avgLat && avgLng) {
      // 区级校验
      if (!isValidCoord(avgLat, avgLng, location, region)) {
        coordValid = false;
      }
      // 板块级校验: 偏离板块中位数 > 10km 视为异常
      const median = boardMedians[region];
      if (median && haversine(avgLat, avgLng, median[0], median[1]) > 10) {
        coordValid = false;
      }
    }

    stats[name] = {
      count: items.length,
      avgPrice,
      minPrice: Math.min(...prices),
      maxPrice: Math.max(...prices),
      avgArea: Math.round(avgArea * 10) / 10,
      avgUnitPrice: sumArea > 0 ? Math.round((sumPrice / sumArea) * 10) / 10 : 0,
      region,
      lat: coordValid && avgLat ? Math.round(avgLat * 1000000) / 1000000 : null,
      lng: coordValid && avgLng ? Math.round(avgLng * 1000000) / 1000000 : null,
    };
  }
  return stats;
}

/**
 * 为每个小区添加距离信息.
 * 优先使用 buildCommunityStats 中从 listings 计算的坐标,
 * geoCache 仅作为后备.
 */
export function enrichStatsWithDistance(communityStats, workplace, geoCache, maxDistance = 15) {
  const results = [];
  for (const [name, stat] of Object.entries(communityStats)) {
    let lat = stat.lat;
    let lng = stat.lng;
    // 后备: 从 geo_cache 查找 (同样需要坐标校验)
    if (!lat || !lng) {
      const cached = geoCache?.[name];
      if (cached?.lat && cached?.lng) {
        if (isValidCoord(cached.lat, cached.lng, '', stat.region)) {
          lat = cached.lat;
          lng = cached.lng;
        }
      }
    }
    if (!lat || !lng) continue;
    const dist = haversine(workplace.lat, workplace.lng, lat, lng);
    if (dist > maxDistance) continue;
    results.push({
      ...stat,
      name,
      lat,
      lng,
      dist: Math.round(dist * 10) / 10,
    });
  }
  results.sort((a, b) => a.dist - b.dist);
  return results;
}

/**
 * 获取数据中的统计摘要.
 */
export function getOverview(listings) {
  const validListings = listings.filter((it) => {
    const p = parseInt(it.price, 10);
    const a = parseFloat(it.area);
    return !isNaN(p) && p > 0 && !isNaN(a) && a > 0;
  });

  const communities = new Set(listings.map((it) => it.community).filter(Boolean));

  const sumPrice = validListings.reduce((s, it) => s + parseInt(it.price, 10), 0);
  const sumArea = validListings.reduce((s, it) => s + parseFloat(it.area), 0);
  const avgPrice = validListings.length > 0 ? Math.round(sumPrice / validListings.length) : 0;
  const avgArea = validListings.length > 0 ? Math.round((sumArea / validListings.length) * 10) / 10 : 0;
  const avgUnitPrice = sumArea > 0 ? Math.round((sumPrice / sumArea) * 10) / 10 : 0;

  return {
    total: listings.length,
    communityCount: communities.size,
    avgPrice,
    avgArea,
    avgUnitPrice,
    scrapedAt: listings[0]?.scraped_at || '',
  };
}
