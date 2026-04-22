import { useEffect, useRef } from 'react';
import { MapContainer, TileLayer, Circle, CircleMarker, Popup, Marker, useMap } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { DISTANCE_RINGS, RING_COLORS } from '../utils/constants';

const workplaceIcon = new L.DivIcon({
  html: '<div style="color:#e74c3c;font-size:28px;text-shadow:0 0 3px white,0 0 3px white"><b>★</b></div>',
  iconSize: [30, 30],
  iconAnchor: [15, 28],
  className: '',
});

function FitBounds({ points }) {
  const map = useMap();
  const prevKey = useRef('');

  useEffect(() => {
    if (points.length === 0) return;
    const key = `${points[0].lat},${points.length}`;
    if (key === prevKey.current) return;
    prevKey.current = key;
    const bounds = L.latLngBounds(points.map((p) => [p.lat, p.lng]));
    map.fitBounds(bounds, { padding: [30, 30] });
  }, [points, map]);

  return null;
}

function getUnitPriceColor(unitPrice, min, max) {
  if (max === min) return '#f39c12';
  const ratio = (unitPrice - min) / (max - min);
  const r = Math.round(ratio * 220);
  const g = Math.round((1 - ratio) * 180);
  return `rgb(${r}, ${g}, 50)`;
}

export default function CommunityMap({ workplace, enrichedStats, maxDistance }) {
  if (!workplace || enrichedStats.length === 0) return null;

  const unitPrices = enrichedStats.map((s) => s.avgUnitPrice).filter(Boolean);
  const minUP = Math.min(...unitPrices);
  const maxUP = Math.max(...unitPrices);

  const visibleRings = DISTANCE_RINGS.filter((r) => r <= maxDistance);

  return (
    <MapContainer
      center={[workplace.lat, workplace.lng]}
      zoom={12}
      style={{ height: 500, width: '100%', borderRadius: 8 }}
    >
      <FitBounds
        points={[
          { lat: workplace.lat, lng: workplace.lng },
          ...enrichedStats,
        ]}
      />
      <TileLayer
        attribution='&copy; 腾讯地图'
        url="https://rt{s}.map.gtimg.com/tile?z={z}&x={x}&y={y}"
        subdomains={['0', '1', '2', '3']}
      />

      {/* 距离环 */}
      {visibleRings.map((rKm) => (
        <Circle
          key={rKm}
          center={[workplace.lat, workplace.lng]}
          radius={rKm * 1000}
          pathOptions={{
            color: RING_COLORS[rKm] || '#95a5a6',
            fillColor: 'none',
            weight: 1.5,
            dashArray: '6,4',
            fillOpacity: 0,
          }}
        />
      ))}

      {/* 工作地点 */}
      <Marker position={[workplace.lat, workplace.lng]} icon={workplaceIcon}>
        <Popup>
          <b>{workplace.name}</b>
          <br />
          {workplace.address || ''}
        </Popup>
      </Marker>

      {/* 小区散点 */}
      {enrichedStats.map((stat) => (
        <CircleMarker
          key={stat.name}
          center={[stat.lat, stat.lng]}
          radius={Math.max(5, Math.min(15, 3 + stat.count))}
          pathOptions={{
            color: getUnitPriceColor(stat.avgUnitPrice, minUP, maxUP),
            fillColor: getUnitPriceColor(stat.avgUnitPrice, minUP, maxUP),
            fillOpacity: 0.7,
            weight: 1,
          }}
        >
          <Popup>
            <b>{stat.name}</b>
            <br />
            距离: {stat.dist}km<br />
            房源: {stat.count}套 | 均{stat.avgPrice.toLocaleString()}元/月
            <br />
            单价: {stat.avgUnitPrice}元/㎡/月 | 均面积: {stat.avgArea}㎡
          </Popup>
        </CircleMarker>
      ))}
    </MapContainer>
  );
}
