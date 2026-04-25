/**
 * 下载 blob 为文件，兼容移动端（iOS Safari 等）.
 * 桌面端: <a>.click() 下载
 * 移动端: 优先 navigator.share，否则 open 新窗口
 */
export function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);

  // iOS / 移动端: 优先 Web Share API
  if (navigator.share && /Mobi|Android/i.test(navigator.userAgent)) {
    const file = new File([blob], filename, { type: blob.type });
    navigator.share({ files: [file] }).catch(() => {
      // share 失败（用户取消或不支持文件分享），fallback 到新窗口
      window.open(url, '_blank');
    });
    setTimeout(() => URL.revokeObjectURL(url), 5000);
    return;
  }

  // 桌面端: a.click()
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
