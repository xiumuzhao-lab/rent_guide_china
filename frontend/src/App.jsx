import ReportPage from './components/ReportPage';
import { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import { Layout, Typography, Spin, Slider, message, Alert, Tabs, Select } from 'antd';
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
import { CITY_CONFIG, CITY_LIST } from './utils/constants';
import useIsMobile from './hooks/useIsMobile';
import { buildCommunityStats, enrichStatsWithDistance, getOverview } from './utils/stats';
import { haversine } from './utils/haversine';
import { generateAnalysis } from './utils/analysis';
import { exportDouyinPoster, generateDouyinText } from './utils/douyinPoster';

const { Header, Content, Footer } = Layout;
const { Title, Text, Paragraph } = Typography;

/** 从 URL search params 解析初始城市、工作地点和距离 */
function readURLParams() {
  const p = new URLSearchParams(window.location.search);
  const cityParam = p.get('city');
  const city = CITY_CONFIG[cityParam] ? cityParam : 'shanghai';
  const config = CITY_CONFIG[city];
  const wp = p.get('wp');
  const dist = parseInt(p.get('dist'), 10);
  const loc = p.get('loc');
  const result = { city };
  if (wp) {
    const decoded = decodeURIComponent(wp);
    const preset = config.workplaces.find((w) => w.name === decoded || w.key === decoded);
    if (preset) {
      result.workplace = preset;
    } else if (loc) {
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

/** 将城市、工作地点和距离写入 URL */
function writeURLParams(city, workplace, maxDistance) {
  const p = new URLSearchParams();
  if (city !== 'shanghai') p.set('city', city);
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

  // 从 URL 初始化
  const initial = useMemo(() => readURLParams(), []);
  const [city, setCity] = useState(initial.city);
  const cityConfig = CITY_CONFIG[city];
  const hasURLWorkplace = !!initial.workplace;
  const [workplace, setWorkplace] = useState(
    initial.workplace || CITY_CONFIG[initial.city].workplaces[0],
  );
  const [maxDistance, setMaxDistance] = useState(initial.maxDistance || 3);
  const [view, setView] = useState('main');

  // IP 定位匹配最近工作地
  const [locating, setLocating] = useState(false);
  const locateByIP = useCallback(() => {
    setLocating(true);
    const proxyBase = window.location.hostname === 'localhost'
      ? '' : 'https://server.scoreless.top';
    fetch(`${proxyBase}/api/ip-location`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((data) => {
        if (data.status !== 0) throw new Error(data.message || `status ${data.status}`);
        if (!data.result?.location) throw new Error('no location in response');
        const { lat, lng } = data.result.location;
        const b = cityConfig.bounds;
        if (lat < b.latMin || lat > b.latMax || lng < b.lngMin || lng > b.lngMax) return;
        const address = data.result.address || '';
        setWorkplace({
          key: 'custom',
          name: address || `定位位置`,
          lat,
          lng,
          address,
        });
      })
      .catch((err) => { console.error('[IP定位失败]', err.message); })
      .finally(() => setLocating(false));
  }, [cityConfig]);

  // 无 URL 参数时，自动定位
  useEffect(() => {
    if (hasURLWorkplace) return;
    locateByIP();
  }, [hasURLWorkplace, locateByIP]);

  // state 变化时同步回 URL
  useEffect(() => { writeURLParams(city, workplace, maxDistance); }, [city, workplace, maxDistance]);

  useEffect(() => {
    async function loadData() {
      setLoading(true);
      try {
        const dataPath = cityConfig.dataPath;
        const verRes = await fetch(`${import.meta.env.BASE_URL}data/${dataPath}versions.json`);
        let listingsFile = 'listings.json';
        let geoCacheFile = 'geo_cache.json';
        if (verRes.ok) {
          const ver = await verRes.json();
          listingsFile = ver.listings || listingsFile;
          geoCacheFile = ver.geo_cache || geoCacheFile;
        }
        const [listingsRes, geoRes] = await Promise.all([
          fetch(`${import.meta.env.BASE_URL}data/${dataPath}${listingsFile}`),
          fetch(`${import.meta.env.BASE_URL}data/${dataPath}${geoCacheFile}`),
        ]);
        if (!listingsRes.ok) throw new Error('listings not found');
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
  }, [city, cityConfig]);

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

  const publishedAt = useMemo(() => {
    if (!listings.length) return null;
    const times = listings.map((l) => l.scraped_at).filter(Boolean).sort();
    return times[times.length - 1];
  }, [listings]);

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


  const handleExportDouyin = useCallback(() => {
    exportDouyinPoster({ analysis, enrichedStats, workplace, maxDistance, rangeOverview, filteredListings });
    // 同时复制推荐文案到剪贴板
    const text = generateDouyinText(analysis, workplace, maxDistance, rangeOverview);
    if (text && navigator.clipboard) {
      navigator.clipboard.writeText(text).catch(() => {});
    }
  }, [analysis, enrichedStats, workplace, maxDistance, rangeOverview, filteredListings]);

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
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <a href={window.location.origin} style={{ display: 'flex', alignItems: 'center', gap: 8, textDecoration: 'none', color: 'inherit' }}>
            <img src={`${import.meta.env.BASE_URL}favicon.svg`} alt="" width={28} height={28} />
            <Title level={1} style={{ margin: 0, fontSize: isMobile ? 16 : 20, fontWeight: 700 }}>租房雷达</Title>
          </a>
          {CITY_LIST.length > 1 && (
            <Select
              value={city}
              onChange={(c) => {
                if (c === city) return;
                const cfg = CITY_CONFIG[c];
                setCity(c);
                setWorkplace(cfg.workplaces[0]);
                setMaxDistance(3);
              }}
              options={CITY_LIST.map((c) => ({ value: c, label: CITY_CONFIG[c].name }))}
              style={{ width: isMobile ? 80 : 90 }}
              size="small"
              popupMatchSelectWidth={false}
            />
          )}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: isMobile ? 8 : 16, flexWrap: 'wrap', width: isMobile ? '100%' : 'auto' }}>
          <WorkplaceSelector value={workplace} onChange={setWorkplace} workplaces={cityConfig.workplaces} />
          <div style={{ width: isMobile ? '100%' : 160, flexShrink: 0 }}>
            <Slider min={3} max={30} value={maxDistance} onChange={setMaxDistance} step={1} marks={{ 3: '3km', 15: '15km', 30: '30km' }} />
          </div>
          <button onClick={locateByIP} disabled={locating} title="定位到最近工作地" style={{
            background: locating ? '#d9d9d9' : 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
            color: '#fff', border: 'none', borderRadius: 8,
            padding: isMobile ? '6px 12px' : '7px 16px',
            cursor: locating ? 'not-allowed' : 'pointer', fontSize: 13, fontWeight: 600,
            whiteSpace: 'nowrap', boxShadow: locating ? 'none' : '0 2px 8px rgba(102,126,234,0.35)',
            display: 'inline-flex', alignItems: 'center', gap: 4,
          }}>
            <span style={{ display: 'inline-block', width: 14, height: 14, border: locating ? '2px solid #999' : '2px solid #fff', borderRadius: '50%', position: 'relative' }}>
              {!locating && <span style={{ position: 'absolute', top: 2, left: 2, width: 6, height: 6, background: '#fff', borderRadius: '50%' }} />}
            </span>
            {locating ? '定位中...' : '定位'}
          </button>
        </div>
      </Header>
      <Content component="main" style={{ padding: isMobile ? 10 : 24, background: '#f5f5f5' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: isMobile ? 12 : 24, maxWidth: 1400, margin: '0 auto' }}>
          {view === 'report' ? (
            <ReportPage
              listings={listings}
              enrichedStats={enrichedStats}
              filteredListings={filteredListings}
              workplace={workplace}
              maxDistance={maxDistance}
              overview={rangeOverview}
            />
          ) : (
            <>
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

          <SmartPicks enrichedStats={enrichedStats} listings={listings} workplace={workplace} isMobile={isMobile} city={city} />

          <section aria-label="单价热力图" style={{ background: '#fff', padding: 16, borderRadius: 8 }}>
            <Title level={2}>{workplace.name} 全景单价热力图</Title>
            <div style={{ fontSize: 12, color: '#999', marginBottom: 8 }}>红色标注为各距离环内单价最低前20%小区，散点颜色由绿到红反映单价从高到低，距离环标注通勤范围</div>
            <HeatmapCanvas workplace={workplace} enrichedStats={enrichedStats} maxDistance={maxDistance} city={city} />
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
            </>
          )}
        </div>
      </Content>
      <Footer component="footer" role="contentinfo" style={{
        background: '#fff',
        borderTop: '1px solid #f0f0f0',
        padding: '24px 48px',
        textAlign: 'center',
      }}>
        <div style={{ maxWidth: 900, margin: '0 auto' }}>
          <Paragraph type="secondary" style={{ fontSize: 12, marginBottom: 4, lineHeight: '22px' }}>
            数据源自公开信息统计分析，纯免费工具，仅供学习探索使用，不构成租房建议。如有偏差请以各平台实时信息为准。
          </Paragraph>
          <button onClick={() => setView(view === 'main' ? 'report' : 'main')} style={{
            background: 'none', border: 'none', color: '#bbb', cursor: 'pointer',
            fontSize: 12, padding: 0, textDecoration: 'underline',
          }}>
            {view === 'main' ? '传播报告' : '返回地图'}
          </button>
          <Paragraph type="secondary" style={{ fontSize: 12, marginTop: 8, marginBottom: 0 }}>
            &copy; {new Date().getFullYear()} 租房数据分析 · v{__APP_VERSION__}
          </Paragraph>
          <Paragraph type="secondary" style={{ fontSize: 12, marginTop: 4, marginBottom: 0 }}>
            <a href="https://beian.miit.gov.cn/" target="_blank" rel="noopener noreferrer" style={{ color: '#999' }}>浙ICP备2026028673号</a>
          </Paragraph>
        </div>
      </Footer>
    </Layout>
  );
}
