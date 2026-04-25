import ReactECharts from 'echarts-for-react';
import useIsMobile from '../hooks/useIsMobile';
import { REGION_NAMES, REGION_COLORS } from '../utils/constants';

const FALLBACK_COLORS = ['#4e79a7', '#f28e2b', '#e15759', '#76b7b2', '#59a14f', '#edc948', '#b07aa1', '#ff9da7'];

/**
 * Linear regression: returns { slope, intercept } for y = slope * x + intercept.
 */
function linearRegression(points) {
  const n = points.length;
  if (n < 2) return null;
  let sx = 0, sy = 0, sxy = 0, sx2 = 0;
  for (const [x, y] of points) {
    sx += x; sy += y; sxy += x * y; sx2 += x * x;
  }
  const denom = n * sx2 - sx * sx;
  if (denom === 0) return null;
  const slope = (n * sxy - sx * sy) / denom;
  const intercept = (sy - slope * sx) / n;
  return { slope, intercept };
}

export default function PriceVsArea({ data, topRegions = [] }) {
  const isMobile = useIsMobile();
  const filteredData = topRegions.length > 0
    ? data.filter((d) => topRegions.includes(d.region))
    : data;
  const regions = topRegions.length > 0
    ? topRegions
    : [...new Set(data.map((d) => d.region))].slice(0, 8);

  const allPoints = [];
  const series = regions.map((reg, i) => {
    const points = filteredData
      .filter((d) => d.region === reg)
      .map((d) => [parseFloat(d.area), parseInt(d.price, 10)])
      .filter(([a, p]) => !isNaN(a) && !isNaN(p) && a > 0 && p > 0);
    allPoints.push(...points);
    return {
      name: REGION_NAMES[reg] || reg,
      type: 'scatter',
      data: points,
      symbolSize: 10,
      itemStyle: {
        color: REGION_COLORS[reg] || FALLBACK_COLORS[i % FALLBACK_COLORS.length],
        opacity: 0.65,
      },
      emphasis: { itemStyle: { opacity: 1, borderColor: '#333', borderWidth: 1.5 } },
    };
  });

  // If too many points, downsample to reduce visual clutter
  const MAX_POINTS = 300;
  let displaySeries = series;
  if (allPoints.length > MAX_POINTS) {
    displaySeries = series.map((s) => {
      if (s.data.length <= Math.ceil(MAX_POINTS / regions.length)) return s;
      const step = Math.ceil(s.data.length / (MAX_POINTS / regions.length));
      return { ...s, data: s.data.filter((_, i) => i % step === 0) };
    });
  }

  // Dynamic axis ranges with padding based on actual distribution
  const areas = allPoints.map((p) => p[0]);
  const prices = allPoints.map((p) => p[1]);
  const sortedAreas = [...areas].sort((a, b) => a - b);
  const sortedPrices = [...prices].sort((a, b) => a - b);
  const areaP5 = sortedAreas[Math.floor(sortedAreas.length * 0.05)] || 0;
  const areaP95 = sortedAreas[Math.floor(sortedAreas.length * 0.95)] || 200;
  const priceP5 = sortedPrices[Math.floor(sortedPrices.length * 0.05)] || 0;
  const priceP95 = sortedPrices[Math.floor(sortedPrices.length * 0.95)] || 10000;

  // Round to nice numbers, add 10% padding
  const areaMin = 0;
  const areaMax = Math.ceil((areaP95 * 1.1) / 10) * 10;
  const priceMin = 0;
  const priceMax = Math.ceil((priceP95 * 1.1) / 1000) * 1000;

  // Sparse tick intervals: aim for ~8 ticks on each axis
  const areaInterval = Math.ceil(areaMax / 8 / 10) * 10;
  const priceInterval = Math.ceil(priceMax / 8 / 1000) * 1000;

  // Regression trend line
  const reg = linearRegression(allPoints);
  const trendData = reg
    ? [[0, Math.max(0, reg.intercept)], [areaMax, reg.slope * areaMax + reg.intercept]]
    : [];

  const avgArea = areas.length > 0 ? Math.round(areas.reduce((s, v) => s + v, 0) / areas.length) : 0;
  const avgPrice = prices.length > 0 ? Math.round(prices.reduce((s, v) => s + v, 0) / prices.length) : 0;

  const option = {
    title: { text: '价格 vs 面积', left: 'center', top: 10, textStyle: { fontSize: 14 } },
    tooltip: {
      trigger: 'item',
      formatter: (p) => {
        if (p.seriesName === '趋势线') {
          return `趋势线: 约 <b>${Math.round(p.data[1]).toLocaleString()}</b> 元 (${p.data[0]}㎡)`;
        }
        const unitPrice = p.data[0] > 0 ? Math.round(p.data[1] / p.data[0]) : 0;
        return `${p.seriesName}<br/>面积: <b>${p.data[0]}㎡</b><br/>租金: <b>${p.data[1].toLocaleString()}元</b><br/>单价: ${unitPrice} 元/㎡`;
      },
    },
    legend: { top: 32, type: 'scroll' },
    xAxis: {
      type: 'value',
      name: '面积 (㎡)',
      max: Math.min(areaMax, 300),
      interval: areaInterval,
      splitLine: { lineStyle: { type: 'dashed', opacity: 0.3 } },
    },
    yAxis: {
      type: 'value',
      name: '月租金 (元)',
      max: Math.min(priceMax, 80000),
      interval: priceInterval,
      splitLine: { lineStyle: { type: 'dashed', opacity: 0.3 } },
    },
    series: [
      ...displaySeries,
      ...(trendData.length > 0 ? [{
        name: '趋势线',
        type: 'line',
        data: trendData,
        symbol: 'none',
        lineStyle: { color: '#e74c3c', type: 'dashed', width: 2, opacity: 0.7 },
        tooltip: { trigger: 'item' },
        silent: true,
        z: 1,
      }] : []),
      {
        type: 'scatter',
        data: [],
        markLine: {
          silent: true,
          symbol: 'none',
          lineStyle: { width: 1 },
          data: [
            {
              xAxis: avgArea,
              lineStyle: { color: '#999', type: 'dotted' },
              label: { formatter: `均面积 ${avgArea}㎡`, position: 'insideEndTop', fontSize: 10, color: '#999' },
            },
            {
              yAxis: avgPrice,
              lineStyle: { color: '#999', type: 'dotted' },
              label: { formatter: `均租金 ${avgPrice.toLocaleString()}元`, position: 'insideEndTop', fontSize: 10, color: '#999' },
            },
          ],
        },
        z: 0,
      },
    ],
    grid: { left: 80, right: 30, bottom: 40, top: 80 },
  };

  return <ReactECharts option={option} style={{ height: isMobile ? 220 : 280 }} />;
}
