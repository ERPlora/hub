// Vite of hub-next. A contract with Django (`packages/live/live/spa.py`, `LIVE["spa"]` in
// `config/settings.py`): with DEBUG the shell loads `http://localhost:5173/static/spa/@vite/client`
// and `…/static/spa/frontend/main.ts` (Vite applies `base` in dev too); in production Django reads
// `frontend/dist/.vite/manifest.json` and links `/static/spa/assets/…` (WhiteNoise).
// `manage.py runserver` starts this dev server (`LIVE["vite"]`); `--novite` skips it.
import { dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

import { erploraVite } from '@erplora/ui/vite';
import { defineConfig } from 'vitest/config';

const DEV_HOST = 'localhost';
const DEV_PORT = 5173;

export default defineConfig({
  // From the string: under happy-dom (tests) the global `URL` is not Node's.
  root: dirname(fileURLToPath(import.meta.url)),
  base: '/static/spa/',
  plugins: erploraVite(),
  build: {
    outDir: 'frontend/dist',
    emptyOutDir: true,
    manifest: '.vite/manifest.json',
    target: 'es2022',
    rollupOptions: { input: 'frontend/main.ts' },
  },
  server: {
    host: DEV_HOST,
    port: DEV_PORT,
    // Django hard-codes the port: another free one would serve a page that never loads.
    strictPort: true,
    // The page comes from `<hub>.localhost:8000`: asset URLs must point back at this server.
    origin: `http://${DEV_HOST}:${DEV_PORT}`,
    hmr: { host: DEV_HOST, port: DEV_PORT },
  },
  test: {
    environment: 'happy-dom',
    include: ['frontend/**/*.test.ts', 'apps/*/frontend/**/*.test.ts', 'vite.config.test.ts', 'eslint.config.test.ts'],
    // Vitest's default `exclude` drops every `vite.config.*` and `eslint.config.*`.
    exclude: ['**/node_modules/**', '**/dist/**'],
  },
});
