import ReactECharts from 'echarts-for-react';
import { REGIONS, REGION_COLORS } from '../utils/constants';

export default function RoomsBarChart({ data }) {
  const roomsCount = {};
  for (const d of data) {
    const r = d.rooms?.trim();
    if (r) roomsCount[r] = (roomsCount[r] || 0) + 1;
  }
  const topRooms = Object.entries(roomsCount)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 8)
    .map(([r]) => r);

  const regions = [...new Set(data.map((d) => d.region))];

  const series = regions.map((reg) => ({
    name: REGIONS[reg]?.name || reg,
    type: 'bar',
    data: topRooms.map((room) =>
      data.filter((d) => d.region === reg && d.rooms === room).length
    ),
    itemStyle: { color: REGION_COLORS[reg] },
  }));

  const option = {
    title: { text: '各区域户型分布', left: 'center' },
    tooltip: { trigger: 'axis' },
    legend: { top: 30 },
    xAxis: { type: 'category', data: topRooms },
    yAxis: { type: 'value', name: '房源数量' },
    series,
    grid: { left: 60, right: 30, bottom: 40, top: 70 },
  };

  return <ReactECharts option={option} style={{ height: 300 }} />;
}
