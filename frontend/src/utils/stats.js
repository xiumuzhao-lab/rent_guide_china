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

    const sumPrice = prices.reduce((s, p) => s + p, 0);
    const sumArea = areas.reduce((s, a) => s + a, 0);
    const avgPrice = Math.round(sumPrice / prices.length);
    const avgArea = areas.length > 0 ? sumArea / areas.length : 0;

    stats[name] = {
      count: items.length,
      avgPrice,
      minPrice: Math.min(...prices),
      maxPrice: Math.max(...prices),
      avgArea: Math.round(avgArea * 10) / 10,
      avgUnitPrice: sumArea > 0 ? Math.round((sumPrice / sumArea) * 10) / 10 : 0,
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
