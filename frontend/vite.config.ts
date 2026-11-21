import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const headers: Record<string, string> = {}
  // Local training identity. Production must inject the authenticated actor at a trusted gateway.
  if (env.VITE_ARCHIVE_CONTOUR !== 'working') headers['X-User-Login'] = env.ARCHIVE_DEMO_LOGIN || 'hr_demo'
  return {
    plugins: [react()],
    server: {
      port: 5173,
      host: true,
      proxy: {
        '/api/v1': {
          target: env.ARCHIVE_API_TARGET || 'http://127.0.0.1:8000',
          changeOrigin: true,
          headers,
        },
      },
    },
  }
})
