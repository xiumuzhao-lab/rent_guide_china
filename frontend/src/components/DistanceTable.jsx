import { Table, Tag } from 'antd';
import { RING_COLORS, RING_LABELS, DISTANCE_RINGS } from '../utils/constants';

function getRingTag(dist) {
  let prev = 0;
  for (const ring of DISTANCE_RINGS) {
    if (dist <= ring) {
      const color = RING_COLORS[ring] || '#95a5a6';
      const label = RING_LABELS[ring] || `${prev}-${ring}km`;
      return { color, label };
    }
    prev = ring;
  }
  return { color: '#95a5a6', label: `${DISTANCE_RINGS[DISTANCE_RINGS.length - 1]}km+` };
}

const columns = [
  {
    title: '小区名',
    dataIndex: 'name',
    key: 'name',
    width: 200,
    ellipsis: true,
  },
  {
    title: '距离',
    dataIndex: 'dist',
    key: 'dist',
    width: 90,
    sorter: (a, b) => a.dist - b.dist,
    render: (v) => `${v} km`,
  },
  {
    title: '距离环',
    key: 'ring',
    width: 140,
    filters: DISTANCE_RINGS.map((r) => ({ text: RING_LABELS[r], value: r })),
    onFilter: (value, record) => {
      let prev = 0;
      for (const ring of DISTANCE_RINGS) {
        if (record.dist <= ring) return ring === value;
        prev = ring;
      }
      return false;
    },
    render: (_, record) => {
      const { color, label } = getRingTag(record.dist);
      return <Tag color={color}>{label}</Tag>;
    },
  },
  {
    title: '套数',
    dataIndex: 'count',
    key: 'count',
    width: 70,
    sorter: (a, b) => a.count - b.count,
  },
  {
    title: '均价',
    dataIndex: 'avgPrice',
    key: 'avgPrice',
    width: 100,
    sorter: (a, b) => a.avgPrice - b.avgPrice,
    render: (v) => `${v.toLocaleString()} 元`,
  },
  {
    title: '单价',
    dataIndex: 'avgUnitPrice',
    key: 'avgUnitPrice',
    width: 110,
    sorter: (a, b) => a.avgUnitPrice - b.avgUnitPrice,
    render: (v) => `${v} 元/㎡/月`,
  },
  {
    title: '均面积',
    dataIndex: 'avgArea',
    key: 'avgArea',
    width: 90,
    sorter: (a, b) => a.avgArea - b.avgArea,
    render: (v) => `${v} ㎡`,
  },
];

export default function DistanceTable({ enrichedStats }) {
  return (
    <Table
      dataSource={enrichedStats}
      columns={columns}
      rowKey="name"
      size="small"
      pagination={{ pageSize: 20, showSizeChanger: true, showTotal: (t) => `共 ${t} 个小区` }}
      scroll={{ y: 400 }}
    />
  );
}
