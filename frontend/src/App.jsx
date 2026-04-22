import './App.css';
import { useState, useEffect, useMemo } from 'react';
import { Layout, Typography, Spin, Slider, message, Alert, Tabs } from 'antd';
import WorkplaceSelector from './components/WorkplaceSelector';
import OverviewCards from './components/OverviewCards';
import CommunityMap from './components/CommunityMap';
import PriceHistogram from './components/PriceHistogram';
import RoomsBarChart from './components/RoomsBarChart';
import RentTypePie from './components/RentTypePie';
import PriceVsArea from './components/PriceVsArea';
import AdSlot from './components/AdSlot';
import TopByRing from './components/TopByRing';
import HeatmapCanvas from './components/HeatmapCanvas';
import AnalysisReport from './components/AnalysisReport';
import { WORKPLACES } from './utils/constants';
import { buildCommunityStats, enrichStatsWithDistance, getOverview } from './utils/stats';
import { generateAnalysis } from './utils/analysis';

const { Header, Content, Footer } = Layout;
const { Title, Text, Paragraph } = Typography;

export default function App() {
  const [listings, setListings] = useState([]);
  const [geoCache, setGeoCache] = useState({});
  const [loading, setLoading] = useState(true);
  const [workplace, setWorkplace] = useState(WORKPLACES[0]);
  const [maxDistance, setMaxDistance] = useState(15);

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

  const analysis = useMemo(
    () => generateAnalysis({ overview, enrichedStats, filteredListings, workplace, maxDistance }),
    [overview, enrichedStats, filteredListings, workplace, maxDistance],
  );

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
        <Spin size="large" tip="加载数据中..." />
      </div>
    );
  }

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Header style={{ background: '#fff', borderBottom: '1px solid #f0f0f0', padding: '0 24px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', height: 64 }}>
        <Title level={4} style={{ margin: 0 }}>租房雷达 · RentRadar</Title>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <WorkplaceSelector value={workplace} onChange={setWorkplace} />
          <div style={{ width: 160, flexShrink: 0 }}>
            <Slider min={3} max={30} value={maxDistance} onChange={setMaxDistance} step={1} marks={{ 3: '3km', 15: '15km', 30: '30km' }} />
          </div>
          {overview.scrapedAt && <Text type="secondary">数据: {overview.scrapedAt.split(' ')[0]}</Text>}
        </div>
      </Header>
      <Content style={{ padding: 24, background: '#f5f5f5' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 24, maxWidth: 1400, margin: '0 auto' }}>
          <Alert
            type="info"
            showIcon
            message="本站数据仅供参考，非实时房源信息。数据来源于公开渠道的统计分析，不构成任何租赁建议。"
            style={{ borderRadius: 8 }}
          />

          <OverviewCards overview={overview} />

          <AnalysisReport summary={analysis.summary} suggestions={analysis.suggestions} />

          <AdSlot slot="SLOT_TOP" format="horizontal" />

          <div style={{ background: '#fff', padding: 16, borderRadius: 8 }}>
            <Title level={5}>{workplace.name} 全景单价热力图</Title>
            <HeatmapCanvas workplace={workplace} enrichedStats={enrichedStats} maxDistance={maxDistance} />
          </div>

          <AdSlot slot="SLOT_MIDDLE" format="horizontal" />

          <div style={{ background: '#fff', padding: 16, borderRadius: 8 }}>
            <Title level={5}>各距离环性价比排行</Title>
            <TopByRing enrichedStats={enrichedStats} listings={listings} />
          </div>

          <div style={{ background: '#fff', padding: 16, borderRadius: 8 }}>
            <Title level={5}>{workplace.name} 周边 {maxDistance}km 租房单价地图 ({enrichedStats.length} 个小区)</Title>
            <CommunityMap workplace={workplace} enrichedStats={enrichedStats} maxDistance={maxDistance} listings={listings} />
          </div>

          <div style={{ background: '#fff', padding: 16, borderRadius: 8 }}>
            <Title level={5}>数据分析</Title>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
              <div>
                <PriceHistogram data={filteredListings} />
                <div style={{ fontSize: 11, color: '#999', marginTop: -8, marginBottom: 8 }}>数据口径: 范围内 {filteredListings.length} 套房源月租金分布, 红线为均价</div>
              </div>
              <div>
                <RoomsBarChart data={filteredListings} />
                <div style={{ fontSize: 11, color: '#999', marginTop: -8, marginBottom: 8 }}>数据口径: 范围内房源按板块统计各户型数量</div>
              </div>
              <div>
                <RentTypePie data={filteredListings} />
                <div style={{ fontSize: 11, color: '#999', marginTop: -8, marginBottom: 8 }}>数据口径: 范围内房源整租/合租/其他类型占比</div>
              </div>
              <div>
                <PriceVsArea data={filteredListings} />
                <div style={{ fontSize: 11, color: '#999', marginTop: -8, marginBottom: 8 }}>数据口径: 范围内房源面积与月租金关系, 帮助判断性价比</div>
              </div>
            </div>
          </div>

          <AdSlot slot="SLOT_BOTTOM" format="auto" />
        </div>
      </Content>
      <Footer style={{
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
