// @erplora/module-ui — componentes Stencil COMPARTIDOS por los Web Components de los módulos.
// Se compilan DENTRO del bundle de cada módulo (vía @erplora/module-stencil), no como paquete
// aparte. Los módulos lo consumen así:
//   import '@erplora/module-ui';                              // registra <data-table> (side-effect)
//   import type { DataTableColumn } from '@erplora/module-ui';
// `ionic-jsx.d.ts` declara los `ion-*` globalmente para el typecheck de Stencil (los provee el
// shell en runtime; no se bundlean).
export { DataTable } from './components/data-table/data-table';
export type { DataTableColumn, DataTableAction } from './components/data-table/data-table';
