/// <reference types="vite/client" />

// `.vue` files for tools without Vue's language service (vue-tsc and Volar resolve them for real).
declare module '*.vue' {
  import type { DefineComponent } from 'vue';
  const component: DefineComponent;
  export default component;
}

// pdf.js's worker module ships no types: Files' preview hands it to pdf.js as `globalThis.pdfjsWorker` (base/frontend/lib/pdf.ts).
declare module 'pdfjs-dist/legacy/build/pdf.worker.mjs' {
  export const WorkerMessageHandler: unknown;
}
