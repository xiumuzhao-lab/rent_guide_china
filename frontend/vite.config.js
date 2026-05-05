import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'fs'
import path from 'path'
import crypto from 'crypto'

function tmapProxyPlugin() {
  let apiKey = ''
  let apiSk = ''

  // 从项目根目录 .env 读取密钥
  const envPath = path.resolve(process.cwd(), '..', '.env')
  if (fs.existsSync(envPath)) {
    for (const line of fs.readFileSync(envPath, 'utf-8').split('\n')) {
      const m = line.match(/^\s*(TENCENT_MAP_KEY|TENCENT_MAP_SK)\s*=\s*(.+)\s*$/)
      if (m) {
        if (m[1] === 'TENCENT_MAP_KEY') apiKey = m[2].trim()
        if (m[1] === 'TENCENT_MAP_SK') apiSk = m[2].trim()
      }
    }
  }

  return {
    name: 'tmap-proxy',
    configureServer(server) {
      server.middlewares.use('/api/ip-location', async (req, res) => {
        const rawIp = (req.headers['x-forwarded-for'] || req.socket.remoteAddress || '').split(',')[0].trim();
        const ip = (!rawIp || rawIp === '127.0.0.1' || rawIp === '::1' || rawIp.startsWith('192.168.') || rawIp.startsWith('10.')) ? '' : rawIp;
        const makeSig = (uri, params) => {
          const sortedStr = Object.keys(params).sort().map(k => `${k}=${params[k]}`).join('&');
          const sig = crypto.createHash('md5').update(`${uri}?${sortedStr}${apiSk}`).digest('hex');
          const encoded = Object.keys(params).sort().map(k => `${k}=${encodeURIComponent(params[k])}`).join('&');
          return `https://apis.map.qq.com${uri}?${encoded}&sig=${sig}`;
        };
        try {
          // 1) IP 定位
          const ipParams = { key: apiKey, output: 'json' };
          if (ip) ipParams.ip = ip;
          const ipResp = await fetch(makeSig('/ws/location/v1/ip', ipParams));
          const data = await ipResp.json();
          if (data.status !== 0) {
            res.setHeader('Content-Type', 'application/json');
            res.end(JSON.stringify(data));
            return;
          }
          // 2) 逆地址编码
          const { lat, lng } = data.result.location;
          const geoResp = await fetch(makeSig('/ws/geocoder/v1', {
            key: apiKey, output: 'json', location: `${lat},${lng}`,
          }));
          const geoData = await geoResp.json();
          let address = '';
          if (geoData.status === 0) {
            const addr = geoData.result.address_component || {};
            const street = addr.street || '';
            const number = addr.street_number || '';
            if (number && street && number.startsWith(street)) address = number;
            else if (street && number) address = street + number;
            else if (number) address = number;
            else if (street) address = street;
            if (!address) address = (geoData.result.formatted_addresses || {}).recommend || '';
          }
          data.result.address = address;
          res.setHeader('Content-Type', 'application/json');
          res.end(JSON.stringify(data));
        } catch (e) {
          res.statusCode = 502;
          res.end(JSON.stringify({ status: -1, message: e.message }));
        }
      });

      server.middlewares.use('/api/tmap', async (req, res) => {
        if (!apiKey) {
          res.statusCode = 500
          res.end(JSON.stringify({ status: -1, message: 'TENCENT_MAP_KEY not configured' }))
          return
        }

        // req.url is like ?keyword=xxx (relative to /api/tmap)
        const rawUrl = req.url || ''
        const search = new URLSearchParams(rawUrl.startsWith('?') ? rawUrl : rawUrl.replace(/^[^?]*/, ''))
        const keyword = search.get('keyword') || ''
        const city = search.get('city') || '上海'

        const uri = '/ws/place/v1/suggestion'
        const apiParams = {
          keyword,
          key: apiKey,
          region: city,
          page_size: '5',
          output: 'json',
        }

        const sortedParams = Object.keys(apiParams).sort()
          .map((k) => `${k}=${apiParams[k]}`).join('&')
        const sig = crypto.createHash('md5')
          .update(`${uri}?${sortedParams}${apiSk}`).digest('hex')

        const encodedParams = Object.keys(apiParams).sort()
          .map((k) => `${k}=${encodeURIComponent(apiParams[k])}`).join('&')
        const tmapUrl = `https://apis.map.qq.com${uri}?${encodedParams}&sig=${sig}`

        try {
          const resp = await fetch(tmapUrl)
          const data = await resp.json()
          res.setHeader('Content-Type', 'application/json')
          res.end(JSON.stringify(data))
        } catch (e) {
          res.statusCode = 502
          res.end(JSON.stringify({ status: -1, message: e.message }))
        }
      })
    },
  }
}

// https://vite.dev/config/
const commitDate = new Date().toISOString().replace(/[-:T]/g, '').slice(0, 12);

export default defineConfig({
  plugins: [react(), tmapProxyPlugin()],
  base: process.env.VITE_BASE || '/',
  define: {
    __APP_VERSION__: JSON.stringify(commitDate),
  },
})
