// @erplora/outfitkit — barrel. Importar este módulo registra los componentes ok-* que OutfitKit
// aporta (lo que Ionic NO da bien) y re-exporta sus clases y tipos. Para tree-shake real, importa
// el componente concreto: import '@erplora/outfitkit/ok-data-table';
//
// OutfitKit EXTIENDE Ionic: solo cubre los huecos (data-table de admin + chrome de landing). Para
// todo lo demás (botones, iconos, inputs, cards, overlays…) se usa `ion-*` directo; ya NO hay
// wrappers ok-* de primitivos.

// ── Compuestos / dashboard ──────────────────────────────────────────────────────────────
export { OkDataTable } from './components/ok-data-table/ok-data-table.js';
export type {
  DataTableColumn,
  DataTableAction,
  DataTableView,
} from './components/ok-data-table/ok-data-table.js';

// ── App launcher (grid 3×3 del shell) ─────────────────────────────────────────────────────
export { OkAppLauncher } from './components/ok-app-launcher/ok-app-launcher.js';
export type { OkLauncherApp } from './components/ok-app-launcher/ok-app-launcher.js';

// ── Dashboard / métricas (pantalla /system) ───────────────────────────────────────────────
export { OkGauge } from './components/ok-gauge/ok-gauge.js';
export type { OkGaugeThreshold, OkGaugeType } from './components/ok-gauge/ok-gauge.js';
export { OkKpi } from './components/ok-kpi/ok-kpi.js';
export { OkStat } from './components/ok-stat/ok-stat.js';
export { OkSparkline } from './components/ok-sparkline/ok-sparkline.js';
export { OkStatusPill } from './components/ok-status-pill/ok-status-pill.js';
export type { OkStatusPillTone, OkStatusPillSize } from './components/ok-status-pill/ok-status-pill.js';
export { OkEmptyState } from './components/ok-empty-state/ok-empty-state.js';

// ── Landing chrome ──────────────────────────────────────────────────────────────────────
export { OkNavbar } from './components/ok-navbar/ok-navbar.js';
export { OkFooter } from './components/ok-footer/ok-footer.js';
export { OkContainer } from './components/ok-container/ok-container.js';
export { OkContainerFull } from './components/ok-container-full/ok-container-full.js';
export { OkHero } from './components/ok-hero/ok-hero.js';
