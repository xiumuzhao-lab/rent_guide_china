import { useState } from 'react';
import { Tabs, Table, Tag } from 'antd';
import { DISTANCE_RINGS, RING_COLORS, REGION_NAMES } from '../utils/constants';
import CommunityListings from './CommunityListings';

const RING_BANDS = [
  { max: DISTANCE_RINGS[0], label: `${DISTANCE_RINGS[0]}km` },
  ...DISTANCE_RINGS.slice(1).map((r, i) => ({
    min: DISTANCE_RINGS[i],
    max: r,
    label: `${DISTANCE_RINGS[i]}-${r}km`,
  })),
];

function getBandKey(band) {
  return `${band.min || 0}-${band.max}`;
}

export default function TopByRing({ enrichedStats, listings }) {
  const [selected, setSelected] = useState(null);

  const columns = [
    {
      title: '小区',
      dataIndex: 'name',
      key: 'name',
      ellipsis: true,
      width: 180,
      render: (text) => (
        <a onClick={() => setSelected(text)} style={{ cursor: 'pointer' }}>{text}</a>
      ),
    },
    {
      title: '板块',
      dataIndex: 'region',
      key: 'region',
      width: 80,
      filters: [...new Set(enrichedStats.map((s) => s.region))].filter(Boolean).map((r) => ({ text: REGION_NAMES[r] || r, value: r })),
      onFilter: (value, record) => record.region === value,
      render: (v) => REGION_NAMES[v] || v,
    },
    {
      title: '距离',
      dataIndex: 'dist',
      key: 'dist',
      width: 80,
      sorter: (a, b) => a.dist - b.dist,
      render: (v) => `${v} km`,
    },
    {
      title: '单价',
      dataIndex: 'avgUnitPrice',
      key: 'avgUnitPrice',
      width: 100,
      defaultSortOrder: 'ascend',
      sorter: (a, b) => a.avgUnitPrice - b.avgUnitPrice,
      render: (v) => <span style={{ fontWeight: 700, color: '#2ecc71' }}>{v} 元/㎡</span>,
    },
    {
      title: '均价',
      dataIndex: 'avgPrice',
      key: 'avgPrice',
      width: 90,
      sorter: (a, b) => a.avgPrice - b.avgPrice,
      render: (v) => `${v.toLocaleString()} 元`,
    },
    {
      title: '面积',
      dataIndex: 'avgArea',
      key: 'avgArea',
      width: 80,
      sorter: (a, b) => a.avgArea - b.avgArea,
      render: (v) => `${v} ㎡`,
    },
    {
      title: '套数',
      dataIndex: 'count',
      key: 'count',
      width: 60,
      sorter: (a, b) => a.count - b.count,
    },
  ];

  const items = RING_BANDS.map((band) => {
    const filtered = [...enrichedStats]
      .filter((s) => {
        if (band.min == null) return s.dist <= band.max;
        return s.dist > band.min && s.dist <= band.max;
      })
      .sort((a, b) => a.avgUnitPrice - b.avgUnitPrice);

    const color = RING_COLORS[band.max] || '#95a5a6';

    return {
      key: getBandKey(band),
      label: (
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          <Tag color={color} style={{ margin: 0, borderRadius: 4 }}>{band.label}</Tag>
          <span style={{ fontSize: 12, color: '#999' }}>{filtered.length} 个</span>
        </span>
      ),
      children: filtered.length > 0 ? (
        <div style={{ overflowX: 'auto' }}>
        <Table
          dataSource={filtered}
          columns={columns}
          rowKey="name"
          size="small"
          pagination={{ pageSize: 20, showSizeChanger: true, showTotal: (t) => `共 ${t} 个小区` }}
        />
        </div>
      ) : (
        <div style={{ textAlign: 'center', padding: 40, color: '#bbb' }}>该范围内暂无小区数据</div>
      ),
    };
  });

  return (
    <>
      <Tabs
        defaultActiveKey={getBandKey(RING_BANDS[0])}
        items={items}
        size="small"
      />
      <CommunityListings
        visible={!!selected}
        community={selected}
        listings={listings}
        onClose={() => setSelected(null)}
      />
    </>
  );
}
