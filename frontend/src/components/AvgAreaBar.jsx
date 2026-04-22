import ReactECharts from 'echarts-for-react';
import { REGIONS, REGION_COLORS } from '../utils/constants';

export default function AvgAreaBar({ data }) {
  const regions = [...new Set(data.map((d) => d.region))];
  const avgAreas = regions.map((r) => {
    const areas = data
      .filter((d) => d.region === r)
      .map((d) => parseFloat(d.area))
      .filter((a) => !isNaN(a) && a > 0);
    return areas.length > 0 ? Math.round((areas.reduce((s, a) => s + a, 0) / areas.length) * 10) / 10 : 0;
  });

  const option = {
    title: { text: '各区域平均面积', left: 'center' },
    tooltip: { trigger: 'axis' },
    xAxis: {
      type: 'category',
      data: regions.map((r) => REGIONS[r]?.name || r),
    },
    yAxis: { type: 'value', name: '平均面积 (㎡)' },
    series: [{
      type: 'bar',
      data: avgAreas.map((v, i) => ({
        value: v,
        itemStyle: { color: REGION_COLORS[regions[i]] },
      })),
      label: { show: true, position: 'top', formatter: '{c}' },
    }],
    grid: { left: 60, right: 30, bottom: 40, top: 50 },
  };

  return <ReactECharts option={option} style={{ height: 300 }} />;
}
