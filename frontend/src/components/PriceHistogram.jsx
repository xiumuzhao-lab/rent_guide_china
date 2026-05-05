import ReactECharts from 'echarts-for-react';
import useIsMobile from '../hooks/useIsMobile';
import { REGION_NAMES, REGION_COLORS } from '../utils/constants';

const FALLBACK_COLORS = ['#4e79a7', '#f28e2b', '#e15759', '#76b7b2', '#59a14f', '#edc948', '#b07aa1', '#ff9da7'];

export default function PriceHistogram({ data, topRegions = [] }) {
  const isMobile = useIsMobile();
  const MAX_DISPLAY = 15000;
  const filtered = data.filter((d) => {
    const p = parseInt(d.price, 10);
    return !isNaN(p) && p > 0 && p <= MAX_DISPLAY;
  });
  if (filtered.length === 0) return null;

  const prices = filtered.map((d) => parseInt(d.price, 10));
  const excludedCount = data.filter((d) => {
    const p = parseInt(d.price, 10);
    return !isNaN(p) && p > MAX_DISPLAY;
  }).length;
  const avg = Math.round(prices.reduce((s, p) => s + p, 0) / prices.length);
  const sorted = [...prices].sort((a, b) => a - b);
  const median = sorted[Math.floor(sorted.length / 2)];

  // Dynamic bin size: adapt to actual data distribution
  const p5 = sorted[Math.floor(sorted.length * 0.05)] || 0;
  const p95 = sorted[Math.floor(sorted.length * 0.95)] || MAX_DISPLAY;
  const range = p95 - p5;
  const rawBinSize = Math.ceil(range / 30 / 100) * 100; // 30 bins covering 5th-95th percentile
  const binSize = Math.max(200, Math.min(rawBinSize, 2000));
  const minBin = Math.floor(p5 / binSize) * binSize;
  const maxBin = Math.ceil(p95 / binSize) * binSize;
  const binCount = Math.ceil((maxBin - minBin) / binSize);

  const regions = topRegions.length > 0 ? topRegions : [...new Set(filtered.map((d) => d.region))].slice(0, 8);
  const regionLabels = regions.map((r) => REGION_NAMES[r] || r);

  // Build bins per region (only within dynamic range)
  const binsByRegion = regions.map((reg) => {
    const bins = new Array(binCount).fill(0);
    for (const d of filtered) {
      if (d.region !== reg) continue;
      const p = parseInt(d.price, 10);
      if (isNaN(p) || p < minBin) continue;
      const idx = Math.floor((p - minBin) / binSize);
      if (idx >= 0 && idx < binCount) bins[idx]++;
    }
    return bins;
  });

  const binLabels = [];
  for (let i = 0; i < binCount; i++) {
    const lo = minBin + i * binSize;
    binLabels.push(lo >= 10000 ? `${(lo / 10000).toFixed(lo % 10000 === 0 ? 0 : 1)}w` : `${lo}`);
  }

  const avgBinIdx = Math.min(Math.floor((avg - minBin) / binSize), binCount - 1);
  const medianBinIdx = Math.min(Math.floor((median - minBin) / binSize), binCount - 1);

  const series = regions.map((reg, i) => ({
    name: regionLabels[i],
    type: 'bar',
    barWidth: '60%',
    data: binsByRegion[i],
    itemStyle: { color: REGION_COLORS[reg] || FALLBACK_COLORS[i % FALLBACK_COLORS.length] },
    emphasis: { focus: 'series' },
  }));

  // Total count per bin for the trend line overlay
  const totals = binLabels.map((_, i) => binsByRegion.reduce((s, bins) => s + bins[i], 0));
  const maxTotal = Math.max(...totals, 1);

  const option = {
    title: {
      text: `月租金分布 (${minBin.toLocaleString()}-${maxBin.toLocaleString()}元)${excludedCount > 0 ? `，${excludedCount} 套超1.5万未显示` : ''}`,
      left: 'center', top: 10, textStyle: { fontSize: 14 },
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: (params) => {
        const lo = params[0].dataIndex * binSize;
        const hi = lo + binSize;
        let html = `<b>${lo.toLocaleString()}-${hi.toLocaleString()} 元</b><br/>`;
        let total = 0;
        for (const p of params) {
          if (p.value > 0) {
            html += `${p.marker} ${p.seriesName}: <b>${p.value}</b> 套<br/>`;
            total += p.value;
          }
        }
        html += `合计: <b>${total}</b> 套`;
        return html;
      },
    },
    legend: { top: 32, type: 'scroll' },
    xAxis: {
      type: 'category',
      data: binLabels,
      axisLabel: { fontSize: 10, rotate: 30 },
      name: '月租金 (元)',
      nameLocation: 'center',
      nameGap: 36,
    },
    yAxis: { type: 'value', name: '房源数量' },
    series: [
      ...series,
      {
        type: 'line',
        data: new Array(binCount).fill(null),
        symbol: 'none',
        lineStyle: { width: 0 },
        areaStyle: { opacity: 0 },
        markLine: {
          silent: true,
          symbol: 'none',
          data: [
            {
              xAxis: avgBinIdx,
              lineStyle: { color: '#e74c3c', type: 'dashed', width: 2 },
              label: { formatter: `均价 ${avg.toLocaleString()}元`, position: 'insideEndTop', fontSize: 11, color: '#e74c3c' },
            },
            {
              xAxis: medianBinIdx,
              lineStyle: { color: '#3498db', type: 'dotted', width: 2 },
              label: { formatter: `中位 ${median.toLocaleString()}元`, position: 'insideEndTop', fontSize: 11, color: '#3498db' },
            },
          ],
        },
        z: 100,
      },
    ],
    grid: { left: 60, right: 20, bottom: 55, top: 80 },
  };

  return <ReactECharts option={option} notMerge style={{ height: isMobile ? 220 : 280 }} />;
}