/// <reference types="vite/client" />

declare module '*.vue' {
  import type { DefineComponent } from 'vue';
  const component: DefineComponent<Record<string, never>, Record<string, never>, unknown>;
  export default component;
}

// Versión de la app horneada por Vite (`define`). La consume el footer del sidebar.
declare const __APP_VERSION__: string;
