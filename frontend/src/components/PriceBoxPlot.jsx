import ReactECharts from 'echarts-for-react';
import { REGION_NAMES, REGION_COLORS } from '../utils/constants';

export default function PriceBoxPlot({ data }) {
  const regions = [...new Set(data.map((d) => d.region))];
  const boxData = regions.map((r) => {
    const prices = data
      .filter((d) => d.region === r)
      .map((d) => parseInt(d.price, 10))
      .filter((p) => !isNaN(p) && p > 0 && p <= 30000)
      .sort((a, b) => a - b);
    if (prices.length === 0) return null;
    const q1 = prices[Math.floor(prices.length * 0.25)];
    const q2 = prices[Math.floor(prices.length * 0.5)];
    const q3 = prices[Math.floor(prices.length * 0.75)];
    return [prices[0], q1, q2, q3, prices[prices.length - 1]];
  });

  const option = {
    title: { text: '各区域月租金分布 (≤3万)', left: 'center' },
    tooltip: { trigger: 'item' },
    xAxis: {
      type: 'category',
      data: regions.map((r) => REGION_NAMES[r] || r),
    },
    yAxis: { type: 'value', name: '月租金 (元/月)' },
    series: [{
      type: 'boxplot',
      data: boxData,
      itemStyle: { borderColor: '#4e79a7' },
    }],
    grid: { left: 80, right: 30, bottom: 40, top: 50 },
  };

  return <ReactECharts option={option} style={{ height: 300 }} />;
}
