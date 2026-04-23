import ReactECharts from 'echarts-for-react';
import { REGION_NAMES, REGION_COLORS } from '../utils/constants';

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

  const regions = topRegions.length > 0 ? topRegions : [...new Set(data.map((d) => d.region))];

  const series = regions.map((reg) => ({
    name: REGION_NAMES[reg] || reg,
    type: 'bar',
    data: topRooms.map((room) =>
      filteredData.filter((d) => d.region === reg && d.rooms === room).length
    ),
    itemStyle: { color: REGION_COLORS[reg] },
  }));

  const option = {
    title: { text: '各区域户型分布', left: 'center', top: 10, textStyle: { fontSize: 14 } },
    tooltip: { trigger: 'axis' },
    legend: { top: 32 },
    xAxis: { type: 'category', data: topRooms },
    yAxis: { type: 'value', name: '房源数量' },
    series,
    grid: { left: 60, right: 30, bottom: 40, top: 80 },
  };

  return <ReactECharts option={option} style={{ height: 280 }} />;
}
