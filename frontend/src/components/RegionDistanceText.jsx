import { useMemo } from 'react';
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

    const sorted = [...all].sort((a, b) => b.count - a.count);
    const selected = sorted.slice(0, 5);

    return selected
      .sort((a, b) => a.avgDist - b.avgDist)
      .map((d) => {
        const name = REGION_NAMES[d.region] || d.region;
        const distLabel = d.avgDist < 1 ? `${Math.round(d.avgDist * 1000)}m` : `${d.avgDist}km`;
        return `${name} ${d.count}个小区 单价${d.avgUnitPrice}元/㎡ 平均距${distLabel}`;
      });
  }, [enrichedStats, maxDistance]);

  const sep = isMobile ? ' | ' : ' \u00b7 ';
  return (
    <div style={{
      fontSize: isMobile ? 12 : 13, color: '#555', lineHeight: 2,
      padding: isMobile ? '8px 10px' : '10px 14px',
      background: '#fafafa', borderRadius: 6, border: '1px solid #f0f0f0',
    }}>
      <span style={{ fontWeight: 600, color: '#333' }}>通勤板块：</span>
      距{workplace.name} {maxDistance}km 内覆盖小区最多&nbsp;&rarr;&nbsp; {lines.join(sep)}
    </div>
  );
}