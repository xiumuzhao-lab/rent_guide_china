import { useState } from 'react';
import ReactECharts from 'echarts-for-react';
import { REGION_NAMES, REGION_COLORS } from '../utils/constants';
import { Modal, Table } from 'antd';

const FALLBACK_COLORS = ['#4e79a7', '#f28e2b', '#e15759', '#76b7b2', '#59a14f', '#edc948', '#b07aa1', '#ff9da7'];

const columns = [
  {
    title: '标题',
    dataIndex: 'title',
    key: 'title',
    ellipsis: true,
    render: (text, record) => (
      <a href={record.url} target="_blank" rel="noreferrer">{text}</a>
    ),
  },
  {
    title: '小区',
    dataIndex: 'community',
    key: 'community',
    width: 120,
    ellipsis: true,
  },
  {
    title: '户型',
    dataIndex: 'rooms',
    key: 'rooms',
    width: 90,
  },
  {
    title: '面积',
    dataIndex: 'area',
    key: 'area',
    width: 70,
    render: (v) => v ? `${v}㎡` : '-',
  },
  {
    title: '月租',
    dataIndex: 'price',
    key: 'price',
    width: 80,
    sorter: (a, b) => a.price - b.price,
    render: (v) => `${v?.toLocaleString()}元`,
  },
];

export default function TopRegionsBar({ enrichedStats, listings }) {
  const [selected, setSelected] = useState(null);

  // 从 enrichedStats 按板块统计小区数量（已去重聚合）
  const regionCommunities = {};
  for (const s of enrichedStats) {
    const r = s.region;
    if (r) {
      if (!regionCommunities[r]) regionCommunities[r] = new Set();
      regionCommunities[r].add(s.name);
    }
  }

  const top8 = Object.entries(regionCommunities)
    .map(([r, set]) => [r, set.size])
    .sort((a, b) => b[1] - a[1])
    .slice(0, 8);

  if (top8.length === 0) return null;

  const names = top8.map(([r]) => REGION_NAMES[r] || r);
  const values = top8.map(([, v]) => v);
  const slugs = top8.map(([r]) => r);
  const colors = top8.map(([r], i) => REGION_COLORS[r] || FALLBACK_COLORS[i]);

  const option = {
    title: { text: '命中板块 Top 8 (小区数)', left: 'center', top: 10, textStyle: { fontSize: 14 } },
    tooltip: { trigger: 'axis', formatter: (p) => `${p[0].name}<br/>小区数: <b>${p[0].value}</b> 个` },
    xAxis: { type: 'category', data: names, axisLabel: { fontSize: 11, rotate: 20 } },
    yAxis: { type: 'value', name: '小区数量', minInterval: 1 },
    series: [{
      type: 'bar',
      data: values.map((v, i) => ({ value: v, itemStyle: { color: colors[i] } })),
      barWidth: '45%',
      label: { show: true, position: 'top', formatter: '{c}', fontSize: 11, fontWeight: 700 },
    }],
    grid: { left: 50, right: 20, bottom: 50, top: 55 },
  };

  const handleClick = (params) => {
    if (params.componentType === 'series') {
      setSelected(slugs[params.dataIndex]);
    }
  };

  // 按板块过滤所有房源
  const regionListings = selected
    ? listings.filter((l) => l.region === selected)
    : [];
  const regionName = selected ? (REGION_NAMES[selected] || selected) : '';

  return (
    <>
      <ReactECharts option={option} style={{ height: 280 }} onEvents={{ click: handleClick }} />
      <Modal
        title={`${regionName} — ${regionListings.length} 套房源`}
        open={!!selected}
        onCancel={() => setSelected(null)}
        footer={null}
        width={800}
        destroyOnClose
      >
        <Table
          dataSource={regionListings}
          columns={columns}
          rowKey="url"
          size="small"
          pagination={{ pageSize: 10, showTotal: (t) => `共 ${t} 套` }}
        />
      </Modal>
    </>
  );
}
