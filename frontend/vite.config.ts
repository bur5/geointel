import { defineConfig } from 'vite';

export default defineConfig({
  server: {
    proxy: {
      '/api/v1/dashboard': process.env.GEOINTEL_DASHBOARD_ORIGIN ?? 'http://127.0.0.1:8000',
    },
  },
});
