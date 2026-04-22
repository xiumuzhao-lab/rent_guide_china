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

        const uri = '/ws/place/v1/suggestion'
        const apiParams = {
          keyword,
          key: apiKey,
          region: '上海',
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
export default defineConfig({
  plugins: [react(), tmapProxyPlugin()],
  base: process.env.VITE_BASE || '/',
})
