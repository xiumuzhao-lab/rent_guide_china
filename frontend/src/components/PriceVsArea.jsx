import ReactECharts from 'echarts-for-react';
import { REGION_NAMES, REGION_COLORS } from '../utils/constants';

export default function PriceVsArea({ data, topRegions = [] }) {
  const filteredData = topRegions.length > 0
    ? data.filter((d) => topRegions.includes(d.region))
    : data;
  const regions = topRegions.length > 0
    ? topRegions
    : [...new Set(data.map((d) => d.region))];

  const series = regions.map((reg) => {
    const points = filteredData
      .filter((d) => d.region === reg)
      .map((d) => [parseFloat(d.area), parseInt(d.price, 10)])
      .filter(([a, p]) => !isNaN(a) && !isNaN(p));
    return {
      name: REGION_NAMES[reg] || reg,
      type: 'scatter',
      data: points,
      symbolSize: 5,
      itemStyle: { color: REGION_COLORS[reg], opacity: 0.5 },
    };
  });

  const option = {
    title: { text: '价格 vs 面积', left: 'center', top: 10, textStyle: { fontSize: 14 } },
    tooltip: {
      trigger: 'item',
      formatter: (p) => `${p.seriesName}<br/>面积: ${p.data[0]}㎡<br/>租金: ${p.data[1].toLocaleString()}元`,
    },
    legend: { top: 32 },
    xAxis: { type: 'value', name: '面积 (㎡)', max: 200 },
    yAxis: { type: 'value', name: '月租金 (元/月)', max: 50000 },
    series,
    grid: { left: 80, right: 30, bottom: 40, top: 80 },
  };

  return <ReactECharts option={option} style={{ height: 280 }} />;
}
