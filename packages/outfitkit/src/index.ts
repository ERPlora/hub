// @erplora/outfitkit — barrel. Importar este módulo registra TODOS los componentes ok-*
// y re-exporta sus clases y tipos. Para tree-shake real, importa el componente concreto:
//   import '@erplora/outfitkit/ok-data-table';
export { OkDataTable } from './components/ok-data-table/ok-data-table.js';
export type { DataTableColumn, DataTableAction } from './components/ok-data-table/ok-data-table.js';
export { OkNavbar } from './components/ok-navbar/ok-navbar.js';
export { OkFooter } from './components/ok-footer/ok-footer.js';
export { OkContainer } from './components/ok-container/ok-container.js';
export { OkContainerFull } from './components/ok-container-full/ok-container-full.js';
export { OkHero } from './components/ok-hero/ok-hero.js';
