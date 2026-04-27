/**
 * 抖音风格竖版海报生成器 (9:16 = 1080x1920).
 * 用于导出适合抖音视频封面/图文的租房数据海报.
 */
import { downloadBlob } from './download';

/** 圆角矩形路径 */
function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + w - r, y);
  ctx.arcTo(x + w, y, x + w, y + r, r);
  ctx.lineTo(x + w, y + h - r);
  ctx.arcTo(x + w, y + h, x + w - r, y + h, r);
  ctx.lineTo(x + r, y + h);
  ctx.arcTo(x, y + h, x, y + h - r, r);
  ctx.lineTo(x, y + r);
  ctx.arcTo(x, y, x + r, y, r);
  ctx.closePath();
}

/** 文字自动换行，返回实际绘制行数 */
function wrapText(ctx, text, x, y, maxWidth, lineHeight, maxLines) {
  let line = '';
  let lineCount = 0;
  for (let i = 0; i < text.length; i++) {
    const testLine = line + text[i];
    if (ctx.measureText(testLine).width > maxWidth && line.length > 0) {
      lineCount++;
      if (maxLines && lineCount >= maxLines) {
        ctx.fillText(line.slice(0, -1) + '...', x, y + (lineCount - 1) * lineHeight);
        return lineCount;
      }
      ctx.fillText(line, x, y + (lineCount - 1) * lineHeight);
      line = text[i];
    } else {
      line = testLine;
    }
  }
  if (line) {
    lineCount++;
    ctx.fillText(line, x, y + (lineCount - 1) * lineHeight);
  }
  return lineCount;
}

/**
 * 生成抖音风格的推荐文案.
 * 根据分析数据生成吸引人的、适合抖音传播的文案.
 */
function generateDouyinCopy(analysis, enrichedStats, workplace, maxDistance, rangeOverview) {
  const lines = [];
  const { summary, suggestions } = analysis;
  if (!summary) return lines;

  // 主标题 - 吸引眼球的开头
  const titles = [
    `在上海${workplace.name}附近租房，选对小区能省一半！`,
    `打工人必看！${workplace.name}周边${maxDistance}km租房真相`,
    `${workplace.name}附近${rangeOverview.total}套房源数据告诉你：这些小区最划算！`,
    `别再瞎租房了！${workplace.name}周边性价比最高的小区竟然是...`,
    `月入5000也能住得好！${workplace.name}周边这些小区均价不到预期`,
  ];
  lines.push({ type: 'title', text: titles[Math.floor(Math.random() * titles.length)] });

  // 核心数据 - 用数字说话
  const avgPrice = rangeOverview.avgPrice;
  const avgUnit = rangeOverview.avgUnitPrice;
  lines.push({
    type: 'stat',
    text: `共${rangeOverview.total}套房源 · ${rangeOverview.communityCount}个小区 · 均价${avgPrice}元/月 · 单价${avgUnit}元/㎡`,
  });

  // 关键发现 - 从建议中提取
  for (const s of suggestions.slice(0, 3)) {
    lines.push({ type: 'point', text: s.text });
  }

  // 结尾钩子 - 引导点击
  const hooks = [
    '完整数据免费查，链接在评论区/主页！',
    '更多小区数据点击主页查看，每日更新！',
    '想知道你家附近租金多少？评论区告诉我！',
    '关注我，每天更新上海租房数据！',
  ];
  lines.push({ type: 'hook', text: hooks[Math.floor(Math.random() * hooks.length)] });

  return lines;
}

/**
 * 绘制抖音海报到 Canvas 并导出.
 *
 * @param {object} params
 * @param {object} params.analysis - generateAnalysis 返回的分析结果
 * @param {Array} params.enrichedStats - 筛选后小区统计
 * @param {object} params.workplace - 工作地点
 * @param {number} params.maxDistance - 最大距离
 * @param {object} params.rangeOverview - 范围内概览
 * @param {Array} params.filteredListings - 筛选后的房源列表
 */
export function exportDouyinPoster({ analysis, enrichedStats, workplace, maxDistance, rangeOverview, filteredListings }) {
  const W = 1080;
  const H = 1920;
  const canvas = document.createElement('canvas');
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext('2d');

  // ---- 背景 ----
  const bgGrad = ctx.createLinearGradient(0, 0, 0, H);
  bgGrad.addColorStop(0, '#0f0c29');
  bgGrad.addColorStop(0.5, '#302b63');
  bgGrad.addColorStop(1, '#24243e');
  ctx.fillStyle = bgGrad;
  ctx.fillRect(0, 0, W, H);

  // 装饰性光晕
  const glow1 = ctx.createRadialGradient(200, 300, 0, 200, 300, 400);
  glow1.addColorStop(0, 'rgba(102,126,234,0.15)');
  glow1.addColorStop(1, 'rgba(102,126,234,0)');
  ctx.fillStyle = glow1;
  ctx.fillRect(0, 0, W, 600);

  const glow2 = ctx.createRadialGradient(880, 1500, 0, 880, 1500, 350);
  glow2.addColorStop(0, 'rgba(118,75,162,0.12)');
  glow2.addColorStop(1, 'rgba(118,75,162,0)');
  ctx.fillStyle = glow2;
  ctx.fillRect(400, 1200, W, 600);

  // ---- 顶部 Header ----
  const headerH = 140;
  ctx.fillStyle = 'rgba(255,255,255,0.06)';
  ctx.fillRect(0, 0, W, headerH);

  // Logo 图标 (小房子)
  ctx.fillStyle = '#fff';
  const logoX = 60;
  const logoY = 50;
  const logoR = 22;
  ctx.beginPath();
  ctx.moveTo(logoX, logoY - logoR);
  ctx.lineTo(logoX - logoR, logoY);
  ctx.lineTo(logoX + logoR, logoY);
  ctx.closePath();
  ctx.fill();
  ctx.fillRect(logoX - logoR * 0.7, logoY, logoR * 1.4, logoR * 0.9);

  // 站名
  ctx.fillStyle = '#fff';
  ctx.font = 'bold 42px "PingFang SC", "Microsoft YaHei", sans-serif';
  ctx.fillText('租房雷达', 100, 65);

  ctx.fillStyle = 'rgba(255,255,255,0.5)';
  ctx.font = '22px "PingFang SC", "Microsoft YaHei", sans-serif';
  ctx.fillText('上海租房数据可视化', 100, 98);

  // 右侧标签
  const tagText = `${workplace.name} · ${maxDistance}km`;
  ctx.font = 'bold 24px "PingFang SC", "Microsoft YaHei", sans-serif';
  const tagW = ctx.measureText(tagText).width + 40;
  roundRect(ctx, W - tagW - 40, 45, tagW, 44, 22);
  ctx.fillStyle = 'rgba(255,255,255,0.12)';
  ctx.fill();
  ctx.fillStyle = '#fff';
  ctx.fillText(tagText, W - tagW - 20, 75);

  // ---- 推荐文案区 ----
  const copy = generateDouyinCopy(analysis, enrichedStats, workplace, maxDistance, rangeOverview);

  let curY = headerH + 50;

  // 主标题
  const titleItem = copy.find((c) => c.type === 'title');
  if (titleItem) {
    ctx.fillStyle = '#fff';
    ctx.font = 'bold 52px "PingFang SC", "Microsoft YaHei", sans-serif';
    curY += 60;
    const titleLines = wrapText(ctx, titleItem.text, 60, curY, W - 120, 68, 3);
    curY += titleLines * 68 + 30;
  }

  // 核心数据卡片
  const statItem = copy.find((c) => c.type === 'stat');
  if (statItem) {
    curY += 10;
    roundRect(ctx, 40, curY, W - 80, 110, 16);
    ctx.fillStyle = 'rgba(255,255,255,0.08)';
    ctx.fill();
    ctx.strokeStyle = 'rgba(255,255,255,0.12)';
    ctx.lineWidth = 1;
    ctx.stroke();

    ctx.fillStyle = 'rgba(255,255,255,0.7)';
    ctx.font = '24px "PingFang SC", "Microsoft YaHei", sans-serif';
    wrapText(ctx, statItem.text, 70, curY + 42, W - 140, 36, 2);
    curY += 130;
  }

  // ---- 大数据展示 ----
  const prices = filteredListings
    .map((d) => parseInt(d.price, 10))
    .filter((p) => !isNaN(p) && p > 0)
    .sort((a, b) => a - b);
  const medianPrice = prices.length > 0 ? prices[Math.floor(prices.length / 2)] : 0;

  const statCards = [
    { label: '房源总数', value: rangeOverview.total.toLocaleString(), unit: '套' },
    { label: '月租中位数', value: medianPrice.toLocaleString(), unit: '元' },
    { label: '平均单价', value: rangeOverview.avgUnitPrice.toString(), unit: '元/㎡' },
    { label: '小区数量', value: rangeOverview.communityCount.toLocaleString(), unit: '个' },
  ];

  const cardW = (W - 80 - 30) / 4;
  curY += 10;
  for (let i = 0; i < statCards.length; i++) {
    const cx = 40 + i * (cardW + 10);
    roundRect(ctx, cx, curY, cardW, 130, 12);
    ctx.fillStyle = 'rgba(255,255,255,0.06)';
    ctx.fill();

    ctx.fillStyle = 'rgba(255,255,255,0.5)';
    ctx.font = '20px "PingFang SC", "Microsoft YaHei", sans-serif';
    ctx.fillText(statCards[i].label, cx + 16, curY + 36);

    ctx.fillStyle = '#fff';
    ctx.font = 'bold 38px "PingFang SC", "Microsoft YaHei", sans-serif';
    ctx.fillText(statCards[i].value, cx + 16, curY + 82);

    ctx.fillStyle = 'rgba(255,255,255,0.4)';
    ctx.font = '18px "PingFang SC", "Microsoft YaHei", sans-serif';
    ctx.fillText(statCards[i].unit, cx + 16 + ctx.measureText(statCards[i].value).width + 6, curY + 82);
  }
  curY += 150;

  // ---- 要点建议 ----
  const points = copy.filter((c) => c.type === 'point');
  if (points.length > 0) {
    ctx.fillStyle = 'rgba(255,255,255,0.85)';
    ctx.font = 'bold 30px "PingFang SC", "Microsoft YaHei", sans-serif';
    ctx.fillText('核心发现', 60, curY);
    curY += 50;

    for (const pt of points) {
      // 要点卡片
      const textH = 80;
      roundRect(ctx, 40, curY, W - 80, textH, 12);
      ctx.fillStyle = 'rgba(255,255,255,0.05)';
      ctx.fill();

      // 竖条装饰
      roundRect(ctx, 40, curY, 5, textH, 2);
      ctx.fillStyle = '#667eea';
      ctx.fill();

      ctx.fillStyle = 'rgba(255,255,255,0.85)';
      ctx.font = '24px "PingFang SC", "Microsoft YaHei", sans-serif';
      wrapText(ctx, pt.text, 65, curY + 34, W - 140, 34, 2);
      curY += textH + 14;
    }
  }

  // ---- TOP 3 性价比之王 ----
  const top3 = [...enrichedStats].sort((a, b) => a.avgUnitPrice - b.avgUnitPrice).slice(0, 3);
  if (top3.length > 0) {
    curY += 20;
    ctx.fillStyle = '#fff';
    ctx.font = 'bold 30px "PingFang SC", "Microsoft YaHei", sans-serif';
    ctx.fillText('性价比 TOP 3', 60, curY);
    curY += 50;

    const medals = ['#FFD700', '#C0C0C0', '#CD7F32'];
    const medalLabels = ['NO.1', 'NO.2', 'NO.3'];
    for (let i = 0; i < top3.length; i++) {
      const c = top3[i];
      const rowH = 90;
      roundRect(ctx, 40, curY, W - 80, rowH, 12);
      ctx.fillStyle = i === 0 ? 'rgba(255,215,0,0.08)' : 'rgba(255,255,255,0.04)';
      ctx.fill();

      if (i === 0) {
        ctx.strokeStyle = 'rgba(255,215,0,0.3)';
        ctx.lineWidth = 1.5;
        ctx.stroke();
      }

      // 排名
      roundRect(ctx, 60, curY + 20, 50, 50, 8);
      ctx.fillStyle = medals[i];
      ctx.fill();
      ctx.fillStyle = '#000';
      ctx.font = 'bold 22px "PingFang SC", "Microsoft YaHei", sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText(medalLabels[i], 85, curY + 52);
      ctx.textAlign = 'left';

      // 小区名
      ctx.fillStyle = '#fff';
      ctx.font = 'bold 28px "PingFang SC", "Microsoft YaHei", sans-serif';
      const nameText = c.name.length > 10 ? c.name.slice(0, 10) + '...' : c.name;
      ctx.fillText(nameText, 130, curY + 40);

      // 距离
      ctx.fillStyle = 'rgba(255,255,255,0.5)';
      ctx.font = '20px "PingFang SC", "Microsoft YaHei", sans-serif';
      ctx.fillText(`距${workplace.name} ${c.dist}km`, 130, curY + 68);

      // 价格（右对齐）
      ctx.fillStyle = '#ff6b6b';
      ctx.font = 'bold 36px "PingFang SC", "Microsoft YaHei", sans-serif';
      ctx.textAlign = 'right';
      ctx.fillText(`${c.avgUnitPrice}`, W - 140, curY + 48);
      ctx.fillStyle = 'rgba(255,255,255,0.5)';
      ctx.font = '20px "PingFang SC", "Microsoft YaHei", sans-serif';
      ctx.fillText('元/㎡/月', W - 60, curY + 48);
      ctx.textAlign = 'left';

      // 均价
      ctx.fillStyle = 'rgba(255,255,255,0.4)';
      ctx.font = '18px "PingFang SC", "Microsoft YaHei", sans-serif';
      ctx.textAlign = 'right';
      ctx.fillText(`均价 ${c.avgPrice.toLocaleString()} 元/月`, W - 60, curY + 72);
      ctx.textAlign = 'left';

      curY += rowH + 12;
    }
  }

  // ---- 结尾钩子 ----
  const hookItem = copy.find((c) => c.type === 'hook');
  if (hookItem) {
    curY += 20;
    roundRect(ctx, 40, curY, W - 80, 70, 12);
    const hookGrad = ctx.createLinearGradient(40, curY, W - 40, curY);
    hookGrad.addColorStop(0, 'rgba(102,126,234,0.2)');
    hookGrad.addColorStop(1, 'rgba(118,75,162,0.2)');
    ctx.fillStyle = hookGrad;
    ctx.fill();

    ctx.fillStyle = '#fff';
    ctx.font = 'bold 26px "PingFang SC", "Microsoft YaHei", sans-serif';
    const hookText = hookItem.text;
    wrapText(ctx, hookText, 60, curY + 30, W - 140, 34, 2);
    curY += 90;
  }

  // ---- 底部 Footer ----
  const footerY = H - 140;
  ctx.fillStyle = 'rgba(255,255,255,0.04)';
  ctx.fillRect(0, footerY, W, 140);

  // 分隔线
  ctx.strokeStyle = 'rgba(255,255,255,0.08)';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(40, footerY);
  ctx.lineTo(W - 40, footerY);
  ctx.stroke();

  // URL
  const params = new URLSearchParams({ wp: workplace.name, dist: maxDistance });
  const url = `${window.location.host}/?${params.toString()}`;
  ctx.fillStyle = 'rgba(255,255,255,0.4)';
  ctx.font = '22px "PingFang SC", "Microsoft YaHei", sans-serif';
  ctx.fillText('完整数据免费查看', 60, footerY + 40);
  ctx.fillStyle = 'rgba(255,255,255,0.6)';
  ctx.font = '24px "PingFang SC", "Microsoft YaHei", sans-serif';
  ctx.fillText(url.length > 40 ? url.slice(0, 37) + '...' : url, 60, footerY + 75);

  // 日期
  ctx.fillStyle = 'rgba(255,255,255,0.3)';
  ctx.font = '20px "PingFang SC", "Microsoft YaHei", sans-serif';
  ctx.textAlign = 'right';
  ctx.fillText(new Date().toLocaleDateString('zh-CN'), W - 60, footerY + 40);
  ctx.fillText('租房雷达 · 数据仅供参考', W - 60, footerY + 70);
  ctx.textAlign = 'left';

  // ---- 导出 ----
  canvas.toBlob((blob) => {
    if (!blob) return;
    downloadBlob(blob, `租房雷达_抖音_${workplace.name}_${maxDistance}km_${new Date().toISOString().slice(0, 10)}.png`);
  }, 'image/png');
}

/**
 * 生成抖音推荐文案（纯文本）.
 * 返回适合粘贴到抖音视频描述的文字.
 */
export function generateDouyinText(analysis, workplace, maxDistance, rangeOverview) {
  const { summary, suggestions } = analysis;
  if (!summary) return '';

  const lines = [];

  // 标题
  lines.push(`📍 ${workplace.name}周边${maxDistance}km租房攻略`);
  lines.push('');

  // 数据概要
  lines.push(`📊 共${rangeOverview.total}套房源，${rangeOverview.communityCount}个小区`);
  lines.push(`💰 月租中位数约${rangeOverview.avgPrice}元，单价${rangeOverview.avgUnitPrice}元/㎡`);
  lines.push('');

  // 建议
  for (const s of suggestions.slice(0, 3)) {
    lines.push(`${s.icon} ${s.title}：${s.text}`);
  }

  lines.push('');
  lines.push('🔗 完整数据搜索：租房雷达');
  lines.push('');
  lines.push('#上海租房 #租房攻略 #张江租房 #租房推荐 #性价比租房 #上海打工租房 #浦东租房 #合租 #整租');

  return lines.join('\n');
}
