import { useMemo, useState, useRef, useCallback } from 'react';
import { Tag, Tooltip } from 'antd';
import html2canvas from 'html2canvas';
import { SUBWAY_LINES } from '../utils/subway';
import { haversine } from '../utils/haversine';
import { REGION_NAMES } from '../utils/constants';
import CommunityListings from './CommunityListings';

/** 找到距离给定坐标最近的地铁站，返回 { station, line, dist } */
function findNearestStation(lat, lng) {
  let best = null;
  for (const line of SUBWAY_LINES) {
    for (const st of line.stations) {
      const d = haversine(lat, lng, st.lat, st.lng);
      if (!best || d < best.dist) {
        best = { station: st.name, line: line.name, dist: d, color: line.color };
      }
    }
  }
  return best;
}

/**
 * 综合评分: 单价越低越好，地铁越近越好，距离越近越好.
 * score = unitPriceNorm * 0.4 + subwayDistNorm * 0.35 + commuteDistNorm * 0.25
 * (归一化到 0-1，0 最优)
 */
function computeScore(up, subwayDist, commuteDist, maxUP, maxSubway, maxCommute) {
  const upN = maxUP > 0 ? up / maxUP : 0;
  const sdN = maxSubway > 0 ? subwayDist / maxSubway : 0;
  const cdN = maxCommute > 0 ? commuteDist / maxCommute : 0;
  return upN * 0.4 + sdN * 0.35 + cdN * 0.25;
}

function SubwayBadge({ station, line, dist, color }) {
  const text = dist < 1 ? `${Math.round(dist * 1000)}m` : `${dist.toFixed(1)}km`;
  const level = dist <= 0.5 ? 'gold' : dist <= 1 ? 'orange' : 'default';
  return (
    <Tooltip title={`${line} · ${station}`}>
      <Tag color={level === 'gold' ? '#fa8c16' : level === 'orange' ? '#fa8c16' : '#faad14'}
        style={{ margin: 0, fontSize: 11, lineHeight: '18px' }}>
        <span style={{ display: 'inline-block', width: 6, height: 6, borderRadius: '50%', background: color, marginRight: 4, verticalAlign: 'middle' }} />
        {station} {text}
      </Tag>
    </Tooltip>
  );
}

export default function SmartPicks({ enrichedStats, listings, workplace, isMobile }) {
  const [selected, setSelected] = useState(null);
  const picksRef = useRef(null);

  const handleExport = useCallback(() => {
    const el = picksRef.current;
    if (!el) return;
    html2canvas(el, { backgroundColor: null, scale: 2 }).then((canvas) => {
      canvas.toBlob((blob) => {
        if (!blob) return;
        import('../utils/download').then(({ downloadBlob }) => {
          downloadBlob(blob, `精选推荐_${workplace.name}.png`);
        });
      }, 'image/png');
    });
  }, [workplace.name]);

  const picks = useMemo(() => {
    // 筛选: 3km 内，均价 <= 6000
    const candidates = enrichedStats.filter((s) => s.dist <= 3 && s.avgPrice <= 6000);
    if (candidates.length === 0) return [];

    // 为每个候选小区计算最近地铁站
    const withSubway = candidates.map((s) => {
      const nearest = findNearestStation(s.lat, s.lng);
      return { ...s, subway: nearest };
    });

    // 归一化参数
    const maxUP = Math.max(...withSubway.map((s) => s.avgUnitPrice));
    const maxSubway = Math.max(...withSubway.map((s) => s.subway?.dist || 99));
    const maxCommute = Math.max(...withSubway.map((s) => s.dist));

    // 计算综合评分
    const scored = withSubway.map((s) => ({
      ...s,
      score: computeScore(s.avgUnitPrice, s.subway?.dist || 99, s.dist, maxUP, maxSubway, maxCommute),
    }));

    // 按综合评分排序，取 top 8
    scored.sort((a, b) => a.score - b.score);
    return scored.slice(0, 8);
  }, [enrichedStats]);

  const summary = useMemo(() => {
    if (picks.length === 0) return '';
    const top3 = picks.slice(0, 3);
    const names = top3.map((p) => p.name).join('、');
    const subwayInfo = top3
      .filter((p) => p.subway && p.subway.dist <= 1)
      .map((p) => `${p.name}距${p.subway.station}仅${Math.round(p.subway.dist * 1000)}m`)
      .join('，');
    const parts = [
      `距${workplace.name} 3km 内，月租 6000 元以下，`,
      `推荐${names}等 ${picks.length} 个高性价比小区（均价 ${Math.min(...picks.map((p) => p.avgPrice))}-${Math.max(...picks.map((p) => p.avgPrice))} 元）。`,
    ];
    if (subwayInfo) parts.push(subwayInfo, '步行即达。');
    return parts.join('');
  }, [picks, workplace.name]);

  if (picks.length === 0) return null;

  return (
    <div ref={picksRef} style={{
      background: 'linear-gradient(160deg, #fffbf0 0%, #fff9f0 50%, #fff 100%)',
      borderRadius: 12,
      padding: isMobile ? 14 : 22,
      border: '1px solid #ffd591',
      boxShadow: '0 1px 6px rgba(255,173,55,0.08)',
    }}>
      {/* 标题栏 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12, flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{
            width: 28, height: 28, borderRadius: 8,
            background: 'linear-gradient(135deg, #fa8c16, #ffc53d)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 14,
          }}>
            <span style={{ color: '#fff', fontSize: 16, fontWeight: 800, lineHeight: 1 }}>荐</span>
          </div>
          <span style={{ fontSize: isMobile ? 15 : 18, fontWeight: 700, color: '#262626' }}>精选推荐</span>
        </div>
        <Tag color="#fa8c16" style={{ margin: 0, fontSize: isMobile ? 10 : 11, borderRadius: 4 }}>
          3km内 · 6000元以下 · 地铁优先
        </Tag>
        <div style={{ flex: 1 }} />
        <button onClick={handleExport} style={{
          background: '#fff', border: '1px solid #d9d9d9', borderRadius: 6,
          padding: isMobile ? '4px 8px' : '2px 10px', cursor: 'pointer',
          fontSize: isMobile ? 11 : 12, color: '#666', whiteSpace: 'nowrap',
        }}>
          导出图片
        </button>
      </div>

      {/* 推荐摘要 */}
      <div style={{
        fontSize: isMobile ? 12 : 13, color: '#444', lineHeight: 1.9, marginBottom: isMobile ? 12 : 18,
        padding: '10px 14px',
        background: 'rgba(255,255,255,0.7)',
        borderRadius: 8,
        border: '1px solid rgba(255,173,55,0.2)',
        letterSpacing: 0.2,
      }}>
        {summary}
      </div>

      {/* 卡片网格 */}
      <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'repeat(2, 1fr)', gap: isMobile ? 8 : 14 }}>
        {picks.map((p, idx) => {
          const medalColors = ['#fa8c16', '#d48806', '#a0760a'];
          const isTop3 = idx < 3;
          return (
            <div key={p.name} onClick={() => setSelected(p.name)} style={{
              background: isTop3 ? '#fff' : '#fafcff',
              borderRadius: 10,
              padding: isMobile ? '12px 14px' : '14px 18px',
              border: isTop3 ? `1.5px solid ${medalColors[idx]}` : '1px solid #f0f0f0',
              cursor: 'pointer',
              boxShadow: isTop3 ? `0 2px 10px ${medalColors[idx]}18` : '0 1px 3px rgba(0,0,0,0.04)',
              transition: 'all 0.2s',
              position: 'relative',
            }}>
              {/* 排名角标 */}
              {isTop3 && (
                <div style={{
                  position: 'absolute', top: -1, left: -1,
                  width: 22, height: 22, borderRadius: '0 0 8px 0',
                  background: medalColors[idx],
                  color: '#fff',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontWeight: 700, fontSize: 11,
                }}>
                  {idx + 1}
                </div>
              )}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginLeft: isTop3 ? (isMobile ? 14 : 18) : 0, gap: 8 }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 600, fontSize: isMobile ? 13 : 14, color: '#262626', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', letterSpacing: 0.3 }}>
                    {p.name}
                  </div>
                  <div style={{ fontSize: isMobile ? 11 : 12, color: '#8c8c8c', marginTop: 3, letterSpacing: 0.2 }}>
                    {REGION_NAMES[p.region] || p.region} · 距{workplace.name} {p.dist}km
                  </div>
                </div>
                <div style={{ textAlign: 'right', flexShrink: 0 }}>
                  <div style={{ fontWeight: 700, fontSize: isMobile ? 17 : 20, color: isTop3 ? (idx === 2 ? '#595959' : '#d48806') : '#fa8c16', letterSpacing: -0.5 }}>
                    {p.avgPrice.toLocaleString()}
                  </div>
                  <div style={{ fontSize: isMobile ? 10 : 11, color: '#595959' }}>元/月</div>
                  <div style={{ fontSize: isMobile ? 10 : 11, color: '#595959', marginTop: 1 }}>
                    {p.avgUnitPrice}元/㎡ · {p.avgArea}㎡
                  </div>
                </div>
              </div>
              {/* 地铁标签 */}
              {p.subway && (
                <div style={{ marginTop: 8 }}>
                  <SubwayBadge {...p.subway} />
                </div>
              )}
            </div>
          );
        })}
      </div>

      <div style={{ fontSize: 11, color: '#d9d9d9', marginTop: 14, textAlign: 'center', letterSpacing: 0.3 }}>
        综合评分：单价 40% + 地铁距离 35% + 通勤距离 25%　点击小区查看详情
      </div>

      <CommunityListings
        visible={!!selected}
        community={selected}
        listings={listings}
        onClose={() => setSelected(null)}
      />
    </div>
  );
}
