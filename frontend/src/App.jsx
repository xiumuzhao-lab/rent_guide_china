import './App.css';
import { useState, useEffect, useMemo } from 'react';
import { Layout, Typography, Spin, Slider, message } from 'antd';
import WorkplaceSelector from './components/WorkplaceSelector';
import OverviewCards from './components/OverviewCards';
import CommunityMap from './components/CommunityMap';
import DistanceTable from './components/DistanceTable';
import PriceBoxPlot from './components/PriceBoxPlot';
import PriceHistogram from './components/PriceHistogram';
import RoomsBarChart from './components/RoomsBarChart';
import AvgAreaBar from './components/AvgAreaBar';
import TopCommunities from './components/TopCommunities';
import RentTypePie from './components/RentTypePie';
import PriceVsArea from './components/PriceVsArea';
import DirectionBar from './components/DirectionBar';
import { WORKPLACES } from './utils/constants';
import { buildCommunityStats, enrichStatsWithDistance, getOverview } from './utils/stats';

const { Header, Content } = Layout;
const { Title, Text } = Typography;

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
        <Title level={4} style={{ margin: 0 }}>链家租房分析</Title>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <WorkplaceSelector value={workplace} onChange={setWorkplace} />
          <div style={{ width: 200 }}>
            <Text type="secondary">最大距离: {maxDistance}km</Text>
            <Slider min={3} max={30} value={maxDistance} onChange={setMaxDistance} step={1} marks={{ 3: '3', 10: '10', 15: '15', 30: '30' }} />
          </div>
          {overview.scrapedAt && <Text type="secondary">数据: {overview.scrapedAt.split(' ')[0]}</Text>}
        </div>
      </Header>
      <Content style={{ padding: 24, background: '#f5f5f5' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 24, maxWidth: 1400, margin: '0 auto' }}>
          <OverviewCards overview={overview} />

          <div style={{ background: '#fff', padding: 16, borderRadius: 8 }}>
            <Title level={5}>{workplace.name} 周边 {maxDistance}km 租房单价地图 ({enrichedStats.length} 个小区)</Title>
            <CommunityMap workplace={workplace} enrichedStats={enrichedStats} maxDistance={maxDistance} listings={listings} />
          </div>

          <div style={{ background: '#fff', padding: 16, borderRadius: 8 }}>
            <Title level={5}>按距离分层的小区列表</Title>
            <DistanceTable enrichedStats={enrichedStats} listings={listings} />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
            <div style={{ background: '#fff', padding: 16, borderRadius: 8 }}><PriceBoxPlot data={listings} /></div>
            <div style={{ background: '#fff', padding: 16, borderRadius: 8 }}><PriceHistogram data={listings} /></div>
            <div style={{ background: '#fff', padding: 16, borderRadius: 8 }}><RoomsBarChart data={listings} /></div>
            <div style={{ background: '#fff', padding: 16, borderRadius: 8 }}><AvgAreaBar data={listings} /></div>
            <div style={{ background: '#fff', padding: 16, borderRadius: 8 }}><TopCommunities data={listings} /></div>
            <div style={{ background: '#fff', padding: 16, borderRadius: 8 }}><RentTypePie data={listings} /></div>
            <div style={{ background: '#fff', padding: 16, borderRadius: 8 }}><PriceVsArea data={listings} /></div>
            <div style={{ background: '#fff', padding: 16, borderRadius: 8 }}><DirectionBar data={listings} /></div>
          </div>
        </div>
      </Content>
    </Layout>
  );
}
