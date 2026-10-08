/// <reference types="vitest/config" />
import { createReadStream, statSync } from 'node:fs'
import { join, normalize, sep } from 'node:path'
import { fileURLToPath } from 'node:url'

import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, type Plugin } from 'vite'

const webui = fileURLToPath(new URL('../webui/', import.meta.url))
const dataDir = join(webui, 'data')

const contentTypes: Record<string, string> = {
  '.json': 'application/json; charset=utf-8',
  '.gz': 'application/gzip',
}

/** In development, serve ../webui/data (written by `arena export`) at /data, as the built site expects. */
function arenaData(): Plugin {
  return {
    name: 'arena-data',
    configureServer(server) {
      server.middlewares.use('/data', (req, res, next) => {
        const path = decodeURIComponent((req.url ?? '/').split('?')[0] ?? '/')
        const file = normalize(join(dataDir, path))
        if (!file.startsWith(dataDir + sep)) {
          next()
          return
        }
        let size: number
        try {
          const stats = statSync(file)
          if (!stats.isFile()) {
            next()
            return
          }
          size = stats.size
        } catch {
          next()
          return
        }
        const extension = file.slice(file.lastIndexOf('.'))
        res.setHeader('Content-Type', contentTypes[extension] ?? 'application/octet-stream')
        res.setHeader('Content-Length', String(size))
        res.setHeader('Cache-Control', 'no-store')
        createReadStream(file).pipe(res)
      })
    },
  }
}

export default defineConfig({
  // Relative URLs: the build works from any directory of any static host, including model-compose's web UI.
  base: './',
  plugins: [react(), tailwindcss(), arenaData()],
  publicDir: false,
  build: {
    outDir: webui,
    // webui/data belongs to `arena export`; scripts/clean.mjs removes only the previous build.
    emptyOutDir: false,
    assetsDir: 'assets',
    target: 'es2023',
  },
  test: {
    include: ['src/**/*.test.{ts,tsx}'],
    environment: 'node',
    restoreMocks: true,
  },
})
