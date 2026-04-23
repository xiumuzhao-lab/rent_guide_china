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
};
// 浦东因面积大 (含临港) 放宽容忍度
const DISTRICT_TOLERANCE_KM = 50;

/**
 * 校验坐标是否在预期区的合理范围内.
 */
function isValidCoord(lat, lng, location) {
  if (!location) return true;
  const district = location.split('-')[0];
  const center = DISTRICT_CENTERS[district];
  if (!center) return true;
  const dist = haversine(lat, lng, center[0], center[1]);
  const tolerance = district === '浦东' ? DISTRICT_TOLERANCE_KM : 25;
  return dist <= tolerance;
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
      if (!isValidCoord(avgLat, avgLng, location)) {
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
    // 后备: 从 geo_cache 查找
    if (!lat || !lng) {
      const cached = geoCache?.[name];
      if (cached?.lat && cached?.lng) {
        lat = cached.lat;
        lng = cached.lng;
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
