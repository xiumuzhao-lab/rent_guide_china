import { useState, useMemo, useCallback, useRef } from 'react';
import {
  Tabs, Card, Typography, Button, Select, message, Space, Tag,
} from 'antd';
import { CopyOutlined, DownloadOutlined, FileTextOutlined, CameraOutlined } from '@ant-design/icons';
import html2canvas from 'html2canvas';
import { generateAnalysis } from '../utils/analysis';
import { generateDouyinText } from '../utils/douyinPoster';
import { exportToCSV } from '../utils/export';
import { downloadBlob } from '../utils/download';
import RentTypePie from './TopRegionsBar';
import RoomsBarChart from './RoomsBarChart';
import PriceHistogram from './PriceHistogram';
import PriceVsArea from './PriceVsArea';
import RegionDistanceText from './RegionDistanceText';
import HeatmapCanvas from './HeatmapCanvas';
import CommunityMap from './CommunityMap';
import TopByRing from './TopByRing';
import useIsMobile from '../hooks/useIsMobile';

const { Title, Text, Paragraph } = Typography;

const PLATFORM_OPTIONS = [
  { value: 'douyin', label: '抖音' },
  { value: 'xiaohongshu', label: '小红书' },
];

function generateXiaohongshuText(analysis, workplace, maxDistance, rangeOverview) {
  const { summary, suggestions } = analysis;
  if (!summary) return '';

  const lines = [];
  lines.push(`📍 ${workplace.name}周边${maxDistance}km租房攻略`);
  lines.push('---');
  lines.push(`👀 共 ${rangeOverview.total} 套房源、${rangeOverview.communityCount} 个小区`);
  lines.push(`💰 月租中位数约 ${rangeOverview.avgPrice} 元，单价 ${rangeOverview.avgUnitPrice} 元/㎡`);
  lines.push('---');

  for (const s of suggestions.slice(0, 4)) {
    lines.push(`${s.icon} ${s.title}`);
    lines.push(s.text);
    lines.push('');
  }

  lines.push('---');
  lines.push('🔗 完整数据 → 租房雷达');
  lines.push('#上海租房 #租房攻略 #浦东租房 #租房推荐 #性价比租房 #上海打工 #合租 #整租');

  return lines.join('\n');
}

function generateCopyText(platform, analysis, workplace, maxDistance, rangeOverview) {
  if (platform === 'xiaohongshu') {
    return generateXiaohongshuText(analysis, workplace, maxDistance, rangeOverview);
  }
  return generateDouyinText(analysis, workplace, maxDistance, rangeOverview);
}

function captureRef(ref, filename) {
  const el = ref.current;
  if (!el) return;
  html2canvas(el, { backgroundColor: '#fff', scale: 2 }).then((canvas) => {
    canvas.toBlob((blob) => {
      if (!blob) return;
      downloadBlob(blob, filename);
    }, 'image/png');
  });
}

export default function ReportPage({
  listings,
  enrichedStats,
  filteredListings,
  workplace,
  maxDistance,
  overview,
}) {
  const [platform, setPlatform] = useState('douyin');
  const [exporting, setExporting] = useState('');
  const isMobile = useIsMobile();
  const analysisRef = useRef(null);
  const heatmapRef = useRef(null);
  const mapRef = useRef(null);
  const rankingRef = useRef(null);

  const rangeOverview = useMemo(() => {
    if (!filteredListings.length) return { total: 0, communityCount: 0, avgPrice: 0, avgUnitPrice: 0 };
    const prices = filteredListings.map((l) => parseInt(l.price, 10)).filter((p) => !isNaN(p) && p > 0);
    const areas = filteredListings.map((l) => parseFloat(l.area)).filter((a) => !isNaN(a) && a > 0);
    const avgPrice = prices.length ? Math.round(prices.reduce((s, p) => s + p, 0) / prices.length) : 0;
    const sumPrice = prices.reduce((s, p) => s + p, 0);
    const sumArea = areas.reduce((s, a) => s + a, 0);
    const avgUnitPrice = sumArea > 0 ? Math.round((sumPrice / sumArea) * 10) / 10 : 0;
    const communityCount = enrichedStats.length;
    return { total: filteredListings.length, communityCount, avgPrice, avgUnitPrice };
  }, [filteredListings, enrichedStats]);

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

  const generatedText = useMemo(
    () => generateCopyText(platform, analysis, workplace, maxDistance, rangeOverview),
    [platform, analysis, workplace, maxDistance, rangeOverview],
  );

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(generatedText).then(() => {
      message.success('已复制到剪贴板');
    }).catch(() => {
      message.error('复制失败');
    });
  }, [generatedText]);

  const handleExportCSV = useCallback(() => {
    exportToCSV(enrichedStats, workplace, maxDistance);
    message.success('CSV 已开始下载');
  }, [enrichedStats, workplace, maxDistance]);

  const handleExportListings = useCallback(() => {
    const BOM = '﻿';
    const header = [
      '小区名', '板块', '户型', '楼层', '面积(㎡)', '月租金(元)',
      '单价(元/㎡/月)', '距离(km)', '租赁类型', '朝向', '地铁',
    ].join(',');
    const rows = filteredListings.map((l) => [
      `"${l.community || ''}"`,
      `"${l.region || ''}"`,
      `"${l.rooms || ''}"`,
      `"${l.floor || ''}"`,
      l.area || '',
      l.price || '',
      l.unit_price || '',
      l.dist || '',
      `"${l.rent_type || ''}"`,
      `"${l.direction || ''}"`,
      `"${l.subway || ''}"`,
    ].join(','));
    const csv = BOM + header + '\n' + rows.join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    downloadBlob(blob, `${workplace.name}_${maxDistance}km_房源列表_${new Date().toISOString().slice(0, 10)}.csv`);
    message.success('房源列表 CSV 已开始下载');
  }, [filteredListings, workplace, maxDistance]);

  const handleCapture = useCallback((ref, name) => {
    setExporting(name);
    captureRef(ref, `${name}_${workplace.name}_${maxDistance}km.png`);
    setTimeout(() => setExporting(''), 3000);
  }, [workplace.name, maxDistance]);

  return (
    <div style={{ maxWidth: 900, margin: '0 auto' }}>
      <Title level={3} style={{ marginBottom: 16 }}>
        <FileTextOutlined /> 传播报告生成
      </Title>

      <Tabs
        defaultActiveKey="images"
        items={[
          {
            key: 'images',
            label: '图片导出',
            forceRender: true,
            children: (
              <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                <Card
                  size="small"
                  title="数据分析总览（合并导出）"
                  extra={(
                    <Button
                      icon={<CameraOutlined />}
                      size="small"
                      loading={exporting === '数据分析'}
                      onClick={() => handleCapture(analysisRef, '数据分析')}
                    >
                      导出图片
                    </Button>
                  )}
                >
                  <div ref={analysisRef} style={{ background: '#fff', padding: 16, borderRadius: 8 }}>
                    <Title level={4} style={{ marginTop: 0 }}>
                      {workplace.name} 板块分析（{maxDistance}km）
                    </Title>
                    <div style={{
                      display: 'grid',
                      gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr',
                      gap: isMobile ? 10 : 16,
                    }}>
                      <RentTypePie data={analysisListings} enrichedStats={enrichedStats} listings={filteredListings} />
                      <RoomsBarChart data={analysisListings} topRegions={topRegions} />
                      <PriceHistogram data={analysisListings} topRegions={topRegions} />
                      <PriceVsArea data={analysisListings} topRegions={topRegions} />
                    </div>
                    <div style={{ marginTop: 12 }}>
                      <RegionDistanceText enrichedStats={enrichedStats} maxDistance={maxDistance} workplace={workplace} />
                    </div>
                  </div>
                </Card>

                <Card
                  size="small"
                  title="单价热力图"
                  extra={(
                    <Button
                      icon={<CameraOutlined />}
                      size="small"
                      loading={exporting === '热力图'}
                      onClick={() => handleCapture(heatmapRef, '热力图')}
                    >
                      导出图片
                    </Button>
                  )}
                >
                  <div ref={heatmapRef} style={{ background: '#fff', padding: 16, borderRadius: 8 }}>
                    <Title level={4} style={{ marginTop: 0 }}>
                      {workplace.name} 全景单价热力图
                    </Title>
                    <HeatmapCanvas workplace={workplace} enrichedStats={enrichedStats} maxDistance={maxDistance} />
                  </div>
                </Card>

                <Card
                  size="small"
                  title="租房地图"
                  extra={(
                    <Button
                      icon={<CameraOutlined />}
                      size="small"
                      loading={exporting === '租房地图'}
                      onClick={() => handleCapture(mapRef, '租房地图')}
                    >
                      导出图片
                    </Button>
                  )}
                >
                  <div ref={mapRef} style={{ background: '#fff', padding: 16, borderRadius: 8 }}>
                    <Title level={4} style={{ marginTop: 0 }}>
                      {workplace.name} 周边 {maxDistance}km 租房单价地图
                    </Title>
                    <CommunityMap workplace={workplace} enrichedStats={enrichedStats} maxDistance={maxDistance} listings={listings} />
                  </div>
                </Card>

                <Card
                  size="small"
                  title="性价比排行"
                  extra={(
                    <Button
                      icon={<CameraOutlined />}
                      size="small"
                      loading={exporting === '性价比排行'}
                      onClick={() => handleCapture(rankingRef, '性价比排行')}
                    >
                      导出图片
                    </Button>
                  )}
                >
                  <div ref={rankingRef} style={{ background: '#fff', padding: 16, borderRadius: 8 }}>
                    <Title level={4} style={{ marginTop: 0 }}>
                      各距离环性价比排行
                    </Title>
                    <TopByRing enrichedStats={enrichedStats} listings={listings} />
                  </div>
                </Card>
              </Space>
            ),
          },
          {
            key: 'copy',
            label: '推荐文案',
            children: (
              <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                <Card size="small">
                  <Space wrap>
                    <Text>平台:</Text>
                    <Select
                      value={platform}
                      onChange={setPlatform}
                      options={PLATFORM_OPTIONS}
                      style={{ width: 140 }}
                    />
                    <Tag color="blue">{workplace.name} {maxDistance}km</Tag>
                    <Tag color="green">{rangeOverview.total} 套房源</Tag>
                  </Space>
                </Card>

                <Card
                  size="small"
                  title="自动生成文案"
                  extra={<Button icon={<CopyOutlined />} onClick={handleCopy} size="small">复制</Button>}
                >
                  <pre style={{
                    background: '#f5f5f5',
                    padding: 12,
                    borderRadius: 6,
                    whiteSpace: 'pre-wrap',
                    wordBreak: 'break-all',
                    fontSize: 13,
                    maxHeight: 400,
                    overflow: 'auto',
                    margin: 0,
                  }}>
                    {generatedText || '暂无数据，请先选择工作地点和距离'}
                  </pre>
                </Card>
              </Space>
            ),
          },
          {
            key: 'export',
            label: '批量导出',
            children: (
              <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                <Card size="small" title="数据导出">
                  <Space wrap>
                    <Button icon={<DownloadOutlined />} onClick={handleExportCSV}>
                      导出小区统计 (CSV)
                    </Button>
                    <Button icon={<DownloadOutlined />} onClick={handleExportListings}>
                      导出房源列表 (CSV)
                    </Button>
                  </Space>
                  <Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 0, fontSize: 12 }}>
                    共 {filteredListings.length} 条房源数据，{enrichedStats.filter((s) => s.dist <= maxDistance).length} 个小区
                  </Paragraph>
                </Card>

                <Card size="small" title="一键复制全部数据">
                  <Space wrap>
                    <Button
                      icon={<CopyOutlined />}
                      onClick={() => {
                        const text = enrichedStats
                          .filter((s) => s.dist <= maxDistance)
                          .map((s) => `${s.name}\t${s.region}\t${s.dist}km\t${s.avgUnitPrice}元/㎡\t${s.count}套`)
                          .join('\n');
                        navigator.clipboard.writeText(`小区名\t板块\t距离\t单价\t房源数\n${text}`).then(() => message.success('已复制'));
                      }}
                    >
                      复制小区数据 (Tab分隔)
                    </Button>
                    <Button
                      icon={<CopyOutlined />}
                      onClick={() => {
                        const text = filteredListings
                          .map((l) => `${l.community}\t${l.rooms}\t${l.area}㎡\t${l.price}元`)
                          .join('\n');
                        navigator.clipboard.writeText(`小区\t户型\t面积\t月租\n${text}`).then(() => message.success('已复制'));
                      }}
                    >
                      复制房源数据 (Tab分隔)
                    </Button>
                  </Space>
                </Card>
              </Space>
            ),
          },
        ]}
      />
    </div>
  );
}
