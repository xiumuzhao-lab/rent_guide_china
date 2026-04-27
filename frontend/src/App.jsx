import './App.css';
import { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import { Layout, Typography, Spin, Slider, message, Alert, Tabs } from 'antd';
import html2canvas from 'html2canvas';
import WorkplaceSelector from './components/WorkplaceSelector';
import OverviewCards from './components/OverviewCards';
import CommunityMap from './components/CommunityMap';
import PriceHistogram from './components/PriceHistogram';
import RoomsBarChart from './components/RoomsBarChart';
import RentTypePie from './components/TopRegionsBar';
import PriceVsArea from './components/PriceVsArea';
import AdSlot from './components/AdSlot';
import TopByRing from './components/TopByRing';
import HeatmapCanvas from './components/HeatmapCanvas';
import AnalysisReport from './components/AnalysisReport';
import SmartPicks from './components/SmartPicks';
import RegionDistanceText from './components/RegionDistanceText';
import { WORKPLACES } from './utils/constants';
import useIsMobile from './hooks/useIsMobile';
import { buildCommunityStats, enrichStatsWithDistance, getOverview } from './utils/stats';
import { haversine } from './utils/haversine';
import { generateAnalysis } from './utils/analysis';

const { Header, Content, Footer } = Layout;
const { Title, Text, Paragraph } = Typography;

/** 从 URL search params 解析初始工作地点和距离 */
function readURLParams() {
  const p = new URLSearchParams(window.location.search);
  const wp = p.get('wp');
  const dist = parseInt(p.get('dist'), 10);
  const loc = p.get('loc');
  const result = {};
  if (wp) {
    const decoded = decodeURIComponent(wp);
    // 先按名称匹配预设工作地点
    const preset = WORKPLACES.find((w) => w.name === decoded || w.key === decoded);
    if (preset) {
      result.workplace = preset;
    } else if (loc) {
      // 自定义地点: 从 loc 参数解析坐标
      const parts = loc.split(',');
      const lat = parseFloat(parts[0]);
      const lng = parseFloat(parts[1]);
      if (!isNaN(lat) && !isNaN(lng)) {
        result.workplace = { key: 'custom', name: decoded, lat, lng, address: '' };
      }
    }
  }
  if (!isNaN(dist) && dist >= 3 && dist <= 30) result.maxDistance = dist;
  return result;
}

/** 将工作地点和距离写入 URL */
function writeURLParams(workplace, maxDistance) {
  const p = new URLSearchParams();
  p.set('wp', workplace.name);
  if (workplace.key === 'custom') {
    p.set('loc', `${workplace.lat},${workplace.lng}`);
  }
  p.set('dist', maxDistance);
  const qs = p.toString();
  const url = window.location.pathname + (qs ? `?${qs}` : '');
  window.history.replaceState(null, '', url);
}

export default function App() {
  const [listings, setListings] = useState([]);
  const [geoCache, setGeoCache] = useState({});
  const [loading, setLoading] = useState(true);
  const isMobile = useIsMobile();
  const regionSectionRef = useRef(null);
  const mainContentRef = useRef(null);

  // 从 URL 或 localStorage 初始化
  const initial = useMemo(() => readURLParams(), []);
  const hasURLWorkplace = !!initial.workplace;
  const savedWorkplace = useMemo(() => {
    if (hasURLWorkplace) return null;
    try {
      const s = localStorage.getItem('rent_radar_workplace');
      if (s) {
        const parsed = JSON.parse(s);
        const preset = WORKPLACES.find((w) => w.key === parsed.key && w.key !== 'custom');
        if (preset) return preset;
        if (parsed.key === 'custom' && parsed.lat && parsed.lng) return parsed;
      }
    } catch { /* ignore */ }
    return null;
  }, [hasURLWorkplace]);
  const [workplace, setWorkplace] = useState(initial.workplace || savedWorkplace || WORKPLACES[0]);
  const [maxDistance, setMaxDistance] = useState(initial.maxDistance || 3);

  // 记住用户选择的工作地
  useEffect(() => {
    try { localStorage.setItem('rent_radar_workplace', JSON.stringify(workplace)); } catch { /* ignore */ }
  }, [workplace]);

  // 无 URL 参数且无 localStorage 记录时，用 IP 定位匹配最近工作地
  useEffect(() => {
    if (hasURLWorkplace || savedWorkplace) return;
    const proxyBase = window.location.hostname === 'localhost'
      ? '' : 'http://123.57.210.21:8900';
    fetch(`${proxyBase}/api/ip-location`)
      .then((r) => r.json())
      .then((data) => {
        if (data.status === 0 && data.result?.location) {
          const { lat, lng } = data.result.location;
          if (lat < 30.7 || lat > 31.9 || lng < 120.8 || lng > 122.0) return;
          let nearest = WORKPLACES[0];
          let minDist = Infinity;
          for (const wp of WORKPLACES) {
            const d = haversine(lat, lng, wp.lat, wp.lng);
            if (d < minDist) { minDist = d; nearest = wp; }
          }
          setWorkplace(nearest);
        }
      })
      .catch(() => { /* IP 定位失败，保持默认 */ });
  }, [hasURLWorkplace, savedWorkplace]);

  // state 变化时同步回 URL
  useEffect(() => { writeURLParams(workplace, maxDistance); }, [workplace, maxDistance]);

  useEffect(() => {
    async function loadData() {
      try {
        const [listingsRes, geoRes] = await Promise.all([
          fetch(`${import.meta.env.BASE_URL}data/listings.json`),
          fetch(`${import.meta.env.BASE_URL}data/geo_cache.json`),
        ]);
        if (!listingsRes.ok) throw new Error('listings.json not found');
        const data = await listingsRes.json();
        setListings(data);
        if (geoRes.ok) {
          const geo = await geoRes.json();
          setGeoCache(geo);
        }
      } catch (e) {
        message.error(`数据加载失败: ${e.message}`);
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, []);

  const communityStats = useMemo(() => buildCommunityStats(listings), [listings]);

  const enrichedStats = useMemo(
    () => enrichStatsWithDistance(communityStats, workplace, geoCache, maxDistance),
    [communityStats, workplace, geoCache, maxDistance],
  );

  const overview = useMemo(() => getOverview(listings), [listings]);

  const filteredListings = useMemo(() => {
    const communityNames = new Set(enrichedStats.map((s) => s.name));
    return listings.filter((l) => communityNames.has((l.community || '').trim()));
  }, [listings, enrichedStats]);

  const rangeOverview = useMemo(() => getOverview(filteredListings), [filteredListings]);

  const analysisListings = useMemo(() => {
    const rangeNames = new Set(
      enrichedStats.filter((s) => s.dist <= maxDistance).map((s) => s.name),
    );
    return listings.filter((l) => rangeNames.has((l.community || '').trim()));
  }, [listings, enrichedStats, maxDistance]);

  const topRegions = useMemo(() => {
    const regionCommunities = {};
    for (const s of enrichedStats) {
      if (s.dist > maxDistance) continue;
      const r = s.region;
      if (r) regionCommunities[r] = (regionCommunities[r] || 0) + 1;
    }
    return Object.entries(regionCommunities)
      .filter(([, count]) => count >= 5)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 6)
      .map(([r]) => r);
  }, [enrichedStats, maxDistance]);

  const analysis = useMemo(
    () => generateAnalysis({ overview, enrichedStats, filteredListings, workplace, maxDistance }),
    [overview, enrichedStats, filteredListings, workplace, maxDistance],
  );

  const handleExportRegion = useCallback(() => {
    const el = regionSectionRef.current;
    if (!el) return;
    html2canvas(el, { backgroundColor: '#fff', scale: 2 }).then((canvas) => {
      canvas.toBlob((blob) => {
        if (!blob) return;
        import('./utils/download').then(({ downloadBlob }) => {
          downloadBlob(blob, `板块分析_${workplace.name}_${maxDistance}km.png`);
        });
      }, 'image/png');
    });
  }, [workplace.name, maxDistance]);

  const handleExportAll = useCallback(() => {
    const el = mainContentRef.current;
    if (!el) return;
    html2canvas(el, { backgroundColor: '#f5f5f5', scale: 2, useCORS: true, allowTaint: true }).then((canvas) => {
      const W = canvas.width;
      const origH = canvas.height;
      const headerH = 56;
      const footerH = 36;
      const scale = W / el.offsetWidth;

      // 创建新 canvas：顶部水印 + 原图 + 底部 URL
      const out = document.createElement('canvas');
      out.width = W;
      out.height = headerH * scale + origH + footerH * scale;
      const oc = out.getContext('2d');

      // --- 顶部渐变水印栏 ---
      const grad = oc.createLinearGradient(0, 0, W, 0);
      grad.addColorStop(0, '#667eea');
      grad.addColorStop(1, '#764ba2');
      oc.fillStyle = grad;
      oc.fillRect(0, 0, W, headerH * scale);

      oc.textBaseline = 'middle';

      // Logo 图标（小房子形状）
      const iconX = Math.round(16 * scale);
      const iconY = Math.round(headerH * scale / 2);
      const iconR = Math.round(8 * scale);
      oc.fillStyle = '#fff';
      // 三角形屋顶
      oc.beginPath();
      oc.moveTo(iconX, iconY - iconR);
      oc.lineTo(iconX - iconR, iconY);
      oc.lineTo(iconX + iconR, iconY);
      oc.closePath();
      oc.fill();
      // 方形屋身
      oc.fillRect(iconX - iconR * 0.7, iconY, iconR * 1.4, iconR * 0.9);

      // 站点名称
      oc.fillStyle = '#fff';
      oc.font = `bold ${Math.round(15 * scale)}px sans-serif`;
      const titleX = Math.round(34 * scale);
      const titleW = oc.measureText('租房雷达').width;
      oc.fillText('租房雷达', titleX, iconY);

      // 副标题 / slogan（在标题下方）
      oc.fillStyle = 'rgba(255,255,255,0.7)';
      oc.font = `${Math.round(10 * scale)}px sans-serif`;
      oc.fillText('上海租房数据可视化', titleX, iconY + Math.round(14 * scale));

      // 工作地点 + 通勤范围（右对齐）
      const rightText = `${workplace.name}周边${maxDistance}km租房分析`;
      oc.fillStyle = 'rgba(255,255,255,0.85)';
      oc.font = `${Math.round(12 * scale)}px sans-serif`;
      const rightW = oc.measureText(rightText).width;
      oc.fillText(rightText, W - rightW - Math.round(16 * scale), iconY);

      // --- 原图 ---
      oc.drawImage(canvas, 0, headerH * scale);

      // --- 底部 URL 栏 ---
      oc.fillStyle = '#fff';
      oc.fillRect(0, headerH * scale + origH, W, footerH * scale);

      oc.fillStyle = '#e0e0e0';
      oc.fillRect(0, headerH * scale + origH, W, 1 * scale);

      const footY = headerH * scale + origH + Math.round(footerH * scale / 2);
      oc.fillStyle = '#999';
      oc.font = `${Math.round(11 * scale)}px sans-serif`;
      const params = new URLSearchParams({ wp: workplace.name, dist: maxDistance });
      const url = `https://rent.scoreless.top/?${params.toString()}`;
      const urlText = url.length > 80 ? url.slice(0, 77) + '...' : url;
      const urlW = oc.measureText(urlText).width;
      oc.fillText(urlText, Math.round(16 * scale), footY);
      oc.fillText(new Date().toLocaleDateString('zh-CN'), W - urlW - Math.round(16 * scale), footY);

      out.toBlob((blob) => {
        if (!blob) return;
        import('./utils/download').then(({ downloadBlob }) => {
          downloadBlob(blob, `租房雷达_${workplace.name}_${maxDistance}km_${new Date().toISOString().slice(0, 10)}.png`);
        });
      }, 'image/png');
    });
  }, [workplace.name, maxDistance]);

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
        <Spin size="large" tip="加载数据中..." />
      </div>
    );
  }

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Header component="header" role="banner" style={{ background: '#fff', borderBottom: '1px solid #f0f0f0', padding: isMobile ? '10px 12px' : '0 24px', display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', height: isMobile ? 'auto' : 64, gap: isMobile ? 8 : 0 }}>
        <a href="https://rent.scoreless.top" style={{ display: 'flex', alignItems: 'center', gap: 8, textDecoration: 'none', color: 'inherit' }}>
          <img src={`${import.meta.env.BASE_URL}favicon.svg`} alt="" width={28} height={28} />
          <Title level={1} style={{ margin: 0, fontSize: isMobile ? 16 : 20, fontWeight: 700 }}>租房雷达</Title>
        </a>
        <div style={{ display: 'flex', alignItems: 'center', gap: isMobile ? 8 : 16, flexWrap: 'wrap', width: isMobile ? '100%' : 'auto' }}>
          <WorkplaceSelector value={workplace} onChange={setWorkplace} />
          <div style={{ width: isMobile ? '100%' : 160, flexShrink: 0 }}>
            <Slider min={3} max={30} value={maxDistance} onChange={setMaxDistance} step={1} marks={{ 3: '3km', 15: '15km', 30: '30km' }} />
          </div>
          <button onClick={handleExportAll} style={{
            background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
            color: '#fff', border: 'none', borderRadius: 8,
            padding: isMobile ? '6px 12px' : '7px 16px',
            cursor: 'pointer', fontSize: 13, fontWeight: 600,
            whiteSpace: 'nowrap', boxShadow: '0 2px 8px rgba(102,126,234,0.35)',
          }}>
            一键导出
          </button>
        </div>
      </Header>
      <Content component="main" style={{ padding: isMobile ? 10 : 24, background: '#f5f5f5' }}>
        <div ref={mainContentRef} style={{ display: 'flex', flexDirection: 'column', gap: isMobile ? 12 : 24, maxWidth: 1400, margin: '0 auto' }}>
          <OverviewCards overview={rangeOverview} />



          <AdSlot slot="SLOT_TOP" format="horizontal" />

          {/* 板块分析（含导出） */}
          <section ref={regionSectionRef} aria-label="板块分析" style={{ background: '#fff', padding: 16, borderRadius: 8 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
              <Title level={2} style={{ margin: 0 }}>板块分析（{maxDistance}km 以内）</Title>
              <button onClick={handleExportRegion} style={{
                background: '#fff', border: '1px solid #d9d9d9', borderRadius: 6,
                padding: isMobile ? '4px 8px' : '2px 10px', cursor: 'pointer',
                fontSize: isMobile ? 11 : 12, color: '#666', whiteSpace: 'nowrap',
              }}>
                导出图片
              </button>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr', gap: isMobile ? 10 : 16, marginTop: 12 }}>
              <div>
                <RentTypePie data={analysisListings} enrichedStats={enrichedStats} listings={filteredListings} />
                <div style={{ fontSize: 11, color: '#999', marginTop: -8, marginBottom: 8 }}>数据口径: {maxDistance}km 内命中板块 Top 8 单价中位数, 点击柱子查看房源</div>
              </div>
              <div>
                <RoomsBarChart data={analysisListings} topRegions={topRegions} />
                <div style={{ fontSize: 11, color: '#999', marginTop: -8, marginBottom: 8 }}>数据口径: {maxDistance}km 内房源按板块统计各户型数量</div>
              </div>
              <div>
                <PriceHistogram data={analysisListings} topRegions={topRegions} />
                <div style={{ fontSize: 11, color: '#999', marginTop: -8, marginBottom: 8 }}>数据口径: {maxDistance}km 内 {analysisListings.length} 套房源月租金分布, 红线为均价</div>
              </div>
              <div>
                <PriceVsArea data={analysisListings} topRegions={topRegions} />
                <div style={{ fontSize: 11, color: '#999', marginTop: -8, marginBottom: 8 }}>数据口径: {maxDistance}km 内房源面积与月租金关系, 帮助判断性价比</div>
              </div>
            </div>
            <div style={{ marginTop: 12 }}>
              <RegionDistanceText enrichedStats={enrichedStats} maxDistance={maxDistance} workplace={workplace} />
            </div>
          </section>

          <SmartPicks enrichedStats={enrichedStats} listings={listings} workplace={workplace} isMobile={isMobile} />

          <section aria-label="单价热力图" style={{ background: '#fff', padding: 16, borderRadius: 8 }}>
            <Title level={2}>{workplace.name} 全景单价热力图</Title>
            <div style={{ fontSize: 12, color: '#999', marginBottom: 8 }}>红色标注为各距离环内单价最低前20%小区，散点颜色由绿到红反映单价从高到低，距离环标注通勤范围</div>
            <HeatmapCanvas workplace={workplace} enrichedStats={enrichedStats} maxDistance={maxDistance} />
          </section>

          <AdSlot slot="SLOT_MIDDLE" format="horizontal" />

          <section aria-label="性价比排行" style={{ background: '#fff', padding: 16, borderRadius: 8 }}>
            <Title level={2}>各距离环性价比排行</Title>
            <TopByRing enrichedStats={enrichedStats} listings={listings} />
          </section>

          <section aria-label="租房地图" style={{ background: '#fff', padding: 16, borderRadius: 8 }}>
            <Title level={2}>{workplace.name} 周边 {maxDistance}km 租房单价地图 ({enrichedStats.length} 个小区)</Title>
            <CommunityMap workplace={workplace} enrichedStats={enrichedStats} maxDistance={maxDistance} listings={listings} />
          </section>

          <AdSlot slot="SLOT_BOTTOM" format="auto" />
        </div>
      </Content>
      <Footer component="footer" role="contentinfo" style={{
        background: '#fff',
        borderTop: '1px solid #f0f0f0',
        padding: '24px 48px',
        textAlign: 'center',
      }}>
        <div style={{ maxWidth: 900, margin: '0 auto' }}>
          <Paragraph type="secondary" style={{ fontSize: 12, marginBottom: 8 }}>
            <strong>免责声明</strong>
          </Paragraph>
          <Paragraph type="secondary" style={{ fontSize: 12, marginBottom: 4 }}>
            1. 本站所有数据均基于公开信息进行统计分析，仅供个人参考与学习研究使用，不构成任何租房、投资或交易建议。
          </Paragraph>
          <Paragraph type="secondary" style={{ fontSize: 12, marginBottom: 4 }}>
            2. 所展示的数据可能存在滞后、偏差或错误，请以各平台实时信息为准。
          </Paragraph>
          <Paragraph type="secondary" style={{ fontSize: 12, marginBottom: 4 }}>
            3. 本站通过广告收入维持运营，广告内容不代表本站立场。用户在参考本站信息做出任何决策前，应自行核实并承担相关风险。
          </Paragraph>
          <Paragraph type="secondary" style={{ fontSize: 12, marginBottom: 4 }}>
            4. 如您认为本站内容侵犯了您的合法权益，请及时联系我们，我们将在核实后尽快处理。
          </Paragraph>
          <Paragraph type="secondary" style={{ fontSize: 12, marginTop: 12, marginBottom: 0 }}>
            &copy; {new Date().getFullYear()} 租房数据分析 · 数据仅供参考
          </Paragraph>
        </div>
      </Footer>
    </Layout>
  );
}
