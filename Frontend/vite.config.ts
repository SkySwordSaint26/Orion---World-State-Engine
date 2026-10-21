import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'VITE_')
  return {
    plugins: [react()],
    server: {
      proxy: {
        '/api/v1': {
          target: env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api/v1',
          rewrite: path => path.replace(/^\/api\/v1/, ''),
          changeOrigin: true,
        },
      },
    },
  }
})
