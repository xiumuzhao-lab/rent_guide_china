import ReactECharts from 'echarts-for-react';
import { REGION_NAMES, REGION_COLORS } from '../utils/constants';

const FALLBACK_COLORS = ['#4e79a7', '#f28e2b', '#e15759', '#76b7b2', '#59a14f', '#edc948', '#b07aa1', '#ff9da7'];

export default function RoomsBarChart({ data, topRegions = [] }) {
  const filteredData = topRegions.length > 0
    ? data.filter((d) => topRegions.includes(d.region))
    : data;

  const roomsCount = {};
  for (const d of filteredData) {
    const r = d.rooms?.trim();
    if (r) roomsCount[r] = (roomsCount[r] || 0) + 1;
  }
  const topRooms = Object.entries(roomsCount)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 8)
    .map(([r]) => r);
  const totalInTopRooms = topRooms.reduce((s, r) => s + roomsCount[r], 0);

  const regions = topRegions.length > 0 ? topRegions : [...new Set(data.map((d) => d.region))].slice(0, 8);

  const series = regions.map((reg, i) => ({
    name: REGION_NAMES[reg] || reg,
    type: 'bar',
    stack: 'total',
    data: topRooms.map((room) =>
      filteredData.filter((d) => d.region === reg && d.rooms === room).length
    ),
    itemStyle: { color: REGION_COLORS[reg] || FALLBACK_COLORS[i % FALLBACK_COLORS.length] },
    emphasis: { focus: 'series' },
  }));

  // Totals per room type for top labels
  const totals = topRooms.map((room) =>
    regions.reduce((s, reg) => s + filteredData.filter((d) => d.region === reg && d.rooms === room).length, 0)
  );

  const option = {
    title: { text: '各板块户型分布', left: 'center', top: 10, textStyle: { fontSize: 14 } },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: (params) => {
        const roomType = params[0].axisValue;
        let total = 0;
        let html = `<b>${roomType}</b><br/>`;
        for (const p of params) {
          if (p.value > 0) {
            html += `${p.marker} ${p.seriesName}: <b>${p.value}</b> 套<br/>`;
            total += p.value;
          }
        }
        const pct = totalInTopRooms > 0 ? Math.round((total / totalInTopRooms) * 100) : 0;
        html += `合计: <b>${total}</b> 套 (${pct}%)`;
        return html;
      },
    },
    legend: { top: 32, type: 'scroll' },
    xAxis: { type: 'category', data: topRooms, name: '户型' },
    yAxis: { type: 'value', name: '房源数量' },
    series: [
      ...series,
      {
        type: 'line',
        data: totals,
        symbol: 'circle',
        symbolSize: 4,
        lineStyle: { width: 0 },
        label: {
          show: true,
          position: 'top',
          fontSize: 10,
          fontWeight: 600,
          formatter: (p) => {
            const pct = totalInTopRooms > 0 ? Math.round((p.value / totalInTopRooms) * 100) : 0;
            return p.value > 0 ? `${p.value} (${pct}%)` : '';
          },
        },
        z: 100,
      },
    ],
    grid: { left: 60, right: 30, bottom: 40, top: 80 },
  };

  return <ReactECharts option={option} style={{ height: 280 }} />;
}
