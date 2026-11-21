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
        ...Object.fromEntries(['legacy', 'workforce', 'requirements', 'hiring', 'students', 'mobility', 'social-support', 'recognition', 'feedback'].map(service => [
          '/' + service + '/', { target: env.API_GATEWAY_TARGET || 'http://127.0.0.1:8080', changeOrigin: true }
        ])),
        '/legacy-api': { target: env.ARCHIVE_API_TARGET || 'http://127.0.0.1:8000', changeOrigin: true, headers, rewrite: path => path.replace(/^\/legacy-api/, '') },
        '/requirements-api': { target: env.API_GATEWAY_TARGET || 'http://127.0.0.1:8080', changeOrigin: true, rewrite: path => path.replace(/^\/requirements-api/, '/requirements/api/v1') },
        '/hiring-api': { target: env.API_GATEWAY_TARGET || 'http://127.0.0.1:8080', changeOrigin: true, rewrite: path => path.replace(/^\/hiring-api/, '/hiring/api/v1') },
        '/api/v1/reports/annual': { target: env.REPORT_API_TARGET || 'http://127.0.0.1:18590', changeOrigin: true },
        '/api/v1/students': {
          target: env.STUDENTS_API_TARGET || 'http://127.0.0.1:8105',
          changeOrigin: true,
        },
        '/support-api': {
          target: env.SUPPORT_API_TARGET || 'http://127.0.0.1:8106',
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/support-api/, '/api/v1/support'),
        },
        '/workforce-api': {
          target: env.WORKFORCE_API_TARGET || 'http://127.0.0.1:8101',
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/workforce-api/, '/api/v1'),
        },
        '/api/v1': {
          target: env.ARCHIVE_API_TARGET || 'http://127.0.0.1:8000',
          changeOrigin: true,
          headers,
        },
      },
    },
  }
})
