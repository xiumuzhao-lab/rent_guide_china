import { useEffect, useRef, useState, useCallback } from 'react';
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

function FitBounds({ points }) {
  const map = useMap();
  const prevKey = useRef('');

  useEffect(() => {
    if (points.length === 0) return;
    const key = `${points[0].lat},${points.length}`;
    if (key === prevKey.current) return;
    prevKey.current = key;
    const bounds = L.latLngBounds(points.map((p) => [p.lat, p.lng]));
    map.fitBounds(bounds, { padding: [50, 50], maxZoom: 14 });
  }, [points, map]);

  return null;
}

function ZoomTracker({ onZoomChange }) {
  useMapEvent('zoomend', (e) => {
    onZoomChange(e.target.getZoom());
  });
  return null;
}

function CommunityLayer({ enrichedStats, minUP, maxUP, onCommunityClick, zoom }) {
  const map = useMap();
  const layerRef = useRef(null);
  const showLabels = zoom >= 13;

  useEffect(() => {
    if (layerRef.current) {
      map.removeLayer(layerRef.current);
    }

    const group = L.layerGroup();

    for (const stat of enrichedStats) {
      const color = getUnitPriceColor(stat.avgUnitPrice, minUP, maxUP);
      let marker;

      if (showLabels) {
        const label = stat.name.length > 6 ? stat.name.slice(0, 6) + '…' : stat.name;
        const icon = new L.DivIcon({
          html: `<div style="
            color:#d32f2f;
            font-size:12px;
            font-weight:700;
            white-space:nowrap;
            text-shadow:1px 1px 0 #fff,-1px 1px 0 #fff,1px -1px 0 #fff,-1px -1px 0 #fff,0 1px 0 #fff,0 -1px 0 #fff;
            cursor:pointer;
            line-height:1.4;
          ">${label} ${stat.avgUnitPrice}元/㎡</div>`,
          iconSize: [0, 0],
          iconAnchor: [0, 0],
          className: '',
        });
        marker = L.marker([stat.lat, stat.lng], { icon }).addTo(group);
      } else {
        const icon = new L.DivIcon({
          html: `<div style="
            width:10px;height:10px;border-radius:50%;
            background:${color};border:1.5px solid #fff;
            box-shadow:0 0 3px rgba(0,0,0,0.3);
            cursor:pointer;
          "></div>`,
          iconSize: [10, 10],
          iconAnchor: [5, 5],
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
  }, [map, enrichedStats, minUP, maxUP, onCommunityClick, showLabels]);

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
        zoom={13}
        style={{ height: 600, width: '100%', borderRadius: 8 }}
      >
        <FitBounds
          points={[
            { lat: workplace.lat, lng: workplace.lng },
            ...enrichedStats,
          ]}
        />
        <ZoomTracker onZoomChange={handleZoomChange} />
        <TileLayer
          attribution='&copy; 高德地图'
          url="https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}"
          subdomains={['1', '2', '3', '4']}
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
        {zoom < 13 ? '放大地图可查看小区名称和单价' : `共 ${enrichedStats.length} 个小区，点击可查看房源明细`}
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
