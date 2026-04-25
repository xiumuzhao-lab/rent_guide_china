/**
 * 生成唯一标识串，用于去重.
 * 格式: {小区名}_{板块}_{经纬度前4位}_{均价}
 */
function generateUniqueId(stat) {
  const latKey = stat.lat ? String(stat.lat).replace('.', '').slice(0, 6) : '0';
  const lngKey = stat.lng ? String(stat.lng).replace('.', '').slice(0, 7) : '0';
  return `${stat.name}_${stat.region || 'unknown'}_${latKey}${lngKey}_${stat.avgUnitPrice}`;
}

/**
 * 将 enrichedStats 导出为 CSV 文件.
 * 包含唯一标识列用于去重.
 */
export function exportToCSV(enrichedStats, workplace, maxDistance) {
  const BOM = '\uFEFF';
  const header = [
    '唯一标识',
    '小区名',
    '板块',
    '距离(km)',
    '房源数',
    '均价(元/月)',
    '最低价(元/月)',
    '最高价(元/月)',
    '均面积(㎡)',
    '单价(元/㎡/月)',
    '纬度',
    '经度',
  ].join(',');

  const rows = enrichedStats
    .filter((s) => s.dist <= maxDistance)
    .map((s) => [
      `"${generateUniqueId(s)}"`,
      `"${s.name}"`,
      `"${s.region || ''}"`,
      s.dist,
      s.count,
      s.avgPrice,
      s.minPrice,
      s.maxPrice,
      s.avgArea,
      s.avgUnitPrice,
      s.lat || '',
      s.lng || '',
    ].join(','));

  const csv = BOM + header + '\n' + rows.join('\n');
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  import('./download').then(({ downloadBlob }) => {
    downloadBlob(blob, `${workplace.name}_${maxDistance}km_租房数据_${new Date().toISOString().slice(0, 10)}.csv`);
  });
}
