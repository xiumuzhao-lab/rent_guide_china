import ReactECharts from 'echarts-for-react';

export default function RentTypePie({ data }) {
  const count = {};
  for (const d of data) {
    const t = d.rent_type?.trim();
    if (t) count[t] = (count[t] || 0) + 1;
  }
  const pieData = Object.entries(count).map(([name, value]) => ({ name, value }));

  const option = {
    title: { text: '租赁类型占比', left: 'center', top: 10, textStyle: { fontSize: 14 } },
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    series: [{
      type: 'pie',
      radius: ['30%', '55%'],
      center: ['50%', '58%'],
      data: pieData,
      label: { formatter: '{b}\n{d}%' },
      color: ['#4e79a7', '#f28e2b', '#e15759', '#76b7b2'],
    }],
  };

  return <ReactECharts option={option} notMerge style={{ height: 280 }} />;
}
