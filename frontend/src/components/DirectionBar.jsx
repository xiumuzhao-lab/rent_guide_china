import ReactECharts from 'echarts-for-react';
import { REGION_NAMES, REGION_COLORS } from '../utils/constants';

export default function DirectionBar({ data }) {
  const dirCount = {};
  for (const d of data) {
    const dir = d.direction?.trim();
    if (dir) dirCount[dir] = (dirCount[dir] || 0) + 1;
  }
  const topDirs = Object.entries(dirCount)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 8)
    .map(([d]) => d);

  const regions = [...new Set(data.map((d) => d.region))];

  const series = regions.map((reg) => ({
    name: REGION_NAMES[reg] || reg,
    type: 'bar',
    data: topDirs.map((dir) =>
      data.filter((d) => d.region === reg && d.direction === dir).length
    ),
    itemStyle: { color: REGION_COLORS[reg] },
  }));

  const option = {
    title: { text: '各区域朝向分布', left: 'center' },
    tooltip: { trigger: 'axis' },
    legend: { top: 30 },
    xAxis: { type: 'category', data: topDirs },
    yAxis: { type: 'value', name: '房源数量' },
    series,
    grid: { left: 60, right: 30, bottom: 40, top: 70 },
  };

  return <ReactECharts option={option} style={{ height: 300 }} />;
}
