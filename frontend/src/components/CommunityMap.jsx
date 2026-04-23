import { useEffect, useRef, useState, useCallback, useMemo } from 'react';
import { MapContainer, TileLayer, Circle, Marker, Tooltip, useMap, useMapEvent } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { DISTANCE_RINGS, RING_COLORS } from '../utils/constants';
import CommunityListings from './CommunityListings';

const workplaceIcon = new L.DivIcon({
  html: '<div style="color:#e74c3c;font-size:28px;text-shadow:0 0 3px white,0 0 3px white"><b>★</b></div>',
  iconSize: [30, 30],
  iconAnchor: [15, 28],
  className: '',
});

function getUnitPriceColor(unitPrice, min, max) {
  if (max === min) return '#f39c12';
  const ratio = (unitPrice - min) / (max - min);
  const r = Math.round(ratio * 220);
  const g = Math.round((1 - ratio) * 180);
  return `rgb(${r}, ${g}, 50)`;
}

function SetInitialView({ workplace }) {
  const map = useMap();
  const prevKey = useRef('');

  useEffect(() => {
    const key = `${workplace.lat},${workplace.lng}`;
    if (key === prevKey.current) return;
    prevKey.current = key;
    const R = 1.5 / 111.32;
    const cosLat = Math.cos((workplace.lat * Math.PI) / 180);
    const bounds = L.latLngBounds([
      [workplace.lat - R, workplace.lng - R / cosLat],
      [workplace.lat + R, workplace.lng + R / cosLat],
    ]);
    map.fitBounds(bounds, { padding: [40, 40] });
  }, [map, workplace]);

  return null;
}

function ZoomTracker({ onZoomChange }) {
  useMapEvent('zoomend', (e) => {
    onZoomChange(e.target.getZoom());
  });
  return null;
}

/**
 * 按网格去重: 将地图按像素网格分格，每格随机选一个小区显示文字标签.
 * 缩放越大，同一地理区域占的像素越多，自然能显示更多标签.
 * 每次缩放变化时随机种子不同，用户能看到不同的小区名.
 */
function pickLabelStats(enrichedStats, zoom) {
  // 格子很大: 缩小时只显示约 1/10，放大后格子相对变小自然显示更多
  const cellSize = zoom >= 16 ? 60 : zoom >= 15 ? 250 : zoom >= 14 ? 450 : 800;
  const grid = new Map();

  const seed = zoom * 7 + 13;
  const rand = (i) => ((seed * (i + 1) * 2654435761) >>> 0) / 4294967296;

  for (let i = 0; i < enrichedStats.length; i++) {
    const stat = enrichedStats[i];
    const key = `${Math.round(stat.lat * cellSize * 100) / (cellSize * 100)}_${Math.round(stat.lng * cellSize * 100) / (cellSize * 100)}`;
    const existing = grid.get(key);
    if (!existing) {
      grid.set(key, { stat, score: rand(i) });
    } else {
      const newScore = rand(i);
      if (newScore < existing.score) {
        grid.set(key, { stat, score: newScore });
      }
    }
  }

  const labelSet = new Set();
  for (const { stat } of grid.values()) {
    labelSet.add(stat.name);
  }
  return labelSet;
}

function CommunityLayer({ enrichedStats, minUP, maxUP, onCommunityClick, zoom }) {
  const map = useMap();
  const layerRef = useRef(null);

  const labelSet = useMemo(
    () => pickLabelStats(enrichedStats, zoom),
    [enrichedStats, zoom],
  );

  // 按距离环分组，每组前 10% 低单价标为红色
  const topStats = useMemo(() => {
    const rings = [3, 5, 8, 10, 15];
    const topSet = new Set();
    let prev = 0;
    for (const r of rings) {
      const group = enrichedStats.filter((s) => s.dist > prev && s.dist <= r);
      const sorted = [...group].sort((a, b) => a.avgUnitPrice - b.avgUnitPrice);
      const cut = Math.max(1, Math.ceil(sorted.length * 0.1));
      for (let i = 0; i < cut && i < sorted.length; i++) {
        topSet.add(sorted[i].name);
      }
      prev = r;
    }
    return topSet;
  }, [enrichedStats]);

  useEffect(() => {
    if (layerRef.current) {
      map.removeLayer(layerRef.current);
    }

    const group = L.layerGroup();

    for (const stat of enrichedStats) {
      const color = getUnitPriceColor(stat.avgUnitPrice, minUP, maxUP);
      const showLabel = labelSet.has(stat.name);
      const isTopValue = topStats.has(stat.name);
      const dotSize = isTopValue ? 14 : 7;
      const dotBg = isTopValue ? '#e74c3c' : color;
      const dotBorder = isTopValue ? '2.5px solid #fff' : '1.5px solid #fff';
      const dotShadow = isTopValue ? '0 0 8px rgba(231,76,60,0.7)' : '0 0 2px rgba(0,0,0,0.25)';
      let marker;

      if (showLabel) {
        const label = stat.name.length > 6 ? stat.name.slice(0, 6) + '…' : stat.name;
        const icon = new L.DivIcon({
          html: `<div style="
            display:flex;align-items:center;gap:3px;
            cursor:pointer;
          "><div style="
            width:${dotSize}px;height:${dotSize}px;border-radius:50%;flex-shrink:0;
            background:${dotBg};border:${dotBorder};
            box-shadow:${dotShadow};
          "></div><span style="
            color:${isTopValue ? '#c0392b' : '#666'};font-size:11px;font-weight:${isTopValue ? 700 : 600};white-space:nowrap;
            text-shadow:1px 1px 0 #fff,-1px 1px 0 #fff,1px -1px 0 #fff,-1px -1px 0 #fff;
            line-height:1.3;
          ">${label}</span><span style="
            color:${isTopValue ? '#c0392b' : color};font-size:11px;font-weight:700;white-space:nowrap;
            text-shadow:1px 1px 0 #fff,-1px 1px 0 #fff;
          ">${stat.avgUnitPrice}元</span></div>`,
          iconSize: [0, 0],
          iconAnchor: [-4, 6],
          className: '',
        });
        marker = L.marker([stat.lat, stat.lng], { icon }).addTo(group);
      } else {
        const icon = new L.DivIcon({
          html: `<div style="
            width:${dotSize}px;height:${dotSize}px;border-radius:50%;
            background:${dotBg};border:${dotBorder};
            box-shadow:${dotShadow};
            cursor:pointer;
          "></div>`,
          iconSize: [dotSize, dotSize],
          iconAnchor: [dotSize / 2, dotSize / 2],
          className: '',
        });
        marker = L.marker([stat.lat, stat.lng], { icon }).addTo(group);
      }

      marker.bindTooltip(
        `<div style="font-size:12px;line-height:1.6">
          <b>${stat.name}</b><br/>
          距离: ${stat.dist}km | 房源: ${stat.count}套<br/>
          均价: ${stat.avgPrice.toLocaleString()}元/月 | 单价: ${stat.avgUnitPrice}元/㎡/月<br/>
          均面积: ${stat.avgArea}㎡
        </div>`,
        { direction: 'top', offset: [0, -5] },
      );
      marker.on('click', () => onCommunityClick(stat.name));
    }

    group.addTo(map);
    layerRef.current = group;

    return () => {
      if (layerRef.current) {
        map.removeLayer(layerRef.current);
        layerRef.current = null;
      }
    };
  }, [map, enrichedStats, minUP, maxUP, onCommunityClick, labelSet]);

  return null;
}

export default function CommunityMap({ workplace, enrichedStats, maxDistance, listings }) {
  const [selected, setSelected] = useState(null);
  const [zoom, setZoom] = useState(13);
  const handleZoomChange = useCallback((z) => setZoom(z), []);

  if (!workplace || enrichedStats.length === 0) return null;

  const unitPrices = enrichedStats.map((s) => s.avgUnitPrice).filter(Boolean);
  const minUP = Math.min(...unitPrices);
  const maxUP = Math.max(...unitPrices);

  const visibleRings = DISTANCE_RINGS.filter((r) => r <= maxDistance);

  return (
    <>
      <MapContainer
        center={[workplace.lat, workplace.lng]}
        zoom={25}
        minZoom={11}
        style={{ height: 700, width: '100%', borderRadius: 8 }}
      >
        <SetInitialView workplace={workplace} />
        <ZoomTracker onZoomChange={handleZoomChange} />
        <TileLayer
          attribution='&copy; 高德地图'
          url="https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}"
          subdomains={['1', '2', '3', '4']}
        />

        {/* 距离环 */}
        {visibleRings.map((rKm) => {
          const ringColor = RING_COLORS[rKm] || '#95a5a6';
          const points = 64;
          const ringLatLngs = [];
          for (let i = 0; i <= points; i++) {
            const angle = (2 * Math.PI * i) / points;
            const d = (rKm * 1000) / 6371000;
            const lat1 = (workplace.lat * Math.PI) / 180;
            const lng1 = (workplace.lng * Math.PI) / 180;
            const lat2 = Math.asin(Math.sin(lat1) * Math.cos(d) + Math.cos(lat1) * Math.sin(d) * Math.cos(angle));
            const lng2 = lng1 + Math.atan2(
              Math.sin(angle) * Math.sin(d) * Math.cos(lat1),
              Math.cos(d) - Math.sin(lat1) * Math.sin(lat2),
            );
            ringLatLngs.push([(lat2 * 180) / Math.PI, (lng2 * 180) / Math.PI]);
          }
          const labelIdx = Math.floor(points * 0.75);
          const labelPos = ringLatLngs[labelIdx];
          return (
            <g key={rKm}>
              <Circle
                center={[workplace.lat, workplace.lng]}
                radius={rKm * 1000}
                pathOptions={{
                  color: ringColor,
                  fillColor: ringColor,
                  weight: 2.5,
                  opacity: 0.6,
                  fillOpacity: 0.04,
                }}
              />
              <Marker
                position={labelPos}
                icon={new L.DivIcon({
                  html: `<div style="
                    background:${ringColor};
                    color:#fff;
                    padding:3px 12px;
                    border-radius:12px;
                    font-size:14px;
                    font-weight:800;
                    letter-spacing:1px;
                    white-space:nowrap;
                    box-shadow:0 1px 4px ${ringColor}88;
                    border:2px solid #fff;
                  ">${rKm} km</div>`,
                  iconSize: [0, 0],
                  iconAnchor: [0, 12],
                  className: '',
                })}
                interactive={false}
              />
            </g>
          );
        })}

        {/* 工作地点 */}
        <Marker position={[workplace.lat, workplace.lng]} icon={workplaceIcon}>
          <Tooltip permanent direction="bottom" offset={[0, 10]}>
            <b>{workplace.name}</b>
          </Tooltip>
        </Marker>

        {/* 小区标注 */}
        <CommunityLayer
          enrichedStats={enrichedStats}
          minUP={minUP}
          maxUP={maxUP}
          onCommunityClick={setSelected}
          zoom={zoom}
        />
      </MapContainer>

      <div style={{ fontSize: 12, color: '#999', marginTop: 4 }}>
        滚轮缩放查看更多小区 · 放大地图显示更多标签 · 悬停查看详情 · 点击查看房源 · 共 {enrichedStats.length} 个小区
      </div>

      <CommunityListings
        visible={!!selected}
        community={selected}
        listings={listings}
        onClose={() => setSelected(null)}
      />
    </>
  );
}
