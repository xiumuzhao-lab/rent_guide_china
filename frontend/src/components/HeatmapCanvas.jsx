import { useRef, useEffect, useCallback, useMemo } from 'react';
import { SUBWAY_BY_CITY } from '../utils/subway';
import { haversine } from '../utils/haversine';

const RING_COLORS = { 3: '#2ecc71', 5: '#27ae60', 8: '#f39c12', 10: '#e67e22', 15: '#e74c3c' };
const DISTANCE_RINGS = [3, 5, 8, 10, 15];

function getUnitPriceColor(unitPrice, min, max) {
  if (max === min) return '#f39c12';
  const ratio = (unitPrice - min) / (max - min);
  const r = Math.round((1 - ratio) * 220);
  const g = Math.round(ratio * 180);
  return `rgb(${r}, ${g}, 50)`;
}

function getUnitPriceRGBA(unitPrice, min, max, alpha) {
  if (max === min) return `rgba(243,156,18,${alpha})`;
  const ratio = (unitPrice - min) / (max - min);
  const r = Math.round((1 - ratio) * 220);
  const g = Math.round(ratio * 180);
  return `rgba(${r}, ${g}, 50, ${alpha})`;
}

export default function HeatmapCanvas({ workplace, enrichedStats, maxDistance, city }) {
  const canvasRef = useRef(null);
  const containerRef = useRef(null);

  const subwayLines = SUBWAY_BY_CITY[city] || [];

  /** 只保留有站点在 maxDistance 范围内的地铁线路 */
  const filteredSubwayLines = useMemo(() => {
    return subwayLines.filter((line) =>
      line.stations.some((st) => haversine(workplace.lat, workplace.lng, st.lat, st.lng) <= maxDistance),
    );
  }, [subwayLines, workplace, maxDistance]);

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container || enrichedStats.length === 0) return;

    const W = container.clientWidth;
    const H = Math.round(W * 0.75);
    const dpr = window.devicePixelRatio || 1;
    canvas.width = W * dpr;
    canvas.height = H * dpr;
    canvas.style.width = W + 'px';
    canvas.style.height = H + 'px';

    const ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);

    // 移动端缩放因子：宽度 < 500 时等比缩小文字和元素
    const sf = W < 500 ? W / 600 : 1;

    // 背景
    ctx.fillStyle = '#f8f9fa';
    ctx.fillRect(0, 0, W, H);

    // 计算坐标范围
    const allLats = [workplace.lat, ...enrichedStats.map((s) => s.lat)];
    const allLngs = [workplace.lng, ...enrichedStats.map((s) => s.lng)];
    let latMin = Math.min(...allLats);
    let latMax = Math.max(...allLats);
    let lngMin = Math.min(...allLngs);
    let lngMax = Math.max(...allLngs);

    const padLat = (latMax - latMin) * 0.08;
    const padLng = (lngMax - lngMin) * 0.08;
    latMin -= padLat; latMax += padLat;
    lngMin -= padLng; lngMax += padLng;

    const cosLat = Math.cos((workplace.lat * Math.PI) / 180);
    const dataW = (lngMax - lngMin) * cosLat;
    const dataH = latMax - latMin;
    const imgRatio = W / H;
    const dataRatio = dataW / dataH;
    if (dataRatio < imgRatio) {
      const extra = (dataH * imgRatio - dataW) / (2 * cosLat);
      lngMin -= extra; lngMax += extra;
    } else {
      const extra = (dataW / imgRatio - dataH) / 2;
      latMin -= extra; latMax += extra;
    }

    const toX = (lng) => ((lng - lngMin) / (lngMax - lngMin)) * W;
    const toY = (lat) => ((latMax - lat) / (latMax - latMin)) * H;
    const kmToLat = (km) => km / 111.32;
    const kmToLng = (km) => km / (111.32 * cosLat);

    const unitPrices = enrichedStats.map((s) => s.avgUnitPrice).filter(Boolean);
    const minUP = Math.min(...unitPrices);
    const maxUP = Math.max(...unitPrices);
    const priceRange = maxUP - minUP;

    // 按距离环分组，avgPrice<=6000 中取单价最低 10% 标红
    const bottomSet = new Set();
    {
      const rings = [3, 5, 8, 10, 15];
      let prev = 0;
      const affordable = enrichedStats.filter((s) => s.avgPrice <= 6000);
      for (const r of rings) {
        const group = affordable.filter((s) => s.dist > prev && s.dist <= r);
        if (group.length === 0) { prev = r; continue; }
        const sorted = [...group].sort((a, b) => a.avgUnitPrice - b.avgUnitPrice);
        const cut = Math.max(1, Math.ceil(sorted.length * 0.1));
        for (let i = 0; i < cut && i < sorted.length; i++) {
          bottomSet.add(sorted[i].name);
        }
        prev = r;
      }
      const group = affordable.filter((s) => s.dist > 15);
      if (group.length > 0) {
        const sorted = [...group].sort((a, b) => a.avgUnitPrice - b.avgUnitPrice);
        const cut = Math.max(1, Math.ceil(sorted.length * 0.1));
        for (let i = 0; i < cut && i < sorted.length; i++) {
          bottomSet.add(sorted[i].name);
        }
      }
    }

    // 网格
    ctx.strokeStyle = '#e0e0e0';
    ctx.lineWidth = 0.5;
    ctx.globalAlpha = 0.3;
    const gridCount = 8;
    for (let i = 0; i <= gridCount; i++) {
      const x = (W * i) / gridCount;
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H); ctx.stroke();
      const y = (H * i) / gridCount;
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke();
    }
    ctx.globalAlpha = 1;

    // ── 地铁线路（分支间断开：连续站距 >5km 视为不同分支） ──
    ctx.lineJoin = 'round';
    ctx.lineCap = 'round';
    ctx.globalAlpha = 0.5;
    for (const line of filteredSubwayLines) {
      ctx.strokeStyle = line.color;
      ctx.lineWidth = Math.max(1, 2 * sf);
      ctx.beginPath();
      let started = false;
      let prevSt = null;
      for (const st of line.stations) {
        const x = toX(st.lng);
        const y = toY(st.lat);
        if (!started) {
          ctx.moveTo(x, y);
          started = true;
        } else if (prevSt && haversine(prevSt.lat, prevSt.lng, st.lat, st.lng) > 5) {
          // 分支断裂：跳过不连线，另起 moveTo
          ctx.moveTo(x, y);
        } else {
          ctx.lineTo(x, y);
        }
        prevSt = st;
      }
      ctx.stroke();
    }
    ctx.globalAlpha = 1;

    // ── 地铁线路名称标注（优先放在画布边缘） ──
    const lineLabelRects = [];
    ctx.globalAlpha = 1;
    for (const line of filteredSubwayLines) {
      const stations = line.stations;
      if (stations.length < 2) continue;
      const lineName = line.name;
      ctx.font = `bold ${Math.round(10 * sf)}px sans-serif`;
      const ltw = ctx.measureText(lineName).width;
      const llw = ltw + 8 * sf;
      const llh = 14 * sf;

      // 优先选择距工作地点最远（最靠近画布边缘）的端点站
      const endpoints = [
        { idx: 0, st: stations[0] },
        { idx: stations.length - 1, st: stations[stations.length - 1] },
      ];
      // 按距工作地点从远到近排序，优先选远端
      endpoints.sort((a, b) => {
        const da = haversine(workplace.lat, workplace.lng, a.st.lat, a.st.lng);
        const db = haversine(workplace.lat, workplace.lng, b.st.lat, b.st.lng);
        return db - da;
      });

      let placed = false;
      // 先尝试端点，再尝试中间站点
      const candidates = [...endpoints.map((e) => e.idx)];
      // 补充中间站点作为备选
      for (const ratio of [0.15, 0.85, 0.3, 0.7, 0.5]) {
        const idx = Math.floor(stations.length * ratio);
        if (!candidates.includes(idx)) candidates.push(idx);
      }

      for (const idx of candidates) {
        if (placed) break;
        const st = stations[idx];
        const mx = toX(st.lng);
        const my = toY(st.lat);
        // 必须在画布可见范围内
        const pad = llw / 2 + 4 * sf;
        if (mx < pad || mx > W - pad || my < llh + 4 * sf || my > H - 4 * sf) continue;

        // 计算线路在该点的方向，沿法线偏移放置标签
        const prevIdx = Math.max(0, idx - 1);
        const nextIdx = Math.min(stations.length - 1, idx + 1);
        const dx = toX(stations[nextIdx].lng) - toX(stations[prevIdx].lng);
        const dy = toY(stations[nextIdx].lat) - toY(stations[prevIdx].lat);
        const len = Math.sqrt(dx * dx + dy * dy) || 1;
        const nx = -dy / len;
        const ny = dx / len;

        for (const offset of [14 * sf, -14 * sf]) {
          if (placed) break;
          const labelX = mx + nx * offset;
          const labelY = my + ny * offset;
          const llx = labelX - llw / 2;
          const lly = labelY - llh / 2;

          const overlaps = lineLabelRects.some(
            (r) => llx < r.x + r.w + 2 && llx + llw > r.x - 2 && lly < r.y + r.h + 2 && lly + llh > r.y - 2,
          );
          if (overlaps) continue;
          lineLabelRects.push({ x: llx, y: lly, w: llw, h: llh });
          ctx.fillStyle = line.color;
          ctx.globalAlpha = 0.9;
          ctx.beginPath();
          ctx.roundRect(llx, lly, llw, llh, 7 * sf);
          ctx.fill();
          ctx.globalAlpha = 1;
          ctx.strokeStyle = '#fff';
          ctx.lineWidth = Math.max(0.8, 1.2 * sf);
          ctx.stroke();
          ctx.fillStyle = '#fff';
          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          ctx.fillText(lineName, labelX, labelY);
          placed = true;
        }
      }
    }
    ctx.globalAlpha = 1;


    // 距离环
    const visibleRings = DISTANCE_RINGS.filter((r) => r <= maxDistance);
    for (const rKm of visibleRings) {
      const color = RING_COLORS[rKm] || '#95a5a6';
      const rx = kmToLng(rKm) / (lngMax - lngMin) * W;
      const ry = kmToLat(rKm) / (latMax - latMin) * H;
      const cx = toX(workplace.lng);
      const cy = toY(workplace.lat);

      ctx.beginPath();
      ctx.ellipse(cx, cy, rx, ry, 0, 0, Math.PI * 2);
      ctx.strokeStyle = color;
      ctx.lineWidth = Math.max(1, 2.5 * sf);
      ctx.globalAlpha = 0.5;
      ctx.setLineDash([8 * sf, 4 * sf]);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.globalAlpha = 1;

      // 环标签
      const labelAngle = Math.PI * 0.3;
      const lx = cx + rx * Math.cos(labelAngle);
      const ly = cy - ry * Math.sin(labelAngle);
      const labelText = `${rKm} km`;
      ctx.font = `bold ${Math.round(13 * sf)}px sans-serif`;
      const tw = ctx.measureText(labelText).width;
      ctx.fillStyle = color;
      ctx.beginPath();
      const pad = 5 * sf;
      const br = 10 * sf;
      ctx.roundRect(lx - tw / 2 - pad, ly - 9 * sf - pad, tw + pad * 2, 18 * sf + pad * 2, br);
      ctx.fill();
      ctx.strokeStyle = '#fff';
      ctx.lineWidth = Math.max(1, 2 * sf);
      ctx.stroke();
      ctx.fillStyle = '#fff';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(labelText, lx, ly);
    }

    // 小区散点 (先画高价再画低价，低价覆盖在上面)
    const sorted = [...enrichedStats].sort((a, b) => b.avgUnitPrice - a.avgUnitPrice);
    for (const stat of sorted) {
      const x = toX(stat.lng);
      const y = toY(stat.lat);
      const isLowPrice = bottomSet.has(stat.name);
      const radius = isLowPrice ? Math.max(3, 7 * sf) : Math.max(2, 4 * sf);
      const color = isLowPrice ? '#e74c3c' : '#5b8ff9';

      ctx.beginPath();
      ctx.arc(x, y, radius, 0, Math.PI * 2);
      ctx.fillStyle = color;
      ctx.globalAlpha = isLowPrice ? 0.9 : 0.6;
      ctx.fill();
      ctx.strokeStyle = '#fff';
      ctx.lineWidth = Math.max(0.8, 1.5 * sf);
      ctx.stroke();
      ctx.globalAlpha = 1;
    }

    // ── 地铁站圆点（最上层，覆盖小区散点） ──
    const stationLabels = [];
    ctx.globalAlpha = 1;
    for (const line of filteredSubwayLines) {
      for (const st of line.stations) {
        const x = toX(st.lng);
        const y = toY(st.lat);
        if (x < -20 || x > W + 20 || y < -20 || y > H + 20) continue;

        if (st.transfer) {
          ctx.beginPath();
          ctx.arc(x, y, 5.5 * sf, 0, Math.PI * 2);
          ctx.fillStyle = '#fff';
          ctx.fill();
          ctx.strokeStyle = line.color;
          ctx.lineWidth = Math.max(1, 2.5 * sf);
          ctx.stroke();
          ctx.beginPath();
          ctx.arc(x, y, 3 * sf, 0, Math.PI * 2);
          ctx.fillStyle = line.color;
          ctx.fill();
        } else {
          ctx.beginPath();
          ctx.arc(x, y, 3 * sf, 0, Math.PI * 2);
          ctx.fillStyle = '#fff';
          ctx.fill();
          ctx.strokeStyle = line.color;
          ctx.lineWidth = Math.max(0.8, 1.5 * sf);
          ctx.stroke();
        }
        stationLabels.push({ x, y, name: st.name, color: line.color, transfer: st.transfer });
      }
    }

    // ── 站名标注（碰撞检测，最上层） ──
    const sLabelRects = [];
    stationLabels.sort((a, b) => (b.transfer ? 1 : 0) - (a.transfer ? 1 : 0));
    ctx.font = `bold ${Math.round(9 * sf)}px sans-serif`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    for (const sl of stationLabels) {
      const name = sl.name.length > 5 ? sl.name.slice(0, 5) + '…' : sl.name;
      const tw = ctx.measureText(name).width;
      const lw = tw + 6 * sf;
      const lh = 13 * sf;
      const lx = sl.x - lw / 2;
      const ly = sl.y + (sl.transfer ? 8 * sf : 5 * sf);

      const overlaps = sLabelRects.some(
        (r) => lx < r.x + r.w && lx + lw > r.x && ly < r.y + r.h && ly + lh > r.y,
      );
      if (overlaps) continue;

      sLabelRects.push({ x: lx, y: ly, w: lw, h: lh });
      ctx.fillStyle = 'rgba(255,255,255,0.88)';
      ctx.beginPath();
      ctx.roundRect(lx, ly, lw, lh, 2 * sf);
      ctx.fill();
      ctx.strokeStyle = sl.color;
      ctx.lineWidth = Math.max(0.4, 0.6 * sf);
      ctx.stroke();
      ctx.fillStyle = sl.color;
      ctx.fillText(name, sl.x, ly + 1.5 * sf);
    }

    // 工作地点
    const wpx = toX(workplace.lng);
    const wpy = toY(workplace.lat);
    ctx.beginPath();
    // 星形
    const starR = Math.max(8, 14 * sf);
    for (let i = 0; i < 5; i++) {
      const angle = -Math.PI / 2 + (i * 2 * Math.PI) / 5;
      const outerX = wpx + starR * Math.cos(angle);
      const outerY = wpy + starR * Math.sin(angle);
      const innerAngle = angle + Math.PI / 5;
      const innerX = wpx + (starR * 0.4) * Math.cos(innerAngle);
      const innerY = wpy + (starR * 0.4) * Math.sin(innerAngle);
      if (i === 0) ctx.moveTo(outerX, outerY);
      else ctx.lineTo(outerX, outerY);
      ctx.lineTo(innerX, innerY);
    }
    ctx.closePath();
    ctx.fillStyle = '#e74c3c';
    ctx.fill();
    ctx.strokeStyle = '#fff';
    ctx.lineWidth = Math.max(1, 2 * sf);
    ctx.stroke();

    // 工作地点名称
    ctx.font = `bold ${Math.round(13 * sf)}px sans-serif`;
    ctx.fillStyle = '#c0392b';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'middle';
    const nameText = workplace.name;
    const ntw = ctx.measureText(nameText).width;
    // 工作地点标签区域（用于碰撞检测）
    const wpLabelX = wpx + 14 * sf;
    const wpLabelY = wpy - 12 * sf;
    const wpLabelW = ntw + 14 * sf;
    const wpLabelH = 24 * sf;
    ctx.fillStyle = 'rgba(255,255,255,0.9)';
    ctx.strokeStyle = '#e74c3c';
    ctx.lineWidth = Math.max(0.6, 1 * sf);
    ctx.beginPath();
    ctx.roundRect(wpLabelX, wpLabelY, wpLabelW, wpLabelH, 6 * sf);
    ctx.fill();
    ctx.stroke();
    ctx.fillStyle = '#c0392b';
    ctx.fillText(nameText, wpx + 21 * sf, wpy);

    // 检查标签是否与工作地点区域碰撞
    const overlapsWorkplace = (x, y, w, h) => {
      return x < wpLabelX + wpLabelW + 8 && x + w > wpLabelX - 8 && y < wpLabelY + wpLabelH + 8 && y + h > wpLabelY - 8;
    };

    // 低价小区标签 — 碰撞检测防重叠（跳过 bottomSet，它们有专属红色标签）
    const labelRects = [];
    const labelStats = [...enrichedStats]
      .filter((s) => !bottomSet.has(s.name))
      .sort((a, b) => a.avgUnitPrice - b.avgUnitPrice);
    ctx.font = `${Math.round(10 * sf)}px sans-serif`;
    for (const stat of labelStats) {
      const x = toX(stat.lng);
      const y = toY(stat.lat);
      const name = stat.name.length > 4 ? stat.name.slice(0, 4) + '…' : stat.name;
      const text = `${name}${stat.avgUnitPrice}`;
      const tw2 = ctx.measureText(text).width;
      const lw = tw2 + 6 * sf;
      const lh = 14 * sf;
      const lx = x - lw / 2;
      const ly = y - 18 * sf - lh;

      // 碰撞检测（包括工作地点）
      const overlaps = labelRects.some(
        (r) => lx < r.x + r.w && lx + lw > r.x && ly < r.y + r.h && ly + lh > r.y
      ) || overlapsWorkplace(lx, ly, lw, lh);
      if (overlaps) continue;

      labelRects.push({ x: lx, y: ly, w: lw, h: lh });
      ctx.fillStyle = 'rgba(255,255,255,0.85)';
      ctx.beginPath();
      ctx.roundRect(lx, ly, lw, lh, 3);
      ctx.fill();
      ctx.fillStyle = '#555';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(text, x, ly + lh / 2);
    }

    // 各环内最低 20% 单价小区标签 — 最上层，红色醒目
    const bottom20Stats = enrichedStats.filter((s) => bottomSet.has(s.name));
    const sortedBottom20 = [...bottom20Stats].sort((a, b) => a.avgUnitPrice - b.avgUnitPrice);
    ctx.font = `bold ${Math.round(11 * sf)}px sans-serif`;
    for (const stat of sortedBottom20) {
      const x = toX(stat.lng);
      const y = toY(stat.lat);
      const name = stat.name.length > 5 ? stat.name.slice(0, 5) + '…' : stat.name;
      const text = `${name} ${stat.avgUnitPrice}元`;
      const tw2 = ctx.measureText(text).width;
      const lw = tw2 + 8 * sf;
      const lh = 16 * sf;

      const lx = x - lw / 2;
      const ly = y + 10 * sf;

      // 跳过与工作地点重叠的标签
      if (overlapsWorkplace(lx, ly, lw, lh)) continue;

      labelRects.push({ x: lx, y: ly, w: lw, h: lh });
      ctx.fillStyle = 'rgba(255,255,255,0.9)';
      ctx.beginPath();
      ctx.roundRect(lx, ly, lw, lh, 3);
      ctx.fill();
      ctx.fillStyle = '#e74c3c';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(text, lx + lw / 2, ly + lh / 2);
    }

    // 色阶条
    const barW = Math.max(10, 16 * sf);
    const barH = H * 0.4;
    const barX = W - 40 * sf;
    const barY = (H - barH) / 2;
    // 图例: 红色=高性价比(低价), 蓝色=其他
    const halfH = barH / 2;
    ctx.fillStyle = '#e74c3c';
    ctx.fillRect(barX, barY, barW, halfH);
    ctx.fillStyle = '#5b8ff9';
    ctx.fillRect(barX, barY + halfH, barW, halfH);
    ctx.strokeStyle = '#ccc';
    ctx.lineWidth = 1;
    ctx.strokeRect(barX, barY, barW, barH);
    ctx.fillStyle = '#666';
    ctx.font = `${Math.round(10 * sf)}px sans-serif`;
    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
    ctx.fillText('高性价比', barX + barW + 4 * sf, barY);
    ctx.textBaseline = 'bottom';
    ctx.fillText('其他', barX + barW + 4 * sf, barY + barH);

    // 标题
    ctx.font = `bold ${Math.round(14 * sf)}px sans-serif`;
    ctx.fillStyle = '#333';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.fillText(
      `${workplace.name} 周边 ${maxDistance}km 租房单价热力图 · 共 ${enrichedStats.length} 个小区`,
      W / 2, 12
    );
  }, [workplace, enrichedStats, maxDistance, filteredSubwayLines]);

  const handleExport = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    canvas.toBlob((blob) => {
      if (!blob) return;
      import('../utils/download').then(({ downloadBlob }) => {
        downloadBlob(blob, `${workplace.name}_${maxDistance}km_热力图.png`);
      });
    }, 'image/png');
  }, [workplace.name, maxDistance]);

  useEffect(() => {
    draw();
    window.addEventListener('resize', draw);
    return () => window.removeEventListener('resize', draw);
  }, [draw]);

  if (!workplace || enrichedStats.length === 0) return null;

  return (
    <div ref={containerRef} style={{ width: '100%', position: 'relative' }}>
      <button
        onClick={handleExport}
        style={{
          position: 'absolute', top: 8, right: 8, zIndex: 10,
          background: 'rgba(255,255,255,0.95)', border: '1px solid #d9d9d9',
          borderRadius: 6, padding: '4px 10px', cursor: 'pointer',
          fontSize: 12, color: '#333', boxShadow: '0 1px 4px rgba(0,0,0,0.1)',
        }}
      >
        导出
      </button>
      <canvas
        ref={canvasRef}
        style={{ borderRadius: 6, display: 'block' }}
      />
    </div>
  );
}
