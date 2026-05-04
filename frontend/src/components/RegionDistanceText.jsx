import { useMemo } from 'react';
import useIsMobile from '../hooks/useIsMobile';
import { REGION_NAMES } from '../utils/constants';

export default function RegionDistanceText({ enrichedStats, maxDistance, workplace }) {
  const isMobile = useIsMobile();

  const result = useMemo(() => {
    const regionMap = {};
    for (const s of enrichedStats) {
      if (s.dist > maxDistance || !s.region) continue;
      if (!regionMap[s.region]) regionMap[s.region] = { dists: [], unitPrices: [], prices: [], areas: [], count: 0 };
      regionMap[s.region].dists.push(s.dist);
      regionMap[s.region].unitPrices.push(s.avgUnitPrice);
      regionMap[s.region].prices.push(s.avgPrice);
      regionMap[s.region].areas.push(s.avgArea);
      regionMap[s.region].count++;
    }

    const median = (arr) => {
      const sorted = [...arr].sort((a, b) => a - b);
      const mid = Math.floor(sorted.length / 2);
      return sorted.length % 2 !== 0 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
    };

    const all = Object.entries(regionMap).map(([region, data]) => {
      const avgDist = data.dists.reduce((s, d) => s + d, 0) / data.dists.length;
      const avgUP = data.unitPrices.reduce((s, v) => s + v, 0) / data.unitPrices.length;
      return {
        region,
        name: REGION_NAMES[region] || region,
        count: data.count,
        avgDist: Math.round(avgDist * 10) / 10,
        avgUnitPrice: Math.round(avgUP),
        medianPrice: Math.round(median(data.prices)),
        medianArea: Math.round(median(data.areas)),
      };
    });

    if (all.length === 0) return null;

    const qualified = all.filter((r) => r.count >= 20);
    if (qualified.length === 0) return null;

    const minPrice = Math.min(...qualified.map((r) => r.avgUnitPrice));
    const minDist = Math.min(...qualified.map((r) => r.avgDist));
    const maxCount = Math.max(...qualified.map((r) => r.count));

    const cheapest = qualified.find((r) => r.avgUnitPrice === minPrice);
    const closest = qualified.find((r) => r.avgDist === minDist);
    const bestValue = qualified.find((r) => r.avgUnitPrice === minPrice && r.count === maxCount)
      || qualified.find((r) => r.avgUnitPrice === minPrice);

    const qualifiedRegions = new Set(qualified.map((r) => r.region));
    const allPrices = [];
    const allAreas = [];
    for (const [region, data] of Object.entries(regionMap)) {
      if (!qualifiedRegions.has(region)) continue;
      allPrices.push(...data.prices);
      allAreas.push(...data.areas);
    }
    const overallMedianPrice = Math.round(median(allPrices));
    const overallMedianArea = Math.round(median(allAreas));
    const totalCount = qualified.reduce((s, r) => s + r.count, 0);

    const picks = [];
    if (closest) {
      picks.push({ name: closest.name, label: '住得较近' });
    }
    if (bestValue && bestValue.region !== closest?.region) {
      picks.push({ name: bestValue.name, label: '性价比较高' });
    }
    const avgUP = qualified.reduce((s, r) => s + r.avgUnitPrice, 0) / qualified.length;
    const avgDist = qualified.reduce((s, r) => s + r.avgDist, 0) / qualified.length;
    const balanced = qualified
      .filter((r) => r.avgUnitPrice < avgUP && r.avgDist < avgDist)
      .filter((r) => r.region !== closest?.region && r.region !== bestValue?.region)
      .sort((a, b) => (a.avgUnitPrice / a.count) - (b.avgUnitPrice / b.count))[0];
    if (balanced) {
      picks.push({ name: balanced.name, label: '通勤性价比兼备' });
    }

    if (picks.length === 0) return null;
    return { picks, overallMedianPrice, overallMedianArea, totalCount };
  }, [enrichedStats, maxDistance]);

  if (!result) return null;

  const { picks, overallMedianPrice, overallMedianArea, totalCount } = result;
  const s = isMobile ? 12 : 13;

  return (
    <div style={{
      fontSize: s - 1, color: '#555', lineHeight: 1.7,
      padding: isMobile ? '6px 10px' : '7px 12px',
      background: 'linear-gradient(135deg, #fefce8 0%, #fff7ed 100%)',
      borderRadius: 6, border: '1px solid #fed7aa',
      display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 2,
    }}>
      <span style={{ fontWeight: 700, color: '#c2410c', marginRight: 4, letterSpacing: 1 }}>推荐</span>
      {picks.map((p, i) => (
        <span key={p.name}>
          {i > 0 && <span style={{ color: '#bbb', margin: '0 2px' }}>·</span>}
          <span style={{ fontWeight: 600, color: '#1e1e1e' }}>{p.name}</span>
          <span style={{ color: '#9a3412', fontSize: s - 1, marginLeft: 2 }}>{p.label}</span>
        </span>
      ))}
      <span style={{ color: '#d4d4d4', margin: '0 6px' }}>|</span>
      <span style={{ color: '#737373' }}>
        距离内月租中位数&nbsp;
        <b style={{ color: '#b45309', fontSize: s + 1 }}>¥{overallMedianPrice.toLocaleString()}</b>
        &nbsp;·&nbsp;面积中位数&nbsp;
        <b style={{ color: '#b45309', fontSize: s + 1 }}>{overallMedianArea}㎡</b>
        &nbsp;·&nbsp;覆盖小区&nbsp;
        <b style={{ color: '#737373' }}>{totalCount.toLocaleString()}</b> 个
      </span>
    </div>
  );
}
