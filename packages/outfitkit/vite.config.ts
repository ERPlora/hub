import { defineConfig } from 'vite';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

// OutfitKit se compila en "library mode" multi-entry: un fichero ESM por componente
// (import individual / tree-shake) + un bundle `outfitkit.js` para CDN. `lit` queda
// EXTERNAL en todos los entries → una sola copia compartida (el consumidor la resuelve
// con su bundler o con un import-map en CDN/Django). Salida CSP-safe (sin eval).
//
// El theme de ejemplo (tokens --ok-*) se emite a dist/ para `@erplora/outfitkit/theme.css`.
const emitTheme = {
  name: 'outfitkit-emit-theme',
  generateBundle() {
    // @ts-expect-error — rollup `this.emitFile` disponible en el hook.
    this.emitFile({
      type: 'asset',
      fileName: 'theme.example.css',
      source: readFileSync(resolve(__dirname, 'src/theme/theme.example.css'), 'utf8'),
    });
  },
};

export default defineConfig({
  plugins: [emitTheme],
  build: {
    target: 'es2022',
    outDir: 'dist',
    emptyOutDir: true,
    minify: false,
    lib: {
      formats: ['es'],
      entry: {
        index: resolve(__dirname, 'src/index.ts'),
        outfitkit: resolve(__dirname, 'src/cdn.ts'),
        // Helper de registro idempotente como entry propio → un módulo puede importar
        // `@erplora/outfitkit/define` sin arrastrar el barrel (que auto-registra todos los ok-*).
        define: resolve(__dirname, 'src/base/define.ts'),
        'ok-data-table': resolve(__dirname, 'src/components/ok-data-table/ok-data-table.ts'),
        'ok-navbar': resolve(__dirname, 'src/components/ok-navbar/ok-navbar.ts'),
        'ok-footer': resolve(__dirname, 'src/components/ok-footer/ok-footer.ts'),
        'ok-container': resolve(__dirname, 'src/components/ok-container/ok-container.ts'),
        'ok-container-full': resolve(__dirname, 'src/components/ok-container-full/ok-container-full.ts'),
        'ok-hero': resolve(__dirname, 'src/components/ok-hero/ok-hero.ts'),
      },
    },
    rollupOptions: {
      external: [/^lit($|\/)/],
      output: {
        // Mantén nombres estables para los chunks compartidos (p.ej. el base ok-element).
        chunkFileNames: 'shared/[name].js',
        entryFileNames: '[name].js',
      },
    },
  },
});
