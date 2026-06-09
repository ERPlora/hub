import { defineConfig, type Plugin } from 'vite';
import vue from '@vitejs/plugin-vue';
import tailwindcss from '@tailwindcss/vite';
import { readFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { join } from 'node:path';

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
    tailwindcss(),
  ],
  build: {
    target: 'es2022',
  },
});
