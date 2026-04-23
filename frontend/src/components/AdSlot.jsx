import { useEffect, useRef } from 'react';

/**
 * Google AdSense 广告位组件 (当前已禁用).
 *
 * 使用方式:
 *   <AdSlot slot="1234567890" format="auto" />
 *
 * @param {object} props
 * @param {string} props.slot - 广告单元 ID (从 AdSense 后台获取)
 * @param {string} [props.format='auto'] - 广告格式: auto|horizontal|vertical|rectangle
 * @param {string} [props.style] - 自定义样式
 */
const ADS_ENABLED = false;

export default function AdSlot({ slot, format = 'auto', style = {} }) {
  const adRef = useRef(null);
  const pushed = useRef(false);

  useEffect(() => {
    if (!ADS_ENABLED || !slot || pushed.current) return;
    pushed.current = true;
    try {
      (window.adsbygoogle = window.adsbygoogle || []).push({});
    } catch {
      // AdSense 未加载时静默忽略
    }
  }, [slot]);

  if (!ADS_ENABLED || !slot) return null;

  return (
    <div style={{ textAlign: 'center', margin: '16px 0', ...style }}>
      <ins
        ref={adRef}
        className="adsbygoogle"
        style={{ display: 'block', minHeight: 90 }}
        data-ad-client="ca-pub-5877303836451682"
        data-ad-slot={slot}
        data-ad-format={format}
        data-full-width-responsive="true"
      />
    </div>
  );
}
