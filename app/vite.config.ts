import path from 'path';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  server: {
    port: 5200,
    host: '127.0.0.1',
    strictPort: true,
    proxy: {
      '/api': 'http://localhost:5201',
      '/files': 'http://localhost:5201',
    },
  },
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
      '@shared': path.resolve(__dirname, 'shared'),
    },
  },
});
