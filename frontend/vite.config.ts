import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { fileURLToPath } from 'node:url'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '..', '')
  const appMode = mode === 'portfolio' ? 'portfolio' : (env.VITE_APP_MODE || 'local')
  if (!['local', 'portfolio'].includes(appMode)) throw new Error('VITE_APP_MODE must be local or portfolio.')
  const proxy = appMode === 'local' ? { '/api': { target: env.ALETHIA_API_TARGET || 'http://127.0.0.1:8000' } } : undefined
  return {
    resolve: { alias: { '@alethia/app': fileURLToPath(new URL(appMode === 'portfolio' ? './src/portfolio/PortfolioApp.tsx' : './src/App.tsx', import.meta.url)) } },
    build: { modulePreload: { polyfill: appMode !== 'portfolio' } },
    plugins: [react(), tailwindcss()],
    preview: {
      host: '127.0.0.1', port: 4173, strictPort: true,
      proxy,
    },
    server: {
      port: 5173,
      strictPort: true,
      proxy,
    },
  }
})
