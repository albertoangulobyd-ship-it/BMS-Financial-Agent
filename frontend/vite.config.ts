/// <reference types="vitest/config" />
// La app local de BMS. Se construye en src/bms_agent/web (lo sirve bms-agent serve en
// /app) porque las instalaciones de Windows y de Docker no tienen Node: lo construido va
// en git, y tests/test_app_local.py comprueba con web/fuente.json que esta al dia.
import { fileURLToPath } from 'node:url';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vite';

// El servidor de verdad (bms-agent serve) al que el servidor de desarrollo pasa /api.
const servidor = process.env.BMS_SERVE_URL ?? 'http://127.0.0.1:8765';
const salida = fileURLToPath(new URL('../src/bms_agent/web', import.meta.url));
const textos = fileURLToPath(new URL('../src/bms_agent/textos', import.meta.url));

export default defineConfig({
  base: '/app/',
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  build: {
    outDir: salida,
    emptyOutDir: true,
    assetsDir: 'assets',
    // Nada en linea como data: (la CSP de /app solo deja fuentes de 'self'), sin mapas
    // (no hace falta ensenar el codigo fuente) y sin el polyfill de modulepreload
    // (Edge y Chromium lo traen).
    assetsInlineLimit: 0,
    sourcemap: false,
    modulePreload: { polyfill: false },
    cssCodeSplit: false,
    reportCompressedSize: false,
    target: 'es2022',
    // Las dependencias en su propio fichero: cambia solo al cambiar una dependencia, asi
    // que lo construido en git no repite medio mega en cada cambio de una pantalla.
    chunkSizeWarningLimit: 700,
    rollupOptions: {
      output: {
        manualChunks: (id) => (id.includes('/node_modules/') ? 'vendor' : undefined),
      },
    },
  },
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    // Los catalogos de textos viven en src/bms_agent/textos (fuera de frontend/): el
    // servidor de desarrollo solo sirve esta carpeta y la de los textos.
    fs: { strict: true, allow: ['.', textos] },
    proxy: {
      '/api': {
        target: servidor,
        // serve exige que el Host sea el suyo (127.0.0.1:<puerto>).
        changeOrigin: true,
        configure: (proxy) => {
          // Solo en desarrollo: un POST desde esta pagina llega con Origin
          // http://127.0.0.1:5173 y serve lo trataria como otro sitio (403 en las
          // ordenes). Se cambia solo si es el origen de este servidor; uno de fuera se
          // deja tal cual y serve lo rechaza.
          proxy.on('proxyReq', (peticion, entrada) => {
            const origen = entrada.headers.origin;
            if (origen === 'http://127.0.0.1:5173' || origen === 'http://localhost:5173') {
              peticion.setHeader('origin', new URL(servidor).origin);
            }
          });
        },
      },
    },
  },
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
  },
});
