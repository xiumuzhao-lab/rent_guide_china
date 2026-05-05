import ReactECharts from 'echarts-for-react';

export default function TopCommunities({ data }) {
  const count = {};
  for (const d of data) {
    const c = d.community?.trim();
    if (c) count[c] = (count[c] || 0) + 1;
  }
  const top15 = Object.entries(count)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 15)
    .reverse();

  const option = {
    title: { text: '热门小区 TOP 15', left: 'center' },
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'value', name: '房源数量' },
    yAxis: {
      type: 'category',
      data: top15.map(([name]) => name.length > 18 ? name.slice(0, 18) + '...' : name),
    },
    series: [{
      type: 'bar',
      data: top15.map(([, v]) => v),
      itemStyle: { color: '#59a14f' },
      label: { show: true, position: 'right', formatter: '{c}' },
    }],
    grid: { left: 140, right: 40, bottom: 30, top: 50 },
  };

  return <ReactECharts option={option} notMerge style={{ height: 350 }} />;
}
