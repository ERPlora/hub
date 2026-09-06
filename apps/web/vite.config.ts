/// <reference types="vitest/config" />
import { defineConfig, type Plugin } from 'vite';
import vue from '@vitejs/plugin-vue';
import tailwindcss from '@tailwindcss/vite';
import Icons from 'unplugin-icons/vite';
import { readFile } from 'node:fs/promises';
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { execSync } from 'node:child_process';
import { availableParallelism } from 'node:os';

import { stripModuleVersion } from './src/lib/module-url';
import { outfitkitVersionStamp, resolveOutfitkitVersion } from './outfitkit-version.ts';

// Versión de la app, horneada en build → la lee el footer del sidebar vía `__APP_VERSION__`.
// Orden de prioridad: env APP_VERSION (CI) > git tag más reciente > package.json.
// package.json es "0.0.0" a propósito (monorepo); la versión real viene de los tags git.
/**
 * Versión de OutfitKit REALMENTE instalada (hub#1024). Vacío si no se puede resolver.
 *
 * hub#1588 — la resolución vive en `outfitkit-version.ts` porque este número tiene ahora DOS
 * consumidores: el `define` de abajo (lo que el shell reporta en runtime) y el sello que el build
 * escribe en `dist/outfitkit-version.json` (lo que la imagen dice llevar). Una sola fuente, para
 * que no puedan decir cosas distintas.
 */
const APP_DIR = fileURLToPath(new URL('.', import.meta.url));
const OUTFITKIT_VERSION = resolveOutfitkitVersion(APP_DIR);

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

// hub#1364 — the vitest pool is CAPPED, not sized off the machine. Left alone, vitest 4 resolves
// `maxWorkers` to `Math.max(availableParallelism() - 1, 1)` (`resolveMaxWorkers`), i.e. the whole
// box. This suite stopped having a box to itself: since hub#1466 it runs as the `pnpm verify` job
// of `test-web.yml` on `ci-runner-1`, a cx53 (16 vCPU / 32 GB) that serves SIX runner slots — so
// six web jobs would ask for 15 forks each, 90 processes on 16 vCPU. Every other pool there is
// already bounded (`CARGO_BUILD_JOBS=8` per slot, precisely so six cargos are not 96 rustc);
// vitest was the last one that was not. The same starvation was measured on the dev machine when
// the gate still ran this suite (hub#1367: 15.8 s idle → 390 s under fleet load).
//
// The cap is a CEILING, never a target: `Math.min` with vitest's own default means this can only
// LOWER the pool, so the 2-core GitHub-hosted fallback (`vars.CI_RUNNER_LABEL` unset, default 1)
// is not oversubscribed to bound a runner it never touches. A number and not a percentage on
// purpose — a percentage is still the machine, which is the thing being bounded. `VITEST_MAX_WORKERS`
// overrides this (vitest applies the env last) for a one-off run on an idle box.
// `minWorkers` is deliberately NOT set: vitest 4 removed it (absent from the whole dist).
// Contract: vite.config.test.ts (hub#1364).
const VITEST_MAX_WORKERS = Math.min(4, Math.max(availableParallelism() - 1, 1));

// En dev, Vite se niega a servir JS de /public importado dinámicamente desde el código
// ("can only be referenced via HTML tags"). Los módulos (WC Lit) se cargan en runtime con
// import() dinámico desde /modules/**; este middleware los sirve CRUDOS (sin transform de Vite),
// antes que el pipeline de transform. En prod los sirve el runtime (crates/server), no Vite.
//
// hub#935 — en producción el shell pide los assets del módulo por su ruta VERSIONADA
// (`/modules/<id>/v/<version>/…`), que es lo que impide que una caché conteste con el bundle de la
// versión anterior. Aquí no hay runtime ni caché: los módulos están copiados en `public/modules/<id>/`
// sin carpeta de versión, así que el segmento se quita antes de tocar disco — para el `.js` que sirve
// este middleware y, en el `rewrite` de abajo, para TODO lo demás (module.json, icons.json, locales),
// que lo sirve el estático de Vite. Sin eso, el shell de dev pediría rutas que no existen.
function serveModulesRaw(): Plugin {
  return {
    name: 'erplora-serve-modules-raw',
    configureServer(server) {
      // Reescribe la url ANTES de cualquier otro middleware: así el estático de Vite ve la ruta que
      // existe en `public/` y no hace falta duplicar aquí el servido de cada tipo de asset.
      server.middlewares.use((req: { url?: string }, _res, next: () => void) => {
        if (req.url?.startsWith('/modules/')) req.url = stripModuleVersion(req.url);
        next();
      });
      server.middlewares.stack.unshift({
        route: '',
        handle: async (req: { url?: string }, res: import('node:http').ServerResponse, next: () => void) => {
          const url = stripModuleVersion((req.url ?? '').split('?')[0]);
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
    // hub#1588 — el sello de versiones en `dist/outfitkit-version.json`: lo que ESTE build metió
    // en la imagen, para que no haya que deducirlo de la fecha de construcción.
    outfitkitVersionStamp({ outfitkit: OUTFITKIT_VERSION, hub: APP_VERSION }),
  ],
  define: {
    __APP_VERSION__: JSON.stringify(APP_VERSION),
    // hub#1024 — la OutfitKit que ESTA imagen lleva de verdad, leída del paquete resuelto (no del
    // rango de `package.json`: el Dockerfile hace `add @erplora/outfitkit@latest` en cada build, así
    // que el rango miente). Con ella el shell puede avisar cuando un módulo trae otra horneada.
    __OUTFITKIT_VERSION__: JSON.stringify(OUTFITKIT_VERSION),
  },
  build: {
    target: 'es2022',
    rollupOptions: {
      treeshake: {
        preset: 'recommended',
        // hub#798 — Stencil's @ionic/core component modules open with unannotated top-level calls
        // (`proxyCustomElement(...)`), so Rollup keeps every one of the 140+ components that
        // @ionic/vue re-exports (~1 MB in the entry chunk, ion-datetime/ion-input-otp/… included,
        // none of them used). Their only real side effect is `defineCustomElement()`, which is an
        // EXPORTED function invoked explicitly (by @ionic/vue on wrapper mount / controller use,
        // and by lib/ionic-wc.ts for OutfitKit's deps) — nothing registers at import time, so the
        // set of registered custom elements does not change; only never-referenced code is
        // dropped. JS only: any CSS stays side-effectful. Contract: vite.config.test.ts (hub#798).
        moduleSideEffects: (id: string) =>
          !(/node_modules\/(\.pnpm\/[^/]+\/node_modules\/)?@ionic\/core\//.test(id) && id.endsWith('.js')),
      },
      output: {
        // hub#798 — cache-stability split. These vendors only change on dependency bumps; without
        // this, EVERY app-code change invalidated one ~1.7 MB entry chunk and a PWA update
        // re-downloaded it whole. The entry still imports them statically (Vite emits
        // modulepreload for all of them → parallel fetch, no waterfall), so boot COST is
        // unchanged — a shell edit just stops invalidating them. Everything else (mammoth, pdfjs,
        // swagger-ui, app code) keeps Rollup's default assignment — those are already lazy chunks
        // and must stay that way.
        //
        // ⚠️ Ionic (@ionic/core, @ionic/vue, ionicons) is NOT grouped, on purpose: a module
        // assigned through manualChunks becomes a chunk entry whose exports are all preserved,
        // and for the @ionic/vue barrel that resurrects every tree-shaken component (measured:
        // 146 @ionic/core files instead of 103, +~300 kB of dead code). Ionic therefore stays in
        // the entry chunk, tree-shaken by the moduleSideEffects override above. Only packages the
        // shell uses (near-)fully are grouped, where full-export preservation costs nothing.
        manualChunks: (id: string): string | undefined => {
          const pkg = id.match(/node_modules\/(?:\.pnpm\/[^/]+\/node_modules\/)?((?:@[^/]+\/)?[^/]+)\//)?.[1];
          if (!pkg) return undefined;
          if (pkg === 'vue' || pkg.startsWith('@vue/') || pkg === 'vue-router' || pkg === 'vue-i18n' || pkg.startsWith('@intlify/')) {
            return 'vendor-vue';
          }
          if (pkg === '@erplora/outfitkit' || pkg === 'lit' || pkg === 'lit-html' || pkg === 'lit-element' || pkg.startsWith('@lit/') || pkg.startsWith('@lit-labs/')) {
            return 'vendor-outfitkit';
          }
          return undefined;
        },
      },
    },
  },
  // Unit tests (vitest), colocated with the code: src/**/*.test.ts. The Playwright e2e SPECS live
  // in tests/e2e and vitest does NOT run them (they need the app up). The root-level test files
  // cover the dev-bench plumbing (hub#787: module sync from a worktree + env-driven port/proxy)
  // and the `updateSnapshots` wiring of the visual contract (hub#1250) — a config FILE, not a
  // spec, so importing it is a pure module load with no server involved.
  test: {
    include: [
      'src/**/*.test.ts',
      'sync-modules.test.mjs',
      'vite.config.test.ts',
      'outfitkit-version.test.ts',
      'tests/playwright.config.test.ts',
      'tests/bench-ports.test.ts',
    ],
    environment: 'node',
    // hub#1367 — these two are anti-hang BACKSTOPS, not assertions, and vitest's defaults
    // (testTimeout 5000, hookTimeout 10000) are WALL-CLOCK budgets. This suite runs on a machine
    // shared with the fleet (~19 worktrees on 15 cores) and, since hub#1352, the pre-push gate is
    // the only place it runs at all — so a test killed for lack of CPU is not a slow test, it is
    // an ABORTED PUSH, and the retry that follows loads the box further.
    //
    // The budget is sized off what the suite actually costs when the machine is healthy: 2178
    // tests in ~17 s of test time, mean ~8 ms, nothing within an order of magnitude of 5 s. 60 s
    // therefore leaves a starved test room to finish while still failing a genuinely hung one
    // inside a minute — the gate stays deterministic, a real failure still fails.
    // Deliberately NOT `retry`: re-rolling the dice would hide the real flakes too.
    testTimeout: 60_000,
    hookTimeout: 60_000,
    // hub#1364 — see VITEST_MAX_WORKERS above.
    maxWorkers: VITEST_MAX_WORKERS,
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
