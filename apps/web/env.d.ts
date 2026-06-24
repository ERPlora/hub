/// <reference types="vite/client" />

declare module '*.vue' {
  import type { DefineComponent } from 'vue';
  const component: DefineComponent<Record<string, never>, Record<string, never>, unknown>;
  export default component;
}

// Versión de la app horneada por Vite (`define`). La consume el footer del sidebar.
declare const __APP_VERSION__: string;

// `swagger-ui-dist` no emite tipos para su bundle ES. Lo usa SOLO ApiDocsPage.vue, al que le
// pasamos el spec por `spec:` (Swagger no hace su propio fetch sin auth). Declaramos la firma
// mínima que consumimos (constructor con `domNode` + `spec`).
declare module 'swagger-ui-dist/swagger-ui-es-bundle.js' {
  interface SwaggerUIOptions {
    domNode?: Element | null;
    spec?: Record<string, unknown>;
    deepLinking?: boolean;
    docExpansion?: 'list' | 'full' | 'none';
    tryItOutEnabled?: boolean;
    [key: string]: unknown;
  }
  const SwaggerUIBundle: (options: SwaggerUIOptions) => { unmount?: () => void };
  export default SwaggerUIBundle;
}

// CSS de Swagger UI importado por su efecto secundario (estilos). Sin export.
declare module 'swagger-ui-dist/swagger-ui.css';
