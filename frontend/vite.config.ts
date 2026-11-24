import { defineConfig } from 'vite';

export default defineConfig({
  server: {
    proxy: {
      '/geointel-api/': {
        target: 'http://127.0.0.1:8000',
        rewrite: (path) => path.replace(/^\/geointel-api/, ''),
      },
    },
  },
});
