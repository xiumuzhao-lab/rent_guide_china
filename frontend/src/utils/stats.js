import { haversine, getCommunityCoords } from './haversine';
import { REGIONS } from './constants';

/**
 * 按小区聚合统计信息.
 */
export function buildCommunityStats(data) {
  const grouped = {};
  for (const item of data) {
    const community = (item.community || '').trim();
    if (!community) continue;
    if (!grouped[community]) grouped[community] = [];
    grouped[community].push(item);
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

    const avgPrice = Math.round(prices.reduce((s, p) => s + p, 0) / prices.length);
    const avgArea = areas.length > 0 ? areas.reduce((s, a) => s + a, 0) / areas.length : 0;

    stats[name] = {
      count: items.length,
      avgPrice,
      minPrice: Math.min(...prices),
      maxPrice: Math.max(...prices),
      avgArea: Math.round(avgArea * 10) / 10,
      avgUnitPrice: avgArea > 0 ? Math.round((avgPrice / avgArea) * 10) / 10 : 0,
      region: items[0].region || '',
    };
  }
  return stats;
}

/**
 * 为每个小区添加距离和坐标信息.
 */
export function enrichStatsWithDistance(communityStats, workplace, geoCache, maxDistance = 15) {
  const results = [];
  for (const [name, stat] of Object.entries(communityStats)) {
    const coords = getCommunityCoords(name, geoCache);
    if (!coords) continue;
    const dist = haversine(workplace.lat, workplace.lng, coords.lat, coords.lng);
    if (dist > maxDistance) continue;
    results.push({
      name,
      lat: coords.lat,
      lng: coords.lng,
      dist: Math.round(dist * 10) / 10,
      ...stat,
    });
  }
  results.sort((a, b) => a.dist - b.dist);
  return results;
}

/**
 * 获取数据中的统计摘要.
 */
export function getOverview(listings) {
  const prices = listings
    .map((it) => parseInt(it.price, 10))
    .filter((p) => !isNaN(p) && p > 0);
  const communities = new Set(listings.map((it) => it.community).filter(Boolean));

  const avgPrice = prices.length > 0 ? Math.round(prices.reduce((s, p) => s + p, 0) / prices.length) : 0;
  const areas = listings
    .map((it) => parseFloat(it.area))
    .filter((a) => !isNaN(a) && a > 0);
  const avgArea = areas.length > 0 ? Math.round((areas.reduce((s, a) => s + a, 0) / areas.length) * 10) / 10 : 0;
  const avgUnitPrice = avgArea > 0 ? Math.round((avgPrice / avgArea) * 10) / 10 : 0;

  return {
    total: listings.length,
    communityCount: communities.size,
    avgPrice,
    avgUnitPrice,
    scrapedAt: listings[0]?.scraped_at || '',
  };
}
