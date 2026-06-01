import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

// App web de hub-next: Vite + React + Tailwind v4 + @erplora/ui. SIN Capacitor (el runtime
// nativo es Tauri). Los Web Components de los módulos se cargan en runtime con import()
// dinámico desde /modules/** (copiados a public/ por sync-modules.mjs). ARQUITECTURA.md §1, §3.1.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    target: 'es2022',
    // El bundle de producción debe ser CSP-safe en script-src (sin eval) — lo verifica verify-csp.mjs.
  },
});
