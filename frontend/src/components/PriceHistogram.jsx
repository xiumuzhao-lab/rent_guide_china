import ReactECharts from 'echarts-for-react';
import { REGION_NAMES, REGION_COLORS } from '../utils/constants';

const FALLBACK_COLORS = ['#4e79a7', '#f28e2b', '#e15759', '#76b7b2', '#59a14f', '#edc948', '#b07aa1', '#ff9da7'];

export default function PriceHistogram({ data, topRegions = [] }) {
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

  const binSize = 500;
  const binCount = Math.ceil(MAX_DISPLAY / binSize);

  const regions = topRegions.length > 0 ? topRegions : [...new Set(filtered.map((d) => d.region))].slice(0, 8);
  const regionLabels = regions.map((r) => REGION_NAMES[r] || r);

  // Build bins per region
  const binsByRegion = regions.map((reg) => {
    const bins = new Array(binCount).fill(0);
    for (const d of filtered) {
      if (d.region !== reg) continue;
      const p = parseInt(d.price, 10);
      if (isNaN(p) || p <= 0) continue;
      const idx = Math.min(Math.floor(p / binSize), binCount - 1);
      bins[idx]++;
    }
    return bins;
  });

  const binLabels = [];
  for (let i = 0; i < binCount; i++) {
    const lo = i * binSize;
    binLabels.push(lo >= 10000 ? `${(lo / 10000).toFixed(lo % 10000 === 0 ? 0 : 1)}w` : `${lo}`);
  }

  const avgBinIdx = Math.min(Math.floor(avg / binSize), binCount - 1);
  const medianBinIdx = Math.min(Math.floor(median / binSize), binCount - 1);

  const series = regions.map((reg, i) => ({
    name: regionLabels[i],
    type: 'bar',
    stack: 'total',
    data: binsByRegion[i],
    itemStyle: { color: REGION_COLORS[reg] || FALLBACK_COLORS[i % FALLBACK_COLORS.length] },
    emphasis: { focus: 'series' },
  }));

  // Summary label on top of each stacked bar
  const totals = binLabels.map((_, i) => binsByRegion.reduce((s, bins) => s + bins[i], 0));

  const option = {
    title: {
      text: `月租金分布 ≤1.5万 (按板块堆叠)${excludedCount > 0 ? `，${excludedCount} 套超1.5万未显示` : ''}`,
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
        data: totals,
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
              label: { formatter: `中位 ${median.toLocaleString()}元`, position: 'insideStartTop', fontSize: 11, color: '#3498db' },
            },
          ],
        },
        z: 100,
      },
    ],
    grid: { left: 60, right: 20, bottom: 55, top: 80 },
  };

  return <ReactECharts option={option} style={{ height: 280 }} />;
}
