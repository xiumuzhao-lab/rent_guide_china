import { AutoComplete, InputNumber, Space } from 'antd';
import { EnvironmentOutlined } from '@ant-design/icons';
import { useState, useRef, useCallback } from 'react';
import { WORKPLACES } from '../utils/constants';

const CUSTOM_KEY = '__custom__';

const defaultOptions = WORKPLACES.map((wp) => ({ value: wp.key, label: wp.name, isPreset: true }));

export default function WorkplaceSelector({ value, onChange }) {
  const [options, setOptions] = useState(defaultOptions);
  const [text, setText] = useState('');
  const [editing, setEditing] = useState(false);
  const timerRef = useRef(null);

  const searchTmap = useCallback(async (keyword) => {
    try {
      const res = await fetch(`/api/tmap?keyword=${encodeURIComponent(keyword)}`);
      const json = await res.json();
      if (json.status === 0 && json.data?.length) {
        const tmapOpts = json.data.map((item) => ({
          value: `tmap_${item.id}`,
          label: `${item.title}（${item.address || item.district || ''}）`,
          lat: item.location?.lat,
          lng: item.location?.lng,
          isPreset: false,
        }));
        setOptions([...defaultOptions, ...tmapOpts]);
      }
    } catch {
      // 生产环境无代理时静默失败
    }
  }, []);

  const handleSearch = (val) => {
    setText(val);
    if (timerRef.current) clearTimeout(timerRef.current);
    if (val.trim().length >= 2) {
      timerRef.current = setTimeout(() => searchTmap(val.trim()), 400);
    } else {
      setOptions(defaultOptions);
    }
  };

  const handleSelect = (key) => {
    // 预定义工作地点
    const wp = WORKPLACES.find((w) => w.key === key);
    if (wp) {
      onChange(wp);
      setText('');
      setEditing(false);
      return;
    }

    // 腾讯地图搜索结果
    const opt = options.find((o) => o.value === key);
    if (opt?.lat != null) {
      onChange({
        key: 'custom',
        name: opt.label.replace(/（.*）$/, ''),
        lat: opt.lat,
        lng: opt.lng,
      });
      setText('');
      setEditing(false);
      return;
    }

    // 自定义坐标
    onChange({ ...value, key: CUSTOM_KEY, name: '自定义坐标' });
    setText('');
    setEditing(false);
  };

  const handleCustomLat = (lat) => {
    if (lat != null) {
      onChange({ ...value, key: CUSTOM_KEY, name: `自定义 (${lat}, ${value.lng})`, lat });
    }
  };

  const handleCustomLng = (lng) => {
    if (lng != null) {
      onChange({ ...value, key: CUSTOM_KEY, name: `自定义 (${value.lat}, ${lng})`, lng });
    }
  };

  const isCustom = value.key === CUSTOM_KEY;
  const displayText = editing ? text : (isCustom ? text : value.name);

  return (
    <Space>
      <EnvironmentOutlined style={{ color: '#e74c3c', fontSize: 18 }} />
      <AutoComplete
        value={displayText}
        options={options}
        onSelect={handleSelect}
        onSearch={handleSearch}
        onChange={(val) => setText(val)}
        onFocus={() => setEditing(true)}
        onBlur={() => setEditing(false)}
        placeholder="输入地名搜索或选择"
        style={{ width: 260 }}
        filterOption={(input, option) => {
          if (!option?.label) return false;
          return option.label.toLowerCase().includes(input.toLowerCase());
        }}
      />
      {isCustom && (
        <>
          <InputNumber
            placeholder="纬度"
            step={0.001}
            value={value.lat}
            onChange={handleCustomLat}
            style={{ width: 110 }}
          />
          <InputNumber
            placeholder="经度"
            step={0.001}
            value={value.lng}
            onChange={handleCustomLng}
            style={{ width: 110 }}
          />
        </>
      )}
    </Space>
  );
}
