import { Select, InputNumber, Space } from 'antd';
import { EnvironmentOutlined } from '@ant-design/icons';
import { WORKPLACES } from '../utils/constants';

export default function WorkplaceSelector({ value, onChange }) {
  const handleSelect = (key) => {
    if (key === 'custom') return;
    const wp = WORKPLACES.find((w) => w.key === key);
    if (wp) onChange(wp);
  };

  const handleCustomLat = (lat) => {
    if (lat != null) {
      onChange({ ...value, key: 'custom', name: `自定义 (${lat}, ${value.lng})`, lat });
    }
  };

  const handleCustomLng = (lng) => {
    if (lng != null) {
      onChange({ ...value, key: 'custom', name: `(${value.lat}, ${lng})`, lng });
    }
  };

  return (
    <Space>
      <EnvironmentOutlined style={{ color: '#e74c3c', fontSize: 18 }} />
      <Select
        value={value.key}
        onChange={handleSelect}
        style={{ width: 180 }}
        options={[
          ...WORKPLACES.map((wp) => ({ value: wp.key, label: wp.name })),
          { value: 'custom', label: '自定义坐标' },
        ]}
      />
      {value.key === 'custom' && (
        <>
          <InputNumber
            placeholder="纬度"
            step={0.001}
            value={value.lat}
            onChange={handleCustomLat}
            style={{ width: 120 }}
          />
          <InputNumber
            placeholder="经度"
            step={0.001}
            value={value.lng}
            onChange={handleCustomLng}
            style={{ width: 120 }}
          />
        </>
      )}
    </Space>
  );
}
