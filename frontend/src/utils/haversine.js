/**
 * Haversine 公式计算两点间距离 (km).
 */
export function haversine(lat1, lon1, lat2, lon2) {
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
 * 根据 geo_cache.json 查找小区坐标.
 * geo_cache 格式: { "小区名": { lat, lng, source } }
 */
export function getCommunityCoords(community, geoCache) {
  const entry = geoCache?.[community];
  if (entry && entry.lat && entry.lng) {
    return { lat: entry.lat, lng: entry.lng };
  }
  return null;
}
