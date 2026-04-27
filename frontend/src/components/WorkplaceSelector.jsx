import { AutoComplete, InputNumber, Space } from 'antd';
import { EnvironmentOutlined } from '@ant-design/icons';
import { useState, useRef, useCallback } from 'react';
import { WORKPLACES } from '../utils/constants';
import useIsMobile from '../hooks/useIsMobile';

const CUSTOM_KEY = '__custom__';

const defaultOptions = WORKPLACES.map((wp) => ({ value: wp.key, label: wp.name, isPreset: true }));

export default function WorkplaceSelector({ value, onChange }) {
  const isMobile = useIsMobile();
  const [options, setOptions] = useState(defaultOptions);
  const [text, setText] = useState('');
  const [editing, setEditing] = useState(false);
  const timerRef = useRef(null);

  const searchTmap = useCallback(async (keyword) => {
    // 生产环境用远程代理, 开发环境用 Vite 代理
    const proxyBase = window.location.hostname === 'localhost'
      ? '' : 'https://123.57.210.21';
    try {
      const res = await fetch(`${proxyBase}/api/tmap?keyword=${encodeURIComponent(keyword)}`);
      if (!res.ok) throw new Error(res.statusText);
      const json = await res.json();
      if (json.status === 0 && json.data?.length) {
        const tmapOpts = json.data.map((item) => ({
          value: `tmap_${item.id}`,
          label: `${item.title}（${item.address || item.district || ''}）`,
          lat: item.location?.lat,
          lng: item.location?.lng,
          isPreset: false,
        }));
        setOptions(tmapOpts);
        return;
      }
    } catch {
      // fallback
    }
    setOptions(defaultOptions);
  }, []);

  const handleSearch = (val) => {
    setText(val);
    setOptions(defaultOptions);
    if (timerRef.current) clearTimeout(timerRef.current);
    if (val.trim().length >= 2) {
      timerRef.current = setTimeout(() => searchTmap(val.trim()), 400);
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

  const acProps = {
    value: displayText,
    options,
    onSelect: handleSelect,
    onSearch: handleSearch,
    onChange: (val) => setText(val),
    onFocus: () => setEditing(true),
    onBlur: () => setEditing(false),
    placeholder: '输入工作地点，搜索周边租房',
    filterOption: (input, option) => {
      if (!option?.label) return false;
      if (!option.isPreset) return true;
      return option.label.toLowerCase().includes(input.toLowerCase());
    },
  };

  if (isMobile) {
    return (
      <div style={{ width: '100%' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 13, color: '#555', whiteSpace: 'nowrap', fontWeight: 500, flexShrink: 0 }}>工作地</span>
          <AutoComplete {...acProps} style={{ flex: 1, minWidth: 0 }} />
        </div>
        {isCustom && (
          <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
            <InputNumber placeholder="纬度" step={0.001} value={value.lat} onChange={handleCustomLat} style={{ flex: 1 }} />
            <InputNumber placeholder="经度" step={0.001} value={value.lng} onChange={handleCustomLng} style={{ flex: 1 }} />
          </div>
        )}
      </div>
    );
  }

  return (
    <Space wrap>
      <EnvironmentOutlined style={{ color: '#e74c3c', fontSize: 18 }} />
      <span style={{ fontSize: 13, color: '#555', whiteSpace: 'nowrap', fontWeight: 500 }}>工作地</span>
      <AutoComplete {...acProps} style={{ width: 260 }} />
      {isCustom && (
        <>
          <InputNumber placeholder="纬度" step={0.001} value={value.lat} onChange={handleCustomLat} style={{ width: 110 }} />
          <InputNumber placeholder="经度" step={0.001} value={value.lng} onChange={handleCustomLng} style={{ width: 110 }} />
        </>
      )}
    </Space>
  );
}
