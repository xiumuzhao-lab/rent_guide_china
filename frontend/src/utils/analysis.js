import { DISTANCE_RINGS, RING_LABELS } from './constants';

/**
 * 根据筛选数据生成租房分析报告和建议.
 *
 * @param {object} params
 * @param {object} params.overview - 全局概览
 * @param {Array} params.enrichedStats - 筛选后小区统计
 * @param {Array} params.filteredListings - 筛选后房源
 * @param {object} params.workplace - 工作地点
 * @param {number} params.maxDistance - 最大距离
 * @returns {object} { summary, suggestions }
 */
export function generateAnalysis({ overview, enrichedStats, filteredListings, workplace, maxDistance }) {
  if (!enrichedStats.length || !filteredListings.length) {
    return { summary: '', suggestions: [] };
  }

  const prices = filteredListings
    .map((d) => parseInt(d.price, 10))
    .filter((p) => !isNaN(p) && p > 0)
    .sort((a, b) => a - b);
  if (prices.length === 0) {
    return { summary: '', suggestions: [] };
  }
  const areas = filteredListings
    .map((d) => parseFloat(d.area))
    .filter((a) => !isNaN(a) && a > 0);

  const count = filteredListings.length;
  const communityCount = enrichedStats.length;
  const avgPrice = Math.round(prices.reduce((s, p) => s + p, 0) / prices.length);
  const medianPrice = prices[Math.floor(prices.length / 2)];
  const p25Price = prices[Math.floor(prices.length * 0.25)];
  const p75Price = prices[Math.floor(prices.length * 0.75)];
  const avgArea = areas.length > 0 ? Math.round((areas.reduce((s, a) => s + a, 0) / areas.length) * 10) / 10 : 0;
  const sumPrice = prices.reduce((s, p) => s + p, 0);
  const sumArea = areas.reduce((s, a) => s + a, 0);
  const avgUnitPrice = sumArea > 0 ? Math.round((sumPrice / sumArea) * 10) / 10 : 0;

  // 按距离环统计
  const ringStats = [];
  let prev = 0;
  for (const r of DISTANCE_RINGS) {
    if (r > maxDistance) break;
    const group = enrichedStats.filter((s) => s.dist > prev && s.dist <= r);
    if (group.length === 0) { prev = r; continue; }
    const unitPrices = group.map((s) => s.avgUnitPrice);
    const avgUP = Math.round((unitPrices.reduce((s, v) => s + v, 0) / unitPrices.length) * 10) / 10;
    ringStats.push({
      ring: r,
      label: RING_LABELS[r] || `${prev}-${r}km`,
      count: group.length,
      avgUnitPrice: avgUP,
      cheapest: [...group].sort((a, b) => a.avgUnitPrice - b.avgUnitPrice).slice(0, 3),
    });
    prev = r;
  }

  // 找最优性价比环
  const bestRing = [...ringStats].sort((a, b) => a.avgUnitPrice - b.avgUnitPrice)[0];
  // 找最近且不贵的环
  const nearAffordable = [...ringStats]
    .filter((r) => r.avgUnitPrice <= avgUnitPrice)
    .sort((a, b) => a.ring - b.ring)[0];

  // 最便宜的小区
  const top3 = [...enrichedStats].sort((a, b) => a.avgUnitPrice - b.avgUnitPrice).slice(0, 3);

  // 户型分布
  const roomsCount = {};
  for (const d of filteredListings) {
    const r = d.rooms?.trim();
    if (r) roomsCount[r] = (roomsCount[r] || 0) + 1;
  }
  const topRoom = Object.entries(roomsCount).sort((a, b) => b[1] - a[1])[0];

  // 租赁类型
  const rentTypes = {};
  for (const d of filteredListings) {
    const t = d.rent_type?.trim();
    if (t) rentTypes[t] = (rentTypes[t] || 0) + 1;
  }
  const totalRent = Object.values(rentTypes).reduce((s, v) => s + v, 0);
  const mainType = Object.entries(rentTypes).sort((a, b) => b[1] - a[1])[0];
  const mainTypePct = mainType ? Math.round((mainType[1] / totalRent) * 100) : 0;

  // ---- 摘要 ----
  const summary = (
    `${workplace.name} 周边 ${maxDistance}km 范围内共 ${count} 套房源、${communityCount} 个小区，` +
    `月租金中位数 ${medianPrice.toLocaleString()} 元（均价 ${avgPrice.toLocaleString()} 元），` +
    `25%~75% 分位 ${p25Price.toLocaleString()}~${p75Price.toLocaleString()} 元，` +
    `平均单价 ${avgUnitPrice} 元/㎡/月，平均面积 ${avgArea} ㎡。` +
    `主力户型 ${topRoom ? topRoom[0] : '-'}（${topRoom ? Math.round((topRoom[1] / count) * 100) : 0}%），` +
    `${mainType ? mainType[0] : '-'} 占比 ${mainTypePct}%。`
  );

  // ---- 建议 ----
  const suggestions = [];

  // 建议1: 最优环
  if (bestRing) {
    const names = bestRing.cheapest.map((c) => c.name).join('、');
    suggestions.push({
      icon: '💰',
      title: '性价比最高区域',
      text: `${bestRing.label}（${bestRing.count} 个小区，均单价 ${bestRing.cheapest[0]?.avgUnitPrice || bestRing.avgUnitPrice} 元/㎡）是性价比最优的距离环。推荐: ${names}`,
    });
  }

  // 建议2: 近且实惠
  if (nearAffordable && nearAffordable !== bestRing) {
    suggestions.push({
      icon: '⚡',
      title: '通勤与价格兼得',
      text: `${nearAffordable.label} 单价 ${nearAffordable.avgUnitPrice} 元/㎡，低于平均线且距离近，是通勤+价格的最优平衡点。`,
    });
  }

  // 建议3: 预算分层
  if (p25Price && p75Price) {
    const cheapCount = prices.filter((p) => p <= p25Price).length;
    suggestions.push({
      icon: '📊',
      title: '预算参考',
      text: `预算 ≤${p25Price.toLocaleString()} 元可选 ${cheapCount} 套（前 25%）；` +
        `${p25Price.toLocaleString()}~${p75Price.toLocaleString()} 元是主流区间（占 50%）；` +
        `超过 ${p75Price.toLocaleString()} 元属于高位。`,
    });
  }

  // 建议4: 最便宜小区
  if (top3.length > 0) {
    const topInfo = top3.map((c) => `${c.name}（${c.avgUnitPrice}元/㎡，${c.dist}km）`).join(' > ');
    suggestions.push({
      icon: '🏆',
      title: '单价最低 TOP 3',
      text: topInfo,
    });
  }

  // 建议5: 面积建议
  if (avgArea > 0) {
    const areaTip = avgArea < 30
      ? '房源偏小，以单间/开间为主，适合单人居住'
      : avgArea < 50
        ? '以一居室为主，适合单人或情侣'
        : avgArea < 80
          ? '以两居室为主，适合合租或小家庭'
          : '以大户型为主，适合家庭整租';
    suggestions.push({
      icon: '🏠',
      title: '户型建议',
      text: `平均面积 ${avgArea} ㎡，${areaTip}。`,
    });
  }

  return { summary, suggestions };
}
