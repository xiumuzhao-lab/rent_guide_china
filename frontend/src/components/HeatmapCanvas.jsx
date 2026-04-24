import { useRef, useEffect, useCallback } from 'react';

const RING_COLORS = { 3: '#2ecc71', 5: '#27ae60', 8: '#f39c12', 10: '#e67e22', 15: '#e74c3c' };
const DISTANCE_RINGS = [3, 5, 8, 10, 15];

function getUnitPriceColor(unitPrice, min, max) {
  if (max === min) return '#f39c12';
  const ratio = (unitPrice - min) / (max - min);
  const r = Math.round(ratio * 220);
  const g = Math.round((1 - ratio) * 180);
  return `rgb(${r}, ${g}, 50)`;
}

function getUnitPriceRGBA(unitPrice, min, max, alpha) {
  if (max === min) return `rgba(243,156,18,${alpha})`;
  const ratio = (unitPrice - min) / (max - min);
  const r = Math.round(ratio * 220);
  const g = Math.round((1 - ratio) * 180);
  return `rgba(${r}, ${g}, 50, ${alpha})`;
}

export default function HeatmapCanvas({ workplace, enrichedStats, maxDistance }) {
  const canvasRef = useRef(null);
  const containerRef = useRef(null);

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

    // 前 20% 最低单价阈值
    const bottom20Threshold = priceRange > 0
      ? [...unitPrices].sort((a, b) => a - b)[Math.floor(unitPrices.length * 0.2)]
      : minUP;

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
      ctx.lineWidth = 2.5;
      ctx.globalAlpha = 0.5;
      ctx.setLineDash([8, 4]);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.globalAlpha = 1;

      // 环标签
      const labelAngle = Math.PI * 0.3;
      const lx = cx + rx * Math.cos(labelAngle);
      const ly = cy - ry * Math.sin(labelAngle);
      const labelText = `${rKm} km`;
      ctx.font = 'bold 13px sans-serif';
      const tw = ctx.measureText(labelText).width;
      ctx.fillStyle = color;
      ctx.beginPath();
      const pad = 5;
      const br = 10;
      ctx.roundRect(lx - tw / 2 - pad, ly - 9 - pad, tw + pad * 2, 18 + pad * 2, br);
      ctx.fill();
      ctx.strokeStyle = '#fff';
      ctx.lineWidth = 2;
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
      const isLowPrice = priceRange > 0 && stat.avgUnitPrice <= minUP + priceRange * 0.25;
      const radius = isLowPrice ? 7 : 4;
      const color = getUnitPriceColor(stat.avgUnitPrice, minUP, maxUP);

      ctx.beginPath();
      ctx.arc(x, y, radius, 0, Math.PI * 2);
      ctx.fillStyle = color;
      ctx.globalAlpha = isLowPrice ? 0.9 : 0.6;
      ctx.fill();
      ctx.strokeStyle = '#fff';
      ctx.lineWidth = 1.5;
      ctx.stroke();
      ctx.globalAlpha = 1;
    }

    // 工作地点
    const wpx = toX(workplace.lng);
    const wpy = toY(workplace.lat);
    ctx.beginPath();
    // 星形
    const starR = 14;
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
    ctx.lineWidth = 2;
    ctx.stroke();

    // 工作地点名称
    ctx.font = 'bold 13px sans-serif';
    ctx.fillStyle = '#c0392b';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'middle';
    const nameText = workplace.name;
    const ntw = ctx.measureText(nameText).width;
    ctx.fillStyle = 'rgba(255,255,255,0.9)';
    ctx.strokeStyle = '#e74c3c';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.roundRect(wpx + 14, wpy - 12, ntw + 14, 24, 6);
    ctx.fill();
    ctx.stroke();
    ctx.fillStyle = '#c0392b';
    ctx.fillText(nameText, wpx + 21, wpy);

    // 低价小区标签 — 碰撞检测防重叠
    const labelRects = [];
    const labelStats = [...enrichedStats]
      .sort((a, b) => a.avgUnitPrice - b.avgUnitPrice);
    ctx.font = '10px sans-serif';
    for (const stat of labelStats) {
      const x = toX(stat.lng);
      const y = toY(stat.lat);
      const name = stat.name.length > 4 ? stat.name.slice(0, 4) + '…' : stat.name;
      const text = `${name}${stat.avgUnitPrice}`;
      const tw2 = ctx.measureText(text).width;
      const lw = tw2 + 6;
      const lh = 14;
      const lx = x - lw / 2;
      const ly = y - 18 - lh;

      // 碰撞检测
      const overlaps = labelRects.some(
        (r) => lx < r.x + r.w && lx + lw > r.x && ly < r.y + r.h && ly + lh > r.y
      );
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

    // 前 20% 最低单价小区标签 — 最上层，红色醒目
    const bottom20Stats = enrichedStats.filter((s) => s.avgUnitPrice <= bottom20Threshold);
    const sortedBottom20 = [...bottom20Stats].sort((a, b) => a.avgUnitPrice - b.avgUnitPrice);
    ctx.font = 'bold 11px sans-serif';
    for (const stat of sortedBottom20) {
      const x = toX(stat.lng);
      const y = toY(stat.lat);
      const name = stat.name.length > 5 ? stat.name.slice(0, 5) + '…' : stat.name;
      const text = `${name} ${stat.avgUnitPrice}元`;
      const tw2 = ctx.measureText(text).width;
      const lw = tw2 + 8;
      const lh = 16;
      const lx = x - lw / 2;
      const ly = y + 10;

      // 碰撞检测 (复用 labelRects)
      const overlaps = labelRects.some(
        (r) => lx < r.x + r.w && lx + lw > r.x && ly < r.y + r.h && ly + lh > r.y
      );
      if (overlaps) continue;

      labelRects.push({ x: lx, y: ly, w: lw, h: lh });
      ctx.fillStyle = 'rgba(255,255,255,0.9)';
      ctx.beginPath();
      ctx.roundRect(lx, ly, lw, lh, 3);
      ctx.fill();
      ctx.fillStyle = '#e74c3c';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(text, x, ly + lh / 2);
    }

    // 色阶条
    const barW = 16;
    const barH = H * 0.4;
    const barX = W - 40;
    const barY = (H - barH) / 2;
    for (let i = 0; i < barH; i++) {
      const ratio = 1 - i / barH;
      ctx.fillStyle = getUnitPriceRGBA(minUP + priceRange * ratio, minUP, maxUP, 1);
      ctx.fillRect(barX, barY + i, barW, 1);
    }
    ctx.strokeStyle = '#ccc';
    ctx.lineWidth = 1;
    ctx.strokeRect(barX, barY, barW, barH);
    ctx.fillStyle = '#666';
    ctx.font = '10px sans-serif';
    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
    ctx.fillText(`${maxUP}元`, barX + barW + 4, barY);
    ctx.textBaseline = 'bottom';
    ctx.fillText(`${minUP}元`, barX + barW + 4, barY + barH);

    // 标题
    ctx.font = 'bold 14px sans-serif';
    ctx.fillStyle = '#333';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.fillText(
      `${workplace.name} 周边 ${maxDistance}km 租房单价热力图 · 共 ${enrichedStats.length} 个小区`,
      W / 2, 12
    );
  }, [workplace, enrichedStats, maxDistance]);

  useEffect(() => {
    draw();
    window.addEventListener('resize', draw);
    return () => window.removeEventListener('resize', draw);
  }, [draw]);

  if (!workplace || enrichedStats.length === 0) return null;

  return (
    <div ref={containerRef} style={{ width: '100%' }}>
      <canvas
        ref={canvasRef}
        style={{ borderRadius: 6, display: 'block' }}
      />
    </div>
  );
}
