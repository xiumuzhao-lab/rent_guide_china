export const REGIONS = {
  zhangjiang: { name: '张江', slug: 'zhangjiang' },
  jinqiao: { name: '金桥', slug: 'jinqiao' },
  tangzhen: { name: '唐镇', slug: 'tangzhen' },
  chuansha: { name: '川沙', slug: 'chuansha' },
  changning: { name: '长宁', slug: 'changning' },
};

export const WORKPLACES = [
  { key: 'zhangjiang', name: '张江国创中心', lat: 31.2033, lng: 121.5905, address: '浦东新区丹桂路899号' },
  { key: 'zhangjiang_2', name: '张江国创二期', lat: 31.219406, lng: 121.627225, address: '浦东新区张江国创中心二期' },
  { key: 'jinqiao', name: '金桥开发区', lat: 31.2475, lng: 121.6282, address: '浦东新区金桥经济技术开发区' },
  { key: 'tangzhen', name: '唐镇', lat: 31.2150, lng: 121.6550, address: '浦东新区唐镇中心' },
  { key: 'chuansha', name: '川沙', lat: 31.1900, lng: 121.7000, address: '浦东新区川沙新镇' },
];

export const DISTANCE_RINGS = [3, 5, 8, 10, 15];

export const RING_COLORS = {
  3: '#2ecc71',
  5: '#27ae60',
  8: '#f39c12',
  10: '#e67e22',
  15: '#e74c3c',
};

export const RING_LABELS = {
  3: '0-3km 步行可达',
  5: '3-5km 骑行/短途',
  8: '5-8km 短途公交',
  10: '8-10km 公交',
  15: '10-15km 需地铁',
};

export const REGION_COLORS = {
  zhangjiang: '#4e79a7',
  jinqiao: '#f28e2b',
  tangzhen: '#e15759',
  chuansha: '#76b7b2',
  changning: '#59a14f',
};
