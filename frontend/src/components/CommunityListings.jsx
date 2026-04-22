import { Modal, Table } from 'antd';

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
    title: '户型',
    dataIndex: 'rooms',
    key: 'rooms',
    width: 90,
  },
  {
    title: '面积',
    dataIndex: 'area',
    key: 'area',
    width: 80,
    render: (v) => v ? `${v}㎡` : '-',
  },
  {
    title: '月租',
    dataIndex: 'price',
    key: 'price',
    width: 90,
    sorter: (a, b) => a.price - b.price,
    render: (v) => `${v?.toLocaleString()}元`,
  },
  {
    title: '单价',
    dataIndex: 'unit_price',
    key: 'unit_price',
    width: 100,
    sorter: (a, b) => (a.unit_price || 0) - (b.unit_price || 0),
    render: (v) => v ? `${v}元/㎡` : '-',
  },
  {
    title: '朝向',
    dataIndex: 'direction',
    key: 'direction',
    width: 80,
  },
];

export default function CommunityListings({ visible, community, listings, onClose }) {
  const data = listings.filter((item) => item.community === community);

  return (
    <Modal
      title={`${community} — ${data.length} 套房源`}
      open={visible}
      onCancel={onClose}
      footer={null}
      width={800}
      destroyOnClose
    >
      <Table
        dataSource={data}
        columns={columns}
        rowKey="url"
        size="small"
        pagination={{ pageSize: 10, showTotal: (t) => `共 ${t} 套` }}
      />
    </Modal>
  );
}
