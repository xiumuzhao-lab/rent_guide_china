import { useMemo, useRef, useCallback } from 'react';
import useIsMobile from '../hooks/useIsMobile';
import { REGION_NAMES } from '../utils/constants';

export default function RegionDistanceText({ enrichedStats, maxDistance, workplace }) {
  const isMobile = useIsMobile();

  const lines = useMemo(() => {
    const regionMap = {};
    for (const s of enrichedStats) {
      if (s.dist > maxDistance || !s.region) continue;
      if (!regionMap[s.region]) regionMap[s.region] = { dists: [], unitPrices: [], count: 0 };
      regionMap[s.region].dists.push(s.dist);
      regionMap[s.region].unitPrices.push(s.avgUnitPrice);
      regionMap[s.region].count++;
    }

    const all = Object.entries(regionMap).map(([region, data]) => {
      const avgDist = data.dists.reduce((s, d) => s + d, 0) / data.dists.length;
      const avgUP = data.unitPrices.reduce((s, v) => s + v, 0) / data.unitPrices.length;
      return { region, count: data.count, avgDist: Math.round(avgDist * 10) / 10, avgUnitPrice: Math.round(avgUP) };
    });

    // 按小区数降序取前 30%，最多 5 个
    const sorted = [...all].sort((a, b) => b.count - a.count);
    const top30Cut = Math.max(1, Math.ceil(sorted.length * 0.3));
    const selected = sorted.slice(0, Math.min(5, top30Cut));

    return selected
      .sort((a, b) => a.avgDist - b.avgDist)
      .map((d) => {
        const name = REGION_NAMES[d.region] || d.region;
        return `${name}（${d.count}个小区，均价 ${d.avgUnitPrice}元/㎡，平均 ${d.avgDist}km）`;
      });
  }, [enrichedStats, maxDistance]);

  if (lines.length === 0) return null;

  return (
    <div style={{
      fontSize: isMobile ? 12 : 13, color: '#555', lineHeight: 1.8,
      padding: isMobile ? '8px 10px' : '10px 14px',
      background: '#fafafa', borderRadius: 6, border: '1px solid #f0f0f0',
    }}>
      <span style={{ fontWeight: 600, color: '#333' }}>板块通勤距离：</span>
      距{workplace.name} {maxDistance}km 内小区数前 30% 板块 — {lines.join('、')}
    </div>
  );
}
