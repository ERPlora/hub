import { Config } from '@stencil/core';

// Compilador Stencil COMPARTIDO de todos los módulos hub.
// Escanea modules/<id>/ui/**/*.tsx (cada @Component) y emite custom elements
// tree-shakables que se AUTO-DEFINEN al importarse. build-all.mjs luego
// esbuild-empaqueta el/los componente(s) de cada módulo en un único
// modules/<id>/dist/<id>.esm.js autocontenido (incluye el runtime de Stencil),
// compatible con el module-loader del shell (import → customElements ya definido).
//
// Decisión: 90% de la lógica en Rust; el WC es una mini-app que llama al SDK
// (query/command/on). No toca BD ni valida permisos para seguridad.
export const config: Config = {
  namespace: 'erplora-modules',
  srcDir: '../../modules',
  // Sin index.html ni www; solo compilamos componentes.
  taskQueue: 'async',
  outputTargets: [
    {
      type: 'dist-custom-elements',
      dir: '.stencil-out',
      // Cada componente se auto-define (customElements.define) al importarse:
      // así el bundle final solo necesita ser importado, sin registro manual.
      customElementsExportBehavior: 'auto-define-custom-elements',
      externalRuntime: false, // incluye el runtime de Stencil en el output
      generateTypeDeclarations: false,
    },
  ],
  // El bundle por módulo lo hace esbuild en build-all.mjs; aquí solo transpila.
  enableCache: true,
  sourceMap: false,
};
