import ReactECharts from 'echarts-for-react';

export default function PriceHistogram({ data }) {
  const prices = data
    .map((d) => parseInt(d.price, 10))
    .filter((p) => !isNaN(p) && p > 0 && p <= 30000);

  const avg = prices.length > 0 ? Math.round(prices.reduce((s, p) => s + p, 0) / prices.length) : 0;

  const bins = [];
  const binSize = 500;
  for (let i = 0; i <= 30000; i += binSize) {
    bins.push({ min: i, max: i + binSize, count: 0, label: `${i}-${i + binSize}` });
  }
  for (const p of prices) {
    const idx = Math.min(Math.floor(p / binSize), bins.length - 1);
    if (idx >= 0 && idx < bins.length) bins[idx].count++;
  }

  const option = {
    title: { text: '整体价格分布', left: 'center' },
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: bins.map((b) => b.label), axisLabel: { rotate: 45, fontSize: 10 } },
    yAxis: { type: 'value', name: '房源数量' },
    series: [{
      type: 'bar',
      data: bins.map((b) => b.count),
      itemStyle: { color: '#4e79a7' },
      markLine: {
        data: [{ xAxis: Math.floor(avg / binSize), name: `均价 ${avg.toLocaleString()}`, label: { formatter: `均价 ${avg.toLocaleString()}` } }],
        lineStyle: { color: 'red', type: 'dashed' },
      },
    }],
    grid: { left: 60, right: 30, bottom: 60, top: 50 },
  };

  return <ReactECharts option={option} style={{ height: 300 }} />;
}
