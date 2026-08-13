/// <reference types="vitest/config" />
import { defineConfig, type Plugin } from 'vite';
import vue from '@vitejs/plugin-vue';
import tailwindcss from '@tailwindcss/vite';
import Icons from 'unplugin-icons/vite';
import { readFile } from 'node:fs/promises';
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { execSync } from 'node:child_process';

// Versión de la app, horneada en build → la lee el footer del sidebar vía `__APP_VERSION__`.
// Orden de prioridad: env APP_VERSION (CI) > git tag más reciente > package.json.
// package.json es "0.0.0" a propósito (monorepo); la versión real viene de los tags git.
const APP_VERSION = (() => {
  // 1. Env var inyectada por CI (build-hub.yml en tags v*).
  if (process.env.APP_VERSION) return process.env.APP_VERSION;
  // 2. Último tag git (p.ej. "v0.1.20" → "0.1.20"). Funciona en local y en CI.
  try {
    const tag = execSync('git describe --tags --abbrev=0 2>/dev/null || echo ""', { encoding: 'utf8' }).trim();
    if (tag) return tag.replace(/^v/, '');
  } catch {
    // git no disponible (p.ej. Docker sin .git) → sigue al fallback
  }
  // 3. Fallback: package.json (0.0.0).
  try {
    return JSON.parse(readFileSync(join(__dirname, 'package.json'), 'utf8')).version || '0.0.0';
  } catch {
    return '0.0.0';
  }
})();

// hub#787: two dev benches must be able to coexist (e.g. two worktrees comparing branches), so
// the dev server port and the runtime proxy target come from the environment, with today's
// values as defaults. Precedence for the target: VITE_RUNTIME_TARGET > derived from HUB_BIND
// (the runtime's own bind var, exported by scripts/dev.mjs) > http://127.0.0.1:8787.
const DEV_PORT = Number(process.env.VITE_PORT) || 5173;
const RUNTIME_TARGET = (() => {
  if (process.env.VITE_RUNTIME_TARGET) return process.env.VITE_RUNTIME_TARGET;
  const bind = process.env.HUB_BIND;
  if (bind) {
    const sep = bind.lastIndexOf(':');
    const rawHost = sep === -1 ? bind : bind.slice(0, sep);
    const port = sep === -1 ? '8787' : bind.slice(sep + 1);
    // A wildcard bind is not a dialable host — proxy to loopback instead.
    const host = !rawHost || rawHost === '0.0.0.0' || rawHost === '::' || rawHost === '[::]' ? '127.0.0.1' : rawHost;
    return `http://${host}:${port}`;
  }
  return 'http://127.0.0.1:8787';
})();

// En dev, Vite se niega a servir JS de /public importado dinámicamente desde el código
// ("can only be referenced via HTML tags"). Los módulos (WC Lit) se cargan en runtime con
// import() dinámico desde /modules/**; este middleware los sirve CRUDOS (sin transform de Vite),
// antes que el pipeline de transform. En prod los sirve el runtime (crates/server), no Vite.
function serveModulesRaw(): Plugin {
  return {
    name: 'erplora-serve-modules-raw',
    configureServer(server) {
      server.middlewares.stack.unshift({
        route: '',
        handle: async (req: { url?: string }, res: import('node:http').ServerResponse, next: () => void) => {
          const url = (req.url ?? '').split('?')[0];
          if (!url.startsWith('/modules/') || !url.endsWith('.js')) return next();
          const filePath = join(__dirname, 'public', url);
          if (!existsSync(filePath)) return next();
          res.setHeader('Content-Type', 'text/javascript; charset=utf-8');
          res.end(await readFile(filePath));
        },
      });
    },
  };
}

// Shell web del Hub: Vite + Vue 3 + @ionic/vue + Tailwind v4. Base Ionic (componentes ion-* vía
// @ionic/vue). Los componentes `ok-*` de OutfitKit son Web Components (Lit): se marcan como custom
// elements para que el compilador de Vue no los trate como componentes Vue. Los módulos (WC Lit) se
// cargan en runtime con import() dinámico desde /modules/** (copiados a public/ por sync-modules.mjs).
// Build CSP-safe en script-src (sin eval): Vue compila las plantillas en build (SFC), no en runtime.
export default defineConfig({
  plugins: [
    serveModulesRaw(),
    vue({
      template: {
        compilerOptions: {
          // ok-* (OutfitKit) y los tags de módulo (erp-*) son custom elements, no componentes Vue.
          isCustomElement: (tag) => tag.startsWith('ok-') || tag.startsWith('erp-'),
        },
      },
    }),
    // Iconos Iconify inline EN BUILD (offline, CSP-safe, sin runtime ni red). Los imports
    // `~icons/<set>/<name>?raw` se reemplazan por el string SVG del set local (@iconify-json/*).
    // El shell los consume vía lib/icons.ts → <HubIcon>. Ver lib/icons.ts y components/HubIcon.vue.
    Icons({ compiler: 'raw' }),
    tailwindcss(),
  ],
  define: {
    __APP_VERSION__: JSON.stringify(APP_VERSION),
  },
  build: {
    target: 'es2022',
  },
  // Unit tests (vitest), colocated with the code: src/**/*.test.ts. The Playwright e2e live in
  // tests/e2e and vitest does NOT run them (they need the app up). The two root-level test files
  // cover the dev-bench plumbing (hub#787): module sync from a worktree + env-driven port/proxy.
  test: {
    include: ['src/**/*.test.ts', 'sync-modules.test.mjs', 'vite.config.test.ts'],
    environment: 'node',
  },
  // Dev proxy (mismo origen → sin CORS). El runtime local (Axum :8787) no expone CORS y el Cloud
  // (erplora.com) tampoco para localhost; con VITE_RUNTIME_URL='' y VITE_CLOUD_API_URL='/cloud'
  // (ver .env.local) todas las llamadas salen de :5173 y Vite las reenvía:
  //   /api + /ws → runtime Axum local · /cloud/* → Cloud Portal (reescrito sin el prefijo)
  server: {
    // Bind explícito a IPv4. Node 17+ (aquí v24) resuelve `localhost`→`::1` primero, así que
    // Vite quedaba escuchando SOLO en IPv6 `[::1]:5173`. El webview de Tauri pega a `127.0.0.1`
    // → conexión rechazada → ventana en blanco. Forzar 127.0.0.1 + strictPort lo evita.
    host: '127.0.0.1',
    port: DEV_PORT,
    strictPort: true,
    proxy: {
      '/cloud': {
        target: 'https://erplora.com',
        changeOrigin: true,
        // secure:false → no verificar el cert en el proxy dev. Necesario tras proxies de inspección
        // TLS corporativos (Netskope): Node no confía en su CA (usa su propio bundle, no el llavero).
        // Solo dev; el tráfico ya pasa por el proxy corporativo de todas formas.
        secure: false,
        rewrite: (p) => p.replace(/^\/cloud/, ''),
      },
      '/api': { target: RUNTIME_TARGET, changeOrigin: true },
      '/ws': { target: RUNTIME_TARGET, changeOrigin: true, ws: true },
    },
  },
});
