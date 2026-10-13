/// <reference types="vite/client" />

// `.vue` files for tools without Vue's language service (vue-tsc and Volar resolve them for real).
declare module '*.vue' {
  import type { DefineComponent } from 'vue';
  const component: DefineComponent;
  export default component;
}
