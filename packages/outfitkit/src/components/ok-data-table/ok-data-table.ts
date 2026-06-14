import { LitElement, html, css, nothing } from 'lit';
import { property, state } from 'lit/decorators.js';
import { repeat } from 'lit/directives/repeat.js';
import { styleMap } from 'lit/directives/style-map.js';
import { define } from '../../base/define.js';
// Internamente usa ion-button / ion-checkbox / ion-icon NATIVOS (los registra el host). OutfitKit
// construye SOBRE Ionic; no envolvemos lo que Ionic ya da.

// ok-data-table — DataTable reutilizable de ERPlora (Lit), construido con elementos Ionic
// (ion-searchbar/ion-button/ion-icon, registrados por el host). Port 1:1 del antiguo
// <data-table> de @erplora/module-ui + el look del DataTable React del Hub. El WC nunca toca la BD.
//
// COMPONENTE COMPUESTO: SÍ tiene su propio CSS (a diferencia de los wrappers finos), todo con
// tokens --ion-*/--ok-*. La superficie pública (props/eventos/tipos) está CONGELADA (la consumen
// ~180 vistas): SOLO se AÑADEN props opcionales nuevas; nada se quita ni renombra.
//
// DOS MODOS:
//  • Cliente (por defecto): recibe TODAS las filas en `rows`; filtra (searchKeys) y pagina en
//    memoria. Para listas pequeñas / no paginadas.
//  • Servidor (`serverSide`): NO filtra ni pagina en memoria. Renderiza las `rows` de la página
//    actual y usa `total`/`page`/`pageSize`/`sort`/`sortDir` para pager y carets. Emite
//    `pageChange`/`sortChange`/`searchChange`/`filterChange`; el módulo re-consulta al runtime.
//
// Filas NO clicables (navegación vía botones de fila): se pasan `actions` y se escucha `rowAction`.

export interface DataTableColumn {
  /** Clave del campo en la fila (o id lógico si se usa `format`). */
  key: string;
  /** Cabecera de la columna. */
  header: string;
  /** Formateador → string a mostrar. Si se omite, se usa row[key]. */
  format?: (row: Record<string, unknown>) => string;
  /** Alineación del contenido de la celda. */
  align?: 'left' | 'right' | 'center';
  /** (server) La columna es ordenable: cabecera clicable que emite `sortChange`. */
  sortable?: boolean;
  /** (server) La columna es filtrable: añade un control en la fila de filtros. */
  filterable?: boolean;
  /** (server) Tipo de control de filtro. Por defecto 'text'. */
  filterType?: 'text' | 'select' | 'multiselect' | 'number' | 'date' | 'range' | 'daterange';
  /** (server) Opciones para `filterType: 'select'` / `'multiselect'`. */
  options?: { value: string; label: string }[];
  /** Render de celda a medida (devuelve un TemplateResult de Lit, p.ej. un `ok-toggle` o un chip).
   *  Tiene prioridad sobre `format`/valor crudo. El módulo lo crea con su `html` (lit deduplicado). */
  render?: (row: Record<string, unknown>) => unknown;
  /** Oculta la columna por defecto (el usuario la reactiva en el selector de columnas). */
  hidden?: boolean;
  /** (opcional) Ancho CSS de la columna en la vista lista en grid (p.ej. '8rem', '20%', 'minmax(8rem,1fr)').
   *  Si se omite, la columna ocupa `minmax(8rem,1fr)`. Sin efecto en el fallback con <table>. */
  width?: string;
}

/** Vista de presentación de las filas (lista/tarjetas). */
export type DataTableView = 'table' | 'cards';

export interface DataTableAction {
  /** Id que se emite en `rowAction`. */
  id: string;
  /** Texto del botón (o aria-label si solo hay icono). */
  label: string;
  /** Nombre de un ion-icon opcional. */
  icon?: string;
  /** Color Ionic del botón (p.ej. 'danger', 'primary'). */
  color?: string;
}

/** Acción primaria de la topbar (botón destacado). Emite el evento `primaryAction`. */
export interface DataTablePrimaryAction {
  /** Texto / aria-label del botón. */
  label: string;
  /** Nombre de un ion-icon opcional (por defecto 'add'). */
  icon?: string;
}

/** Clave estable de fila: nombre de campo o función que la devuelve. */
export type DataTableRowKey = string | ((row: Record<string, unknown>) => string);

/** (NUEVO, additivo) Todos los textos humanos del data-table, para i18n. Default en INGLÉS.
 *  Se pasan desde fuera vía la prop `.labels` (parcial); lo no pasado cae al default inglés.
 *  El contenido data-driven (columns/rows/options) NO va aquí — ya es externo. */
export interface OkDataTableLabels {
  /** Placeholder del buscador. */
  search: string;
  /** Estado vacío / "sin resultados". */
  empty: string;
  /** Título del botón/panel de filtros + aria del drawer de filtros. */
  filters: string;
  /** Botón "Limpiar" (selección y filtros). */
  clear: string;
  /** Botón "Aplicar" (filtros). */
  apply: string;
  /** Barra de selección: "{n} seleccionados" ({n} = nº filas). */
  selected: string;
  /** Botón "Importar CSV". */
  importCsv: string;
  /** Botón "Exportar CSV". */
  exportCsv: string;
  /** Botón "Añadir" (alta). */
  add: string;
  /** Aria del botón de menú overflow (⋮). */
  moreActions: string;
  /** Aria del selector de "filas por página". */
  rowsPerPage: string;
  /** Sufijo del selector compacto de tamaño de página (p.ej. "10 / pág."). */
  perPageShort: string;
  /** Aria del botón de vista lista. */
  viewList: string;
  /** Aria del botón de vista tarjetas. */
  viewCards: string;
  /** Aria del selector de columnas. */
  columnsVisible: string;
  /** Texto resumido del selector de columnas. */
  columns: string;
  /** Cabecera de la columna de acciones de fila. */
  actions: string;
  /** Aria del botón "Cerrar" (drawer). */
  close: string;
  /** Título del drawer de alta. */
  newRecord: string;
  /** Aria del drawer del formulario de alta/edición. */
  form: string;
  /** Placeholder del input de filtro de texto. */
  filterPlaceholder: string;
  /** Etiqueta/placeholder "Desde" (rango de fechas). */
  from: string;
  /** Etiqueta/placeholder "Hasta" (rango de fechas). */
  to: string;
  /** Sufijo aria "{label} desde" (rango de fechas en línea); {label} = cabecera de columna. */
  fromOf: string;
  /** Sufijo aria "{label} hasta" (rango de fechas en línea); {label} = cabecera de columna. */
  toOf: string;
  /** Placeholder "≥" (rango numérico, borde inferior). */
  gte: string;
  /** Placeholder "≤" (rango numérico, borde superior). */
  lte: string;
  /** Texto cuando una columna no tiene valores distintos (chips de filtro). */
  noValues: string;
  /** Aria "Seleccionar todo" (checkbox de cabecera). */
  selectAll: string;
  /** Aria "Seleccionar fila" (checkbox de fila, vista lista). */
  selectRow: string;
  /** Aria "Seleccionar" (checkbox de tarjeta). */
  select: string;
  /** Pager: "Mostrando {from}–{to} de" ({from}/{to} ya interpolados por el componente). */
  showing: string;
  /** Pager: singular "registro" (cuando count === 1). */
  recordSingular: string;
  /** Pager: plural "registros" (cuando count !== 1). */
  recordPlural: string;
}

/** Defaults en INGLÉS. Variables con token `{n}`/`{label}`/`{from}`/`{to}`. */
const DEFAULT_LABELS: OkDataTableLabels = {
  search: 'Search…',
  empty: 'No results',
  filters: 'Filters',
  clear: 'Clear',
  apply: 'Apply',
  selected: '{n} selected',
  importCsv: 'Import CSV',
  exportCsv: 'Export CSV',
  add: 'Add',
  moreActions: 'More actions',
  rowsPerPage: 'Rows per page',
  perPageShort: '{n} / page',
  viewList: 'View as list',
  viewCards: 'View as cards',
  columnsVisible: 'Visible columns',
  columns: 'Columns',
  actions: 'Actions',
  close: 'Close',
  newRecord: 'New',
  form: 'Form',
  filterPlaceholder: 'Filter…',
  from: 'From',
  to: 'To',
  fromOf: '{label} from',
  toOf: '{label} to',
  gte: '≥',
  lte: '≤',
  noValues: 'No values',
  selectAll: 'Select all',
  selectRow: 'Select row',
  select: 'Select',
  showing: 'Showing {from}–{to} of',
  recordSingular: 'record',
  recordPlural: 'records',
};

export class OkDataTable extends LitElement {
  static styles = css`
    :host {
      /* Vars overridable (estilo Ionic), default = cadena --ok-* → --ion-* → hex */
      --background: var(--ok-surface, var(--ion-card-background, var(--ion-background-color, #ffffff)));
      --color: var(--ok-text, var(--ion-text-color, #1c1b17));
      --color-muted: var(--ok-muted, var(--ion-color-medium, rgba(var(--ion-text-color-rgb, 24, 24, 27), 0.55)));
      --border-color: var(--ok-border, var(--ion-color-step-150, rgba(var(--ion-text-color-rgb, 24, 24, 27), 0.12)));
      --border-color-soft: var(--ok-border-soft, var(--ion-color-step-100, rgba(var(--ion-text-color-rgb, 24, 24, 27), 0.07)));
      /* Borde más marcado para los controles de la toolbar (selects/pastilla de fechas), para que se
       * distingan como controles en claro y oscuro aunque el lienzo y la superficie casi no contrasten. */
      --control-border: color-mix(in srgb, var(--color) 22%, transparent);
      /* Relieve de cabecera/pie: step-100 (definido en claro y oscuro) → contraste con el lienzo. */
      --header-background: var(--ok-surface-2, var(--ion-color-step-100, rgba(var(--ion-text-color-rgb, 24, 24, 27), 0.04)));
      --row-hover: var(--ok-row-hover, var(--ion-color-step-50, rgba(var(--ion-text-color-rgb, 24, 24, 27), 0.03)));
      --primary: var(--ok-primary, var(--ion-color-primary, #3880ff));
      --primary-contrast: var(--ok-primary-contrast, var(--ion-color-primary-contrast, #ffffff));
      --border-radius: var(--ok-radius, 16px);
      --font: var(--ok-font, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif);

      display: block;
      color: var(--color);
      font-family: var(--font);
    }
    * { box-sizing: border-box; }
    .card {
      position: relative;
      display: flex;
      flex-direction: column;
      /* Flat: sin borde ni elevación (directiva 2026-06-09). */
      border: 0;
      border-radius: var(--border-radius);
      overflow: hidden;
      background: var(--background);
      box-shadow: none;
    }

    /* Panel lateral derecho (drawer) DENTRO de la tabla: filtros / alta-edición. No empuja contenido. */
    .tk-scrim { position: absolute; inset: 0; background: rgba(0, 0, 0, 0.18); z-index: 19; }
    .drawer { position: absolute; top: 0; right: 0; height: 100%; width: 340px; max-width: 88%;
      background: var(--background); border-left: 1px solid var(--border-color);
      box-shadow: -10px 0 28px rgba(0, 0, 0, 0.10); display: flex; flex-direction: column; z-index: 20;
      animation: tk-slide-in 0.18s ease; }
    @keyframes tk-slide-in { from { transform: translateX(100%); } to { transform: translateX(0); } }
    .drawer .dh { flex: 0 0 auto; display: flex; align-items: center; justify-content: space-between;
      padding: 0.6rem 0.5rem 0.6rem 1rem; border-bottom: 1px solid var(--border-color); font-size: 1rem; }
    .drawer .db { flex: 1 1 auto; min-height: 0; overflow: auto; padding: 1rem; display: flex; flex-direction: column; gap: 0.85rem; }
    .fblock { display: flex; flex-direction: column; gap: 0.45rem; }
    .flabel { font-size: 13px; font-weight: 500; color: var(--color); }
    .frange { display: flex; gap: 0.5rem; }
    /* Filtros cliente: chips multi-select (estilo Hub) + rango de fechas. */
    .chips { display: flex; flex-wrap: wrap; gap: 0.4rem; }
    .chip { display: inline-flex; align-items: center; gap: 0.25rem; padding: 0.25rem 0.6rem; border: 1px solid var(--border-color); border-radius: 999px; background: var(--background); color: var(--color-muted); font-size: 12px; cursor: pointer; transition: color 0.12s, background 0.12s, border-color 0.12s; }
    .chip:hover { color: var(--color); }
    .chip.on { border-color: var(--primary); color: var(--primary); background: color-mix(in srgb, var(--primary) 15%, transparent); }
    .chip ion-icon { font-size: 12px; }
    .chip-empty { font-size: 12px; color: var(--color-muted); }
    .daterange { display: flex; gap: 0.6rem; }
    .daterange ion-input { flex: 1; }
    /* Pie del drawer de filtros: Limpiar / Aplicar. */
    .df { flex: 0 0 auto; display: flex; align-items: center; justify-content: flex-end; gap: 0.4rem; padding: 0.6rem 0.85rem; border-top: 1px solid var(--border-color); }
    .df .df-clear { margin-right: auto; }

    /* Modo fill: la tabla ocupa el alto del contenedor; filas con scroll interno; pager fijo. */
    :host([fill]) { display: flex; flex-direction: column; height: 100%; min-height: 0; }
    :host([fill]) .card { flex: 1 1 auto; min-height: 0; }
    :host([fill]) .bar, :host([fill]) .panel, :host([fill]) .pager { flex: 0 0 auto; }
    :host([fill]) .scroll, :host([fill]) .cards-grid { flex: 1 1 auto; min-height: 0; overflow: auto; }

    /* ── Topbar / cabecera (relieve) ─────────────────────────────────────────────────────── */
    .bar { display: flex; flex-direction: column; gap: 0.6rem; padding: 0.65rem 1rem; border-bottom: 1px solid var(--border-color); background: var(--header-background); }
    /* Toolbar CONSOLIDADA: TODOS los controles (buscador, filtros, page-size, vistas, columnas,
     * CSV, ⋮, alta) son hijos directos de UNA sola fila flex que envuelve ELEMENTO A ELEMENTO
     * (no por bloques): caben en una línea → una línea; los que no caben bajan a la(s) línea(s)
     * que hagan falta. El cluster derecho se empuja al borde con .tk-spacer (hueco flexible)
     * solo cuando todo cabe en una línea; al envolver, el spacer se oculta y todo se apila a la
     * izquierda. */
    .bar-main { display: flex; flex-wrap: wrap; align-items: center; gap: 0.5rem; }
    .bar-main > ion-button { --padding-start: 0.5rem; --padding-end: 0.5rem; margin: 0; }
    /* Spacer que absorbe el hueco libre en pantallas anchas (empuja el cluster derecho al borde).
     * Se oculta por debajo de 1024px para que, al envolver, los controles se apilen a la izquierda. */
    .tk-spacer { flex: 1 1 0; min-width: 0; align-self: stretch; }
    @media (max-width: 1024px) { .tk-spacer { display: none; } }
    /* Buscador a ancho completo (línea propia) en móvil; el resto envuelve debajo. */
    @media (max-width: 640px) { .search { flex-basis: 100%; max-width: none; } }
    .title-wrap { display: flex; align-items: baseline; gap: 0.5rem; }
    .title { font-size: 15px; font-weight: 600; line-height: 1; margin: 0; }
    .title-count { font-size: 12px; font-weight: 500; color: var(--color-muted); }

    /* Botón de herramienta cuadrado (filtros/import/export), look del Hub: 36×36, badge contador. */
    .toolbtn { position: relative; --padding-start: 0; --padding-end: 0; --border-radius: 10px; width: 36px; height: 36px; margin: 0; }
    .toolbtn .badge { position: absolute; top: -5px; right: -5px; min-width: 16px; height: 16px; padding: 0 3px; border-radius: 999px; background: var(--primary); color: var(--primary-contrast); font-size: 10px; font-weight: 700; line-height: 16px; text-align: center; pointer-events: none; }

    /* Buscador (caja con icono + limpiar), look del Hub. No crece (el spacer se queda el hueco);
     * puede encoger hasta min-width y, por debajo, envuelve. */
    .search { flex: 0 1 22rem; min-width: 12rem; max-width: 24rem; }
    ion-searchbar { --background: var(--background); --border-radius: 10px; padding: 0; min-height: 36px; }
    /* Flat: el buscador quita borde y elevación vía la clase específica de Ionic 'ion-no-border'.
     * (La regla global de Ionic para .ion-no-border no cruza el Shadow DOM, así que la
     * reimplementamos aquí dentro: --box-shadow controla la elevación; ::part(native) el borde.) */
    ion-searchbar.ion-no-border { --box-shadow: none; }
    ion-searchbar.ion-no-border::part(native) { border: none; box-shadow: none; }

    /* Toggle de vista lista/tarjetas (segmento) */
    .viewseg { display: inline-flex; align-items: center; gap: 2px; padding: 2px; border: 1px solid var(--border-color); border-radius: 10px; background: var(--background); }
    .viewseg ion-button { --border-radius: 7px; }

    /* Botón primario (primaryAction) */
    .primary-btn { --background: var(--primary); --color: var(--primary-contrast); }

    /* Selects de la toolbar: fondo + borde visibles (como el buscador y la pastilla de fechas) para
     * que se distingan como controles en claro y oscuro (sin fondo eran invisibles en dark). */
    .tk-cols { min-width: 6.5rem; max-width: 9rem; min-height: 38px; font-size: 13px; background: var(--background); color: var(--color); border: 1px solid var(--control-border); border-radius: 10px; --padding-start: 0.6rem; --padding-end: 0.4rem; --padding-top: 0.3rem; --padding-bottom: 0.3rem; }
    .vsep { width: 1px; align-self: stretch; background: var(--border-color); margin: 0.3rem 0.25rem; }

    /* Selector de filas/página en la toolbar (consolidado) */
    /* max-width: ion-select es display:block (sin core.css el host estira a la
     * línea entera cuando .bar-end hace wrap) — se capa como .tk-cols. */
    .tk-psize { min-width: 4.25rem; max-width: 5.5rem; min-height: 38px; font-size: 13px; background: var(--background); color: var(--color); border: 1px solid var(--control-border); border-radius: 10px; --padding-start: 0.6rem; --padding-end: 0.4rem; --padding-top: 0.35rem; --padding-bottom: 0.35rem; }

    /* Filtros EN LÍNEA en la toolbar (select / rango de fechas) */
    .tk-filter { min-width: 8.5rem; max-width: 13rem; min-height: 38px; font-size: 13px; background: var(--background); color: var(--color); border: 1px solid var(--control-border); border-radius: 10px; --padding-start: 0.7rem; --padding-end: 0.5rem; --padding-top: 0.35rem; --padding-bottom: 0.35rem; }
    .tk-daterange { display: inline-flex; align-items: center; gap: 0.35rem; padding: 0.3rem 0.6rem; min-height: 38px; border: 1px solid var(--control-border); border-radius: 10px; background: var(--background); color: var(--color-muted); font-size: 13px; }
    .tk-daterange ion-icon { font-size: 15px; flex: 0 0 auto; }
    .tk-daterange ion-input { --background: transparent; --padding-start: 0; --padding-end: 0; --padding-top: 2px; --padding-bottom: 2px; --color: var(--color); min-height: 26px; width: 6.8rem; font-size: 13px; }
    .tk-daterange .arr { color: var(--color-muted); }

    /* Barra contextual de selección */
    .selbar { display: flex; align-items: center; gap: 0.6rem; padding: 0.4rem 0.7rem; border-radius: 10px;
      font-size: 13px; color: var(--primary);
      background: color-mix(in srgb, var(--primary) 12%, transparent); }
    .selbar .sel-clear { margin-left: auto; display: inline-flex; align-items: center; gap: 0.25rem; cursor: pointer; font-weight: 500; color: inherit; background: none; border: 0; font: inherit; }
    .selbar .sel-clear:hover { text-decoration: underline; }

    /* Acordeones (alta / filtros en modo tarjetas) */
    .panel { padding: 0.85rem 1rem; border-bottom: 1px solid var(--border-color); background: var(--header-background); }
    .filters-panel { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 0.6rem; }

    /* ── Vista lista en CSS GRID (no <table>): permite ancho por columna ──────────────────── */
    .scroll { overflow-x: auto; }
    .grid { min-width: max-content; font-size: 14px; }
    .grow { display: grid; align-items: center; gap: 0.5rem; padding: 0 1rem; }
    .ghead { position: sticky; top: 0; z-index: 2; border-bottom: 1px solid var(--border-color);
      background: var(--header-background); padding-top: 0.55rem; padding-bottom: 0.55rem; }
    .gcell { display: flex; align-items: center; min-width: 0; }
    .gcell > span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .gcell.right { justify-content: flex-end; text-align: right; }
    .gcell.center { justify-content: center; text-align: center; }
    .gh { font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; color: var(--color-muted); }
    .gh.sortable { cursor: pointer; user-select: none; white-space: nowrap; transition: background-color var(--ok-transition, 150ms ease), color var(--ok-transition, 150ms ease), box-shadow var(--ok-transition, 150ms ease), transform 120ms ease; }
    @media (hover: hover) {
      .gh.sortable:hover { color: var(--color); }
    }
    /* Caret de orden (3 estados, icono Ionic): neutral atenuado / activo en color primario. */
    .caret { display: inline-flex; align-items: center; margin-left: 0.25rem; flex: 0 0 auto; font-size: 13px; opacity: 0.3; }
    .caret.on { opacity: 1; color: var(--primary); }
    .grow-data { border-bottom: 1px solid var(--border-color-soft); padding-top: 0.6rem; padding-bottom: 0.6rem; transition: background-color var(--ok-transition, 150ms ease), color var(--ok-transition, 150ms ease), box-shadow var(--ok-transition, 150ms ease), transform 120ms ease; }
    .grow-data:last-child { border-bottom: 0; }
    @media (hover: hover) {
      .grow-data:hover { background: var(--row-hover); }
    }
    .grow-data:active { transform: scale(0.995); }
    .grow-data.selected { background: color-mix(in srgb, var(--primary) 10%, transparent); }
    .selcb { display: flex; align-items: center; justify-content: center; }
    .filters-grow { padding-top: 0.4rem; padding-bottom: 0.6rem; }
    .filters-grow input, .filters-grow select { width: 100%; box-sizing: border-box; font: inherit; font-size: 13px; padding: 0.3rem 0.4rem; border: 1px solid var(--border-color); border-radius: 6px; background: var(--background); color: var(--color); }
    .range { display: flex; gap: 0.25rem; }

    /* ── Vista tarjetas ──────────────────────────────────────────────────────────────────── */
    .cards-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap: 0.75rem; padding: 1rem; }
    /* Flat: sin borde ni elevación — las tarjetas se delimitan por la superficie (no por sombra). */
    .rcard { display: flex; flex-direction: column; border: 0; border-radius: 12px; overflow: hidden; background: var(--header-background); box-shadow: none; transition: background-color var(--ok-transition, 150ms ease), color var(--ok-transition, 150ms ease), box-shadow var(--ok-transition, 150ms ease), transform 120ms ease; }
    @media (hover: hover) {
      .rcard:hover { background: var(--row-hover); }
    }
    .rcard:active { transform: scale(0.995); }
    @media (prefers-reduced-motion: reduce) {
      .gh.sortable:hover, .gh.sortable:active,
      .grow-data:hover, .grow-data:active,
      .rcard:hover, .rcard:active { transform: none; }
    }
    .rcard.selected { background: color-mix(in srgb, var(--primary) 12%, var(--header-background)); }
    .rcard-head { display: flex; align-items: center; gap: 0.5rem; padding: 0.55rem 0.75rem; border-bottom: 1px solid var(--border-color); background: var(--header-background); }
    .rcard-head .rc-icon { display: inline-flex; color: var(--primary); }
    .rcard-head .rc-title { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 600; }
    .rcard-body { flex: 1; padding: 0.6rem 0.85rem; display: flex; flex-direction: column; gap: 0.4rem; }
    .rrow { display: flex; justify-content: space-between; gap: 0.5rem; font-size: 13px; }
    .rrow .rk { color: var(--color-muted); }
    .rrow .rv { font-weight: 500; text-align: right; }
    .ractions { display: flex; justify-content: flex-end; gap: 0.25rem; padding: 0.25rem 0.5rem; border-top: 1px solid var(--border-color-soft); background: var(--header-background); }

    /* ── Estado vacío ────────────────────────────────────────────────────────────────────── */
    .empty { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 0.75rem; padding: 3.5rem 1rem; text-align: center; color: var(--color-muted); }
    .empty .empty-ic { display: grid; place-items: center; width: 3.25rem; height: 3.25rem; border-radius: 999px; background: var(--header-background); font-size: 26px; }

    .actions { display: flex; gap: 0.25rem; justify-content: flex-end; }

    /* ── Pie: contador + paginación ──────────────────────────────────────────────────────── */
    .pager { display: flex; align-items: center; justify-content: space-between; gap: 0.75rem; padding: 0.55rem 1rem; border-top: 1px solid var(--border-color); background: var(--header-background); font-size: 12.5px; color: var(--color-muted); }
    .pager .left { display: flex; align-items: center; gap: 0.6rem; }
    .pager .strong { font-weight: 600; color: var(--color); }
    .psize { font: inherit; font-size: 12.5px; padding: 0.2rem 0.35rem; border: 1px solid var(--border-color); border-radius: 6px; background: var(--background); color: var(--color); }
    .pager .nav { display: flex; align-items: center; gap: 0.2rem; }
    .pager .nav .pp { font-weight: 600; color: var(--color); padding: 0 0.25rem; }
    /* Pager numerado: botón por página + «…» en los saltos (look del Hub). */
    .pnum { min-width: 1.75rem; height: 1.75rem; padding: 0 0.4rem; border: 1px solid transparent; border-radius: 8px; background: none; font: inherit; font-size: 12.5px; font-weight: 600; color: var(--color); cursor: pointer; transition: background 0.12s, border-color 0.12s; }
    .pnum:hover { background: var(--row-hover); }
    .pnum.on { background: color-mix(in srgb, var(--primary) 14%, transparent); color: var(--primary); border-color: color-mix(in srgb, var(--primary) 40%, transparent); }
    .pgap { padding: 0 0.15rem; color: var(--color-muted); }
    ion-button { --box-shadow: none; }
  `;

  /** Columnas a renderizar. */
  @property({ attribute: false }) columns: DataTableColumn[] = [];
  /** Filas (objetos planos). En modo servidor, solo las de la página actual. */
  @property({ attribute: false }) rows: Record<string, unknown>[] = [];
  /** (cliente) Campos sobre los que filtra el buscador en memoria. Vacío = sin buscador. */
  @property({ attribute: false }) searchKeys: string[] = [];
  /** Campo usado como key estable de fila. */
  @property({ attribute: 'row-key-field' }) rowKeyField = 'id';
  /** (NUEVO, opcional) Clave estable de fila: nombre de campo o función. Tiene prioridad sobre
   *  `rowKeyField`; por defecto usa `row.id` (vía `rowKeyField`). Se usa para selección y `repeat`. */
  @property({ attribute: false }) rowKey?: DataTableRowKey;
  /** Filas por página. */
  @property({ type: Number, attribute: 'page-size' }) pageSize = 10;
  /** Mensaje cuando no hay filas. Si no se pasa, deriva de `this.t.empty` (inglés por defecto). */
  @property({ attribute: 'empty-message' }) emptyMessage?: string;
  /** Placeholder del buscador. Si no se pasa, deriva de `this.t.search` (inglés por defecto). */
  @property({ attribute: 'search-placeholder' }) searchPlaceholder?: string;
  /** (NUEVO, additivo) Textos humanos del data-table para i18n (parcial). Lo no pasado cae al
   *  default inglés (`DEFAULT_LABELS`). No afecta a columns/rows/options (ya externos). */
  @property({ attribute: false }) labels: Partial<OkDataTableLabels> = {};
  /** Acciones por fila (botones). */
  @property({ attribute: false }) actions: DataTableAction[] = [];
  /** Muestra el botón "+" que despliega un acordeón con el slot `create` (formulario de alta). */
  @property({ type: Boolean }) addable = false;
  /** Opciones del selector de "filas por página". Vacío = sin selector. */
  @property({ attribute: false }) pageSizeOptions: number[] = [10, 25, 50, 100];
  /** Modo "llenar el contenedor": la tabla ocupa el alto disponible, las filas hacen scroll DENTRO
   *  (cabecera sticky) y el pager queda SIEMPRE visible. Requiere que el contenedor tenga alto. */
  @property({ type: Boolean, reflect: true }) fill = false;
  /** Muestra un multiselect (ion-select) en la barra para elegir qué columnas se ven.
   *  Default ON (2026-06-14): toda tabla trae el selector de columnas. Para ocultarlo,
   *  pon la PROPIEDAD a false (`el.columnPicker = false`); el atributo booleano no puede
   *  apagar un default true (cualquier valor presente cuenta como true en Lit). */
  @property({ type: Boolean, attribute: 'column-picker' }) columnPicker = true;
  /** Muestra botones de import/export CSV en la barra. Export vacío = solo cabeceras (estructura). */
  @property({ type: Boolean }) csv = false;
  /** Nombre del fichero de export CSV. */
  @property({ attribute: 'csv-name' }) csvName = 'export.csv';

  // ── Modo servidor ───────────────────────────────────────────────────────────────────────
  /** Activa el modo servidor: no filtra/pagina en memoria, solo emite eventos. */
  @property({ type: Boolean, attribute: 'server-side' }) serverSide = false;
  /** (server) Total de filas filtradas (lo da el runtime) para calcular el nº de páginas. */
  @property({ type: Number }) total = 0;
  /** (server) Página actual (0-based), controlada por el padre. */
  @property({ type: Number }) page = 0;
  /** (server) Muestra el buscador aunque no haya `searchKeys` (búsqueda server-side). */
  @property({ type: Boolean }) searchable = false;
  /** (server) Columna de orden activa. */
  @property({ type: String }) sort?: string;
  /** (server) Dirección del orden activo. */
  @property({ attribute: 'sort-dir' }) sortDir: 'asc' | 'desc' = 'asc';

  // ── NUEVO (todo opcional, retrocompatible) ────────────────────────────────────────────────
  /** (NUEVO) Título de la cabecera (a la izquierda, junto al contador de registros).
   *  Tipo `string` (no opcional) para no chocar con `HTMLElement.title`; '' = sin título. */
  @property() title = '';
  /** (NUEVO) Conmutador de vista lista/tarjetas. Acepta `true` (= ['table','cards']) o un array de
   *  vistas. La presencia de 'cards' (o 'card') habilita la vista tarjetas. Compatibilidad: el
   *  antiguo valor booleano sigue funcionando. */
  @property({ attribute: false }) views: boolean | string[] = false;
  /** (NUEVO, alias documentado) Habilita import/export CSV (equivalente a `exportable`+`importable`
   *  / `csv`). Mostrar el botón de Exportar. */
  @property({ type: Boolean }) exportable = false;
  /** (NUEVO) Mostrar el botón de Importar CSV. */
  @property({ type: Boolean }) importable = false;
  /** (NUEVO, alias) Selector de columnas (equivalente a `columnPicker`). */
  @property({ type: Boolean, attribute: 'column-selector' }) columnSelector = false;
  /** (NUEVO, alias) Opciones del selector de "filas por página" (equivalente a `pageSizeOptions`). */
  @property({ attribute: false }) pageSizes?: number[];

  /** (NUEVO) Selección de filas con checkbox por fila + seleccionar-todo + barra contextual. */
  @property({ type: Boolean }) selectable = false;
  /** (NUEVO) Conjunto de keys seleccionadas (controlado por el padre o interno). */
  @property({ attribute: false }) selectedKeys?: Set<string>;

  /** (NUEVO) Acción primaria de la topbar (botón destacado). Emite `primaryAction`. */
  @property({ attribute: false }) primaryAction?: DataTablePrimaryAction;

  /** (NUEVO) Filtros EN LÍNEA en la toolbar (selects/daterange/text compactos) en vez del botón
   *  funnel + drawer. Opt-in (por defecto `false` → se conserva el drawer). Look del screenshot:
   *  «Todos los Estados» · «Todos los tipos» · rango de fechas, todo en una línea con el buscador.
   *  Emite `filterChange` igual que el drawer. */
  @property({ type: Boolean }) inlineFilters = false;
  /** (NUEVO) Acciones del menú overflow (botón «⋮»). Emite `menuAction` con `{ actionId }`. */
  @property({ attribute: false }) menuActions: DataTableAction[] = [];

  /** (NUEVO) Cabecera de la tarjeta: título (string/HTML). Si se omite, no hay cabecera de título. */
  @property({ attribute: false }) cardTitle?: (row: Record<string, unknown>) => unknown;
  /** (NUEVO) Cabecera de la tarjeta: nombre de un ion-icon o TemplateResult. */
  @property({ attribute: false }) cardIcon?: (row: Record<string, unknown>) => unknown;
  /** (NUEVO) Cuerpo a medida de la tarjeta (string/HTML). Si se omite, se listan los campos. */
  @property({ attribute: false }) renderCard?: (row: Record<string, unknown>) => unknown;

  // Estado interno SOLO del modo cliente.
  @state() private q = '';
  @state() private clientPage = 0;
  @state() private clientPageSize = 0; // 0 = usa `pageSize`
  // Orden en memoria (modo cliente): columna activa + dirección. Vacío = sin orden.
  @state() private clientSort = '';
  @state() private clientSortDir: 'asc' | 'desc' = 'asc';
  // Filtros en memoria (modo cliente): por columna, multi-select (Set de valores) o rango de fechas.
  @state() private clientFilters: Record<string, { values?: Set<string>; from?: string; to?: string }> = {};
  // Borrador del panel de filtros (se aplica con "Aplicar"; replica el modal del Hub).
  @state() private filterDraft: Record<string, { values?: Set<string>; from?: string; to?: string }> = {};
  // Panel lateral derecho (drawer) DENTRO de la tabla: filtros o alta/edición. No empuja la tabla;
  // funciona igual en vista lista y tarjetas. Inspirado en el Filters Tool Panel de AG Grid.
  @state() private panel: 'none' | 'filters' | 'create' = 'none';
  @state() private viewMode: 'table' | 'cards' = 'table';
  // Columnas ocultas por el usuario (column chooser). Vacío = todas visibles.
  @state() private hiddenKeys = new Set<string>();
  // Selección interna (cuando el padre no controla `selectedKeys`).
  @state() private internalSelection = new Set<string>();
  // Menú overflow («⋮»): abierto/cerrado + evento de anclaje del ion-popover (sin trigger-by-id, que
  // no resuelve dentro de Shadow DOM → se ancla con `.event`).
  @state() private menuOpen = false;
  private menuEv?: Event;

  // ── i18n: textos efectivos (default inglés ← overrides de `.labels`) ──────────────────────
  private get t(): OkDataTableLabels {
    return { ...DEFAULT_LABELS, ...this.labels };
  }
  /** Placeholder efectivo del buscador (prop explícita → label i18n → default inglés). */
  private get effSearchPlaceholder(): string {
    return this.searchPlaceholder ?? this.t.search;
  }
  /** Mensaje efectivo de estado vacío (prop explícita → label i18n → default inglés). */
  private get effEmptyMessage(): string {
    return this.emptyMessage ?? this.t.empty;
  }

  // ── Resolución de alias (compat + documentados) ──────────────────────────────────────────
  private get effPageSizes(): number[] {
    return this.pageSizes ?? this.pageSizeOptions;
  }
  private get effColumnPicker(): boolean {
    return this.columnPicker || this.columnSelector;
  }
  private get effExport(): boolean {
    return this.csv || this.exportable;
  }
  private get effImport(): boolean {
    return this.csv || this.importable;
  }
  /** ¿Está habilitado el conmutador de vista lista/tarjetas? */
  private get viewToggle(): boolean {
    if (Array.isArray(this.views)) return this.views.length > 1;
    return this.views === true;
  }
  /** ¿Está disponible la vista tarjetas? (presente en `views` o `views === true`). */
  private get cardViewEnabled(): boolean {
    if (Array.isArray(this.views)) return this.views.some((v) => v === 'cards' || v === 'card');
    return this.views === true;
  }

  /** Columnas actualmente visibles (respeta el column chooser). */
  private get visibleColumns(): DataTableColumn[] {
    return this.hiddenKeys.size ? this.columns.filter((c) => !this.hiddenKeys.has(c.key)) : this.columns;
  }
  private setVisibleColumns(keys: string[]): void {
    const visible = new Set(keys);
    this.hiddenKeys = new Set(this.columns.map((c) => c.key).filter((k) => !visible.has(k)));
    this.emit('columnsChange', { visible: keys });
  }

  // ── Selección ─────────────────────────────────────────────────────────────────────────────
  private keyOf(row: Record<string, unknown>): string {
    if (typeof this.rowKey === 'function') return String(this.rowKey(row) ?? '');
    if (typeof this.rowKey === 'string') return String(row[this.rowKey] ?? '');
    return String(row[this.rowKeyField] ?? '');
  }
  private get selection(): Set<string> {
    return this.selectedKeys ?? this.internalSelection;
  }
  private setSelection(next: Set<string>): void {
    if (!this.selectedKeys) this.internalSelection = next; // no controlado → estado propio
    this.emit('selectionChange', { keys: [...next] });
    this.requestUpdate();
  }
  private toggleRow(key: string): void {
    const next = new Set(this.selection);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    this.setSelection(next);
  }
  private toggleAll(visible: Record<string, unknown>[]): void {
    const keys = visible.map((r) => this.keyOf(r));
    const allOn = keys.length > 0 && keys.every((k) => this.selection.has(k));
    const next = new Set(this.selection);
    if (allOn) keys.forEach((k) => next.delete(k));
    else keys.forEach((k) => next.add(k));
    this.setSelection(next);
  }

  // ── CSV ─────────────────────────────────────────────────────────────────────────────────────
  private csvEscape(v: unknown): string {
    const s = v === null || v === undefined ? '' : String(v);
    return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  }
  /** Exporta las filas a CSV (cabeceras = column.key). Si no hay filas, exporta solo la estructura. */
  private exportCsv(): void {
    const cols = this.columns;
    const head = cols.map((c) => this.csvEscape(c.key)).join(',');
    const lines = this.rows.map((r) => cols.map((c) => this.csvEscape(r[c.key])).join(','));
    const csv = [head, ...lines].join('\r\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = this.csvName;
    a.click();
    URL.revokeObjectURL(url);
    this.emit('csvExport', { rows: this.rows.length });
    this.emit('export', { rows: this.rows.length });
  }
  private parseCsv(text: string): { headers: string[]; rows: Record<string, string>[] } {
    const out: string[][] = [];
    let row: string[] = [];
    let field = '';
    let q = false;
    for (let i = 0; i < text.length; i++) {
      const c = text[i];
      if (q) {
        if (c === '"') {
          if (text[i + 1] === '"') { field += '"'; i++; } else q = false;
        } else field += c;
      } else if (c === '"') q = true;
      else if (c === ',') { row.push(field); field = ''; }
      else if (c === '\n' || c === '\r') {
        if (c === '\r' && text[i + 1] === '\n') i++;
        row.push(field); field = '';
        if (row.length > 1 || row[0] !== '') out.push(row);
        row = [];
      } else field += c;
    }
    if (field !== '' || row.length) { row.push(field); out.push(row); }
    const headers = out.shift() ?? [];
    const rows = out.map((r) => Object.fromEntries(headers.map((h, i) => [h, r[i] ?? ''])));
    return { headers, rows };
  }
  private async onImportFile(ev: Event): Promise<void> {
    const input = ev.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    const text = await file.text();
    const { headers, rows } = this.parseCsv(text);
    this.emit('csvImport', { headers, rows });
    this.emit('import', { headers, rows });
    input.value = '';
  }

  private toggle(p: 'filters' | 'create'): void {
    if (p === 'filters' && this.panel !== 'filters') {
      // Al abrir el panel de filtros (modo cliente) clonamos el estado aplicado como borrador.
      this.filterDraft = this.cloneFilters(this.clientFilters);
    }
    this.panel = this.panel === p ? 'none' : p;
  }

  // ── Filtros en memoria (modo cliente): borrador → aplicar. ───────────────────────────────────
  private cloneFilters(src: Record<string, { values?: Set<string>; from?: string; to?: string }>) {
    const out: Record<string, { values?: Set<string>; from?: string; to?: string }> = {};
    for (const [k, f] of Object.entries(src)) {
      out[k] = { values: f.values ? new Set(f.values) : undefined, from: f.from, to: f.to };
    }
    return out;
  }
  private toggleFilterValue(key: string, value: string): void {
    const next = this.cloneFilters(this.filterDraft);
    const values = new Set(next[key]?.values ?? []);
    if (values.has(value)) values.delete(value);
    else values.add(value);
    next[key] = { ...next[key], values };
    this.filterDraft = next;
  }
  private setFilterRange(key: string, edge: 'from' | 'to', value: string): void {
    const next = this.cloneFilters(this.filterDraft);
    next[key] = { ...next[key], [edge]: value };
    this.filterDraft = next;
  }
  private applyFilters(): void {
    // Descarta entradas vacías para que `activeFilterCount` sea fiel.
    const clean: Record<string, { values?: Set<string>; from?: string; to?: string }> = {};
    for (const [k, f] of Object.entries(this.filterDraft)) {
      if ((f.values && f.values.size > 0) || f.from || f.to) clean[k] = f;
    }
    this.clientFilters = clean;
    this.clientPage = 0;
    this.panel = 'none';
    this.emit('filterChange', { filters: this.serializeFilters(clean) });
  }
  private clearFilters(): void {
    this.filterDraft = {};
  }
  private serializeFilters(src: Record<string, { values?: Set<string>; from?: string; to?: string }>) {
    const out: Record<string, unknown> = {};
    for (const [k, f] of Object.entries(src)) {
      if (f.values && f.values.size > 0) out[k] = [...f.values];
      else if (f.from || f.to) out[k] = { from: f.from ?? '', to: f.to ?? '' };
    }
    return out;
  }
  /** Abre el panel lateral (API pública para el módulo, p.ej. "editar" abre el form pre-rellenado). */
  open(panel: 'filters' | 'create' = 'create'): void {
    this.panel = panel;
  }
  /** Cierra el panel lateral. */
  close(): void {
    this.panel = 'none';
  }

  private emit<T>(type: string, detail: T): void {
    this.dispatchEvent(new CustomEvent<T>(type, { detail, bubbles: true, composed: true }));
  }

  private get hasSearch(): boolean {
    return this.searchable || this.searchKeys.length > 0;
  }

  /** Columnas filtrables (con control en el panel de filtros). En cliente y en servidor. */
  private get filterColumns(): DataTableColumn[] {
    return this.columns.filter((c) => c.filterable);
  }

  /** ¿Hay que mostrar el botón de Filtros? (cualquier columna filtrable). */
  private get hasFilterRow(): boolean {
    return this.filterColumns.length > 0;
  }

  /** Nº de filtros activos (modo cliente) → badge del botón Filtros. */
  private get activeFilterCount(): number {
    return Object.values(this.clientFilters).filter(
      (f) => (f.values && f.values.size > 0) || f.from || f.to,
    ).length;
  }

  /** Valor crudo de una columna para ordenar/filtrar (usa format si lo hay, si no row[key]). */
  private rawValue(col: DataTableColumn, row: Record<string, unknown>): unknown {
    if (col.format) return col.format(row);
    return row[col.key];
  }

  /** Valores distintos de una columna (para los chips del filtro multi-select). */
  private distinctValues(col: DataTableColumn): string[] {
    const set = new Set<string>();
    for (const row of this.rows) {
      const v = this.rawValue(col, row);
      if (v != null && v !== '') set.add(String(v));
    }
    return [...set].sort((a, b) => a.localeCompare(b));
  }

  /** Filas tras buscar + filtrar + ordenar EN MEMORIA (solo modo cliente). */
  private get clientFiltered(): Record<string, unknown>[] {
    let result: Record<string, unknown>[] = this.rows;

    // 1) Búsqueda global por searchKeys.
    const needle = this.q.trim().toLowerCase();
    if (needle && this.searchKeys.length) {
      result = result.filter((r) =>
        this.searchKeys.some((k) => String(r[k] ?? '').toLowerCase().includes(needle)),
      );
    }

    // 2) Filtros por columna (multi-select por valores + rango de fechas).
    const fkeys = Object.keys(this.clientFilters);
    if (fkeys.length) {
      result = result.filter((row) =>
        fkeys.every((key) => {
          const f = this.clientFilters[key];
          const col = this.columns.find((c) => c.key === key);
          if (!col) return true;
          if (f.values && f.values.size > 0) {
            return f.values.has(String(this.rawValue(col, row) ?? ''));
          }
          if (f.from || f.to) {
            const raw = this.rawValue(col, row);
            const t = raw == null ? NaN : new Date(raw as string).getTime();
            const from = f.from ? new Date(f.from).getTime() : -Infinity;
            const to = f.to ? new Date(f.to).getTime() + 86_400_000 - 1 : Infinity;
            return !Number.isNaN(t) && t >= from && t <= to;
          }
          return true;
        }),
      );
    }

    // 3) Orden por columna (solo si hay una activa; no muta `this.rows`).
    if (this.clientSort) {
      const col = this.columns.find((c) => c.key === this.clientSort);
      if (col) {
        const dir = this.clientSortDir === 'asc' ? 1 : -1;
        result = [...result].sort((a, b) => {
          const va = this.rawValue(col, a);
          const vb = this.rawValue(col, b);
          if (va == null) return 1;
          if (vb == null) return -1;
          if (va < vb) return -1 * dir;
          if (va > vb) return 1 * dir;
          return 0;
        });
      }
    }

    return result;
  }

  private cell(col: DataTableColumn, row: Record<string, unknown>): string {
    if (col.format) return col.format(row);
    const v = row[col.key];
    return v === null || v === undefined ? '' : String(v);
  }

  private onSearch = (ev: Event): void => {
    const value = (ev.target as HTMLInputElement).value ?? '';
    if (this.serverSide) {
      this.emit('searchChange', value);
    } else {
      this.q = value;
      this.clientPage = 0;
    }
  };

  /** ¿Es ordenable la columna? Servidor: opt-in (`sortable`). Cliente: por defecto SÍ (como el Hub),
   *  salvo `sortable: false` explícito. */
  private isSortable(col: DataTableColumn): boolean {
    return this.serverSide ? !!col.sortable : col.sortable !== false;
  }

  private onHeaderClick(col: DataTableColumn): void {
    if (!this.isSortable(col)) return;
    if (this.serverSide) {
      const dir = this.sort === col.key && this.sortDir === 'asc' ? 'desc' : 'asc';
      this.emit('sortChange', { sort: col.key, dir });
      return;
    }
    // Cliente: alterna asc/desc en memoria.
    if (this.clientSort === col.key) {
      this.clientSortDir = this.clientSortDir === 'asc' ? 'desc' : 'asc';
    } else {
      this.clientSort = col.key;
      this.clientSortDir = 'asc';
    }
  }

  private onFilterInput(col: DataTableColumn, ev: Event): void {
    const value = (ev.target as HTMLInputElement | HTMLSelectElement).value ?? '';
    this.emit('filterChange', { col: col.key, value });
  }

  private onRangeInput(col: DataTableColumn, edge: 'from' | 'to', ev: Event): void {
    const raw = (ev.target as HTMLInputElement).value ?? '';
    // Rango numérico: emite Number para que el runtime compare con el tipo real (`>=`/`<=`).
    const v = raw === '' ? '' : Number(raw);
    this.emit('filterChange', { col: col.key, value: { [edge]: v } });
  }

  private onDateRangeInput(col: DataTableColumn, edge: 'from' | 'to', ev: Event): void {
    // Rango de fechas: emite el string ISO (YYYY-MM-DD); el runtime compara texto (cronológico).
    const v = (ev.target as HTMLInputElement).value ?? '';
    this.emit('filterChange', { col: col.key, value: { [edge]: v } });
  }

  // ── Filtros EN LÍNEA (toolbar) ────────────────────────────────────────────────────────────
  // En modo cliente escriben directamente `clientFilters` (filtran en memoria); en servidor solo
  // emiten `filterChange`. Reutilizan la misma forma de filtro que el drawer (values / from / to).
  private setClientFilter(key: string, patch: { values?: Set<string>; from?: string; to?: string }): void {
    const next = { ...this.clientFilters };
    const merged = { ...next[key], ...patch };
    const empty = (!merged.values || merged.values.size === 0) && !merged.from && !merged.to;
    if (empty) delete next[key];
    else next[key] = merged;
    this.clientFilters = next;
    this.clientPage = 0;
  }
  // ion-select (select/multiselect) del panel de filtros (renderFilterControl). En servidor emite
  // `filterChange`; en cliente escribe `clientFilters` (multiselect ⇒ filtra por inclusión).
  private onFilterSelect(col: DataTableColumn, value: unknown, multi: boolean): void {
    if (this.serverSide) {
      this.emit('filterChange', { col: col.key, value: value ?? (multi ? [] : '') });
      return;
    }
    if (multi) {
      const arr = Array.isArray(value) ? value.map((v) => String(v)) : value != null && value !== '' ? [String(value)] : [];
      this.setClientFilter(col.key, { values: arr.length ? new Set(arr) : undefined });
    } else {
      const v = String(value ?? '');
      this.setClientFilter(col.key, { values: v ? new Set([v]) : undefined });
    }
  }
  private onInlineRange(col: DataTableColumn, edge: 'from' | 'to', ev: Event): void {
    const v = (ev.target as HTMLInputElement).value ?? '';
    if (this.serverSide) {
      this.emit('filterChange', { col: col.key, value: { [edge]: v } });
      return;
    }
    this.setClientFilter(col.key, { [edge]: v || undefined });
  }

  // Menú overflow: ancla el popover al botón vía el evento de click (compatible con Shadow DOM).
  private openMenu(ev: Event): void {
    this.menuEv = ev;
    this.menuOpen = true;
  }

  private setViewMode(mode: 'table' | 'cards'): void {
    if (this.viewMode === mode) return;
    this.viewMode = mode;
    this.emit('viewChange', mode);
  }

  // Control de filtro de una columna, con componentes Ionic (mismos inputs que el form de alta).
  private renderFilterControl(col: DataTableColumn): unknown {
    if (!col.filterable) return nothing;
    const type = col.filterType ?? 'text';
    if (type === 'select' || type === 'multiselect') {
      const multi = type === 'multiselect';
      const opts = col.options ?? this.distinctValues(col).map((v) => ({ value: v, label: v }));
      return html`
        <ion-select
          label=${col.header}
          label-placement="stacked"
          ?multiple=${multi}
          interface="modal"
          .interfaceOptions=${{ cssClass: 'ok-overlay' }}
          placeholder=${col.header}
          @ionChange=${(e: CustomEvent) => this.onFilterSelect(col, (e.detail as { value: unknown }).value, multi)}
        >
          ${multi ? nothing : html`<ion-select-option value="">${col.header}</ion-select-option>`}
          ${opts.map((o) => html`<ion-select-option value=${o.value}>${o.label}</ion-select-option>`)}
        </ion-select>
      `;
    }
    if (type === 'range' || type === 'daterange') {
      const t = type === 'daterange' ? 'date' : 'number';
      const onEdge = type === 'daterange' ? this.onDateRangeInput.bind(this) : this.onRangeInput.bind(this);
      return html`
        <div class="fblock">
          <span class="flabel">${col.header}</span>
          <div class="frange">
            <ion-input type=${t} fill="outline" placeholder=${type === 'daterange' ? this.t.from : this.t.gte}
              @ionInput=${(e: Event) => onEdge(col, 'from', e)}></ion-input>
            <ion-input type=${t} fill="outline" placeholder=${type === 'daterange' ? this.t.to : this.t.lte}
              @ionInput=${(e: Event) => onEdge(col, 'to', e)}></ion-input>
          </div>
        </div>
      `;
    }
    const inputType = type === 'number' ? 'number' : type === 'date' ? 'date' : 'text';
    return html`
      <ion-input
        type=${inputType}
        fill="outline"
        label=${col.header}
        label-placement="stacked"
        placeholder=${this.t.filterPlaceholder}
        @ionInput=${(e: Event) => this.onFilterInput(col, e)}
      ></ion-input>
    `;
  }

  // Controles de filtro COMPACTOS para la toolbar (modo `inlineFilters`). Solo select y rango de
  // fechas (los del screenshot); el resto de tipos siguen disponibles vía el drawer si no se activa
  // `inlineFilters`. Look: «Todos los Estados» (placeholder) / «01/10/25 → 18/10/25».
  private renderInlineFilters(): unknown {
    const cols = this.filterColumns.filter((c) => {
      const t = c.filterType ?? 'text';
      return t === 'select' || t === 'multiselect' || t === 'date' || t === 'daterange';
    });
    if (!cols.length) return nothing;
    return html`${cols.map((c) => this.renderInlineFilter(c))}`;
  }
  private renderInlineFilter(col: DataTableColumn): unknown {
    const type = col.filterType ?? 'text';
    const f = this.clientFilters[col.key];
    if (type === 'select' || type === 'multiselect') {
      const multi = type === 'multiselect';
      const opts = col.options ?? this.distinctValues(col).map((v) => ({ value: v, label: v }));
      const current = multi
        ? [...(f?.values ?? new Set<string>())]
        : f?.values && f.values.size
          ? [...f.values][0]
          : '';
      return html`
        <ion-select
          class="tk-filter"
          ?multiple=${multi}
          interface="modal"
          .interfaceOptions=${{ cssClass: 'ok-overlay' }}
          aria-label=${col.header}
          placeholder=${col.header}
          .value=${current}
          @ionChange=${(e: CustomEvent) => this.onFilterSelect(col, (e.detail as { value: unknown }).value, multi)}
        >
          ${multi ? nothing : html`<ion-select-option value="">${col.header}</ion-select-option>`}
          ${opts.map((o) => html`<ion-select-option value=${o.value}>${o.label}</ion-select-option>`)}
        </ion-select>
      `;
    }
    // date / daterange → pastilla compacta con icono calendario y dos ion-input (type=date).
    return html`
      <span class="tk-daterange" role="group" aria-label=${col.header}>
        <ion-icon name="calendar-outline"></ion-icon>
        <ion-input type="date" aria-label=${this.t.fromOf.replace('{label}', col.header)} .value=${f?.from ?? ''} @ionChange=${(e: Event) => this.onInlineRange(col, 'from', e)}></ion-input>
        <span class="arr">→</span>
        <ion-input type="date" aria-label=${this.t.toOf.replace('{label}', col.header)} .value=${f?.to ?? ''} @ionChange=${(e: Event) => this.onInlineRange(col, 'to', e)}></ion-input>
      </span>
    `;
  }

  // Menú overflow («⋮») con ion-popover anclado por evento (Shadow-DOM-safe).
  private renderOverflowMenu(): unknown {
    if (!this.menuActions.length) return nothing;
    return html`
      <ion-button class="toolbtn" fill="clear" aria-label=${this.t.moreActions} @click=${(e: Event) => this.openMenu(e)}>
        <ion-icon slot="icon-only" name="ellipsis-vertical"></ion-icon>
      </ion-button>
      <ion-popover
        .isOpen=${this.menuOpen}
        .event=${this.menuEv}
        dismiss-on-select="true"
        @didDismiss=${() => (this.menuOpen = false)}
      >
        <ion-content>
          <ion-list lines="none">
            ${this.menuActions.map(
              (a) => html`
                <ion-item button .detail=${false} @click=${() => { this.menuOpen = false; this.emit('menuAction', { actionId: a.id }); }}>
                  ${a.icon ? html`<ion-icon slot="start" name=${a.icon} color=${a.color ?? nothing}></ion-icon>` : nothing}
                  <ion-label color=${a.color ?? nothing}>${a.label}</ion-label>
                </ion-item>
              `,
            )}
          </ion-list>
        </ion-content>
      </ion-popover>
    `;
  }

  // Botones de acción de una fila (compartido por vista tabla y tarjetas).
  private actionButtons(row: Record<string, unknown>): unknown {
    if (!this.actions.length) return nothing;
    return html`
      <div class="actions">
        ${this.actions.map(
          (a) => html`
            <ion-button
              size="small"
              fill="clear"
              color=${a.color ?? 'medium'}
              @click=${() => this.emit('rowAction', { actionId: a.id, row })}
            >
              ${a.icon ? html`<ion-icon slot="icon-only" name=${a.icon}></ion-icon>` : a.label}
            </ion-button>
          `,
        )}
      </div>
    `;
  }

  // Botón de barra icon-only (filtros / alta / conmutador de vista). `on` = estado activo.
  // `badge` opcional → contador (p.ej. nº de filtros activos), look del Hub.
  private toolButton(icon: string, on: boolean, onClick: () => void, label: string, badge?: number): unknown {
    return html`
      <ion-button class="toolbtn" size="small" fill=${on ? 'solid' : 'outline'} title=${label} aria-label=${label} @click=${onClick}>
        <ion-icon slot="icon-only" name=${icon}></ion-icon>
        ${badge && badge > 0 ? html`<span class="badge">${badge}</span>` : nothing}
      </ion-button>
    `;
  }

  /** Plantilla de columnas del grid de la vista lista: [checkbox] [columnas…] [acciones]. */
  private gridTemplate(): string {
    return [
      this.selectable ? '2.75rem' : null,
      ...this.visibleColumns.map((c) => c.width ?? 'minmax(8rem,1fr)'),
      this.actions.length ? 'auto' : null,
    ].filter(Boolean).join(' ');
  }

  /** Lista de páginas a mostrar en el pager numerado (1-based): primera, última, vecinas de la
   *  actual y «…» donde haya saltos. P.ej. en página 1 de 52 → [1,2,3,'…',52]. */
  private pageList(cur1: number, total: number): (number | '…')[] {
    if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);
    const want = new Set<number>([1, total, cur1, cur1 - 1, cur1 + 1]);
    if (cur1 <= 3) [2, 3].forEach((p) => want.add(p)); // arranque: 1 2 3 … N
    if (cur1 >= total - 2) [total - 1, total - 2].forEach((p) => want.add(p)); // final: 1 … N-2 N-1 N
    const sorted = [...want].filter((p) => p >= 1 && p <= total).sort((a, b) => a - b);
    const out: (number | '…')[] = [];
    let prev = 0;
    for (const p of sorted) {
      if (p - prev > 1) out.push('…');
      out.push(p);
      prev = p;
    }
    return out;
  }

  render(): unknown {
    const ps = this.serverSide ? this.pageSize : this.clientPageSize || this.pageSize;
    let visible: Record<string, unknown>[];
    let pages: number;
    let current: number;
    let count: number;
    if (this.serverSide) {
      visible = this.rows;
      count = this.total;
      pages = Math.max(1, Math.ceil(this.total / ps));
      current = Math.min(this.page, pages - 1);
    } else {
      const filtered = this.clientFiltered;
      count = filtered.length;
      pages = Math.max(1, Math.ceil(filtered.length / ps));
      current = Math.min(this.clientPage, pages - 1);
      visible = filtered.slice(current * ps, current * ps + ps);
    }

    const goTo = (p: number): void => {
      if (this.serverSide) this.emit('pageChange', p);
      else this.clientPage = p;
    };
    const setPageSize = (n: number): void => {
      if (this.serverSide) this.emit('pageSizeChange', n);
      else {
        this.clientPageSize = n;
        this.clientPage = 0;
      }
    };

    const searchbar = this.serverSide
      ? html`<ion-searchbar class="ion-no-border" placeholder=${this.effSearchPlaceholder} debounce="250" @ionInput=${this.onSearch}></ion-searchbar>`
      : html`<ion-searchbar class="ion-no-border" .value=${this.q} placeholder=${this.effSearchPlaceholder} debounce="250" @ionInput=${this.onSearch}></ion-searchbar>`;

    const selCount = this.selection.size;
    const showTopbar =
      !!this.title || this.hasSearch || this.viewToggle || this.effColumnPicker ||
      this.effExport || this.effImport || this.hasFilterRow || this.addable ||
      !!this.primaryAction;

    return html`
      <div class="card">
        ${showTopbar
          ? html`
              <div class="bar">
                <div class="bar-main">
                  ${this.title
                    ? html`<div class="title-wrap"><h2 class="title">${this.title}</h2><span class="title-count">${count}</span></div>`
                    : nothing}
                  ${this.hasSearch ? html`<div class="search">${searchbar}</div>` : nothing}
                  ${this.inlineFilters ? this.renderInlineFilters() : nothing}
                  <span class="tk-spacer"></span>
                    ${this.effPageSizes.length
                      ? html`
                          <ion-select
                            class="tk-psize"
                            interface="popover"
                            aria-label=${this.t.rowsPerPage}
                            .value=${ps}
                            @ionChange=${(e: CustomEvent) => setPageSize(Number((e.detail as { value: unknown }).value))}
                          >
                            ${this.effPageSizes.map((n) => html`<ion-select-option .value=${n}>${n}</ion-select-option>`)}
                          </ion-select>
                        `
                      : nothing}
                    ${this.viewToggle
                      ? html`
                          <span class="viewseg">
                            ${this.toolButton('list-outline', this.viewMode === 'table', () => this.setViewMode('table'), this.t.viewList)}
                            ${this.toolButton('grid-outline', this.viewMode === 'cards', () => this.setViewMode('cards'), this.t.viewCards)}
                          </span>
                        `
                      : nothing}
                    ${this.effColumnPicker
                      ? html`
                          <ion-select
                            class="tk-cols"
                            multiple
                            interface="popover"
                            aria-label=${this.t.columnsVisible}
                            .value=${this.visibleColumns.map((c) => c.key)}
                            .selectedText=${this.t.columns}
                            @ionChange=${(e: CustomEvent) => this.setVisibleColumns((e.detail as { value: string[] }).value)}
                          >
                            ${this.columns.map((c) => html`<ion-select-option value=${c.key}>${c.header}</ion-select-option>`)}
                          </ion-select>
                        `
                      : nothing}
                    ${this.hasFilterRow && !this.inlineFilters ? this.toolButton('funnel-outline', this.panel === 'filters' || this.activeFilterCount > 0, () => this.toggle('filters'), this.t.filters, this.serverSide ? undefined : this.activeFilterCount) : nothing}
                    ${this.effImport
                      ? html`
                          ${this.toolButton('cloud-upload-outline', false, () => (this.renderRoot.querySelector('.tk-file') as HTMLInputElement)?.click(), this.t.importCsv)}
                          <input class="tk-file" type="file" accept=".csv,text/csv" hidden @change=${(e: Event) => this.onImportFile(e)} />
                        `
                      : nothing}
                    ${this.effExport ? this.toolButton('download-outline', false, () => this.exportCsv(), this.t.exportCsv) : nothing}
                    ${this.addable ? this.toolButton('add', this.panel === 'create', () => this.toggle('create'), this.t.add) : nothing}
                    ${this.renderOverflowMenu()}
                    ${this.primaryAction
                      ? html`
                          <ion-button
                            class="primary-btn"
                            size="small"
                            title=${this.primaryAction.label}
                            aria-label=${this.primaryAction.label}
                            @click=${() => this.emit('primaryAction', {})}
                          ><ion-icon slot="icon-only" name=${this.primaryAction.icon ?? 'add'}></ion-icon></ion-button>
                        `
                      : nothing}
                    <!-- El módulo proyecta aquí acciones globales adicionales. -->
                    <slot name="toolbar"></slot>
                </div>
                ${this.selectable && selCount > 0
                  ? html`
                      <div class="selbar">
                        <strong>${this.t.selected.replace('{n}', String(selCount))}</strong>
                        <button class="sel-clear" @click=${() => this.setSelection(new Set())}>
                          <ion-icon name="close" style="font-size:14px"></ion-icon> ${this.t.clear}
                        </button>
                      </div>
                    `
                  : nothing}
              </div>
            `
          : nothing}

        ${this.viewMode === 'cards' && this.cardViewEnabled ? this.renderCards(visible) : this.renderTable(visible)}

        ${pages > 1 || this.effPageSizes.length
          ? html`
              <div class="pager">
                <div class="left">
                  <span>
                    ${pages > 1
                      ? html`${this.t.showing
                          .replace('{from}', String(current * ps + 1))
                          .replace('{to}', String(Math.min((current + 1) * ps, count)))} `
                      : nothing}
                    <span class="strong">${count}</span> ${count === 1 ? this.t.recordSingular : this.t.recordPlural}
                  </span>
                  ${!showTopbar && this.effPageSizes.length
                    ? html`
                        <select class="psize" @change=${(e: Event) => setPageSize(Number((e.target as HTMLSelectElement).value))}>
                          ${this.effPageSizes.map((n) => html`<option value=${n} ?selected=${n === ps}>${this.t.perPageShort.replace('{n}', String(n))}</option>`)}
                        </select>
                      `
                    : nothing}
                </div>
                ${pages > 1
                  ? html`
                      <div class="nav">
                        <ion-button size="small" fill="clear" ?disabled=${current === 0} @click=${() => goTo(current - 1)}><ion-icon slot="icon-only" name="chevron-back"></ion-icon></ion-button>
                        ${this.pageList(current + 1, pages).map((p) =>
                          p === '…'
                            ? html`<span class="pgap">…</span>`
                            : html`<button class=${`pnum${p === current + 1 ? ' on' : ''}`} @click=${() => goTo(p - 1)}>${p}</button>`,
                        )}
                        <ion-button size="small" fill="clear" ?disabled=${current >= pages - 1} @click=${() => goTo(current + 1)}><ion-icon slot="icon-only" name="chevron-forward"></ion-icon></ion-button>
                      </div>
                    `
                  : nothing}
              </div>
            `
          : nothing}

        ${this.panel !== 'none' ? this.renderDrawer() : nothing}
      </div>
    `;
  }

  // Panel lateral derecho DENTRO de la tabla (no empuja contenido; igual en lista y tarjetas).
  private renderDrawer(): unknown {
    const isFilters = this.panel === 'filters';
    // En modo cliente el panel de filtros usa chips multi-select + rango de fechas con borrador
    // y botones Aplicar/Limpiar (1:1 con el modal de filtros del Hub). En servidor, controles que
    // emiten `filterChange` en vivo (sin botón Aplicar).
    const clientFilters = isFilters && !this.serverSide;
    return html`
      <div class="tk-scrim" @click=${() => this.close()}></div>
      <aside class="drawer" role="dialog" aria-label=${isFilters ? this.t.filters : this.t.form}>
        <header class="dh">
          <strong>${isFilters ? this.t.filters : this.t.newRecord}</strong>
          <ion-button fill="clear" size="small" aria-label=${this.t.close} @click=${() => this.close()}><ion-icon slot="icon-only" name="close"></ion-icon></ion-button>
        </header>
        <div class="db">
          ${isFilters
            ? clientFilters
              ? this.filterColumns.map((c) => this.renderClientFilter(c))
              : this.filterColumns.map((c) => html`<div class="fblock">${this.renderFilterControl(c)}</div>`)
            : html`<slot name="create"></slot>`}
        </div>
        ${clientFilters
          ? html`
              <footer class="df">
                <button class="sel-clear df-clear" ?disabled=${Object.keys(this.filterDraft).length === 0} @click=${() => this.clearFilters()}>${this.t.clear}</button>
                <ion-button class="primary-btn" size="small" @click=${() => this.applyFilters()}>${this.t.apply}</ion-button>
              </footer>
            `
          : nothing}
      </aside>
    `;
  }

  // Control de filtro CLIENTE de una columna: chips multi-select (select) o rango de fechas.
  private renderClientFilter(col: DataTableColumn): unknown {
    const label = col.header;
    if (col.filterType === 'daterange' || col.filterType === 'date') {
      const f = this.filterDraft[col.key] ?? {};
      return html`
        <div class="fblock">
          <span class="flabel">${label}</span>
          <div class="daterange">
            <ion-input type="date" label=${this.t.from} label-placement="stacked" fill="outline" .value=${f.from ?? ''} @ionChange=${(e: Event) => this.setFilterRange(col.key, 'from', (e as CustomEvent).detail.value ?? '')}></ion-input>
            <ion-input type="date" label=${this.t.to} label-placement="stacked" fill="outline" .value=${f.to ?? ''} @ionChange=${(e: Event) => this.setFilterRange(col.key, 'to', (e as CustomEvent).detail.value ?? '')}></ion-input>
          </div>
        </div>
      `;
    }
    // Por defecto: multi-select por chips con los valores distintos de la columna.
    const distinct = this.distinctValues(col);
    const selected = this.filterDraft[col.key]?.values ?? new Set<string>();
    return html`
      <div class="fblock">
        <span class="flabel">${label}</span>
        <div class="chips">
          ${distinct.length === 0
            ? html`<span class="chip-empty">${this.t.noValues}</span>`
            : distinct.map((v) => {
                const on = selected.has(v);
                return html`
                  <button class=${`chip${on ? ' on' : ''}`} @click=${() => this.toggleFilterValue(col.key, v)}>
                    ${on ? html`<ion-icon name="checkmark-outline"></ion-icon>` : nothing}${v}
                  </button>
                `;
              })}
        </div>
      </div>
    `;
  }

  private emptyState(): unknown {
    return html`
      <div class="empty">
        <span class="empty-ic"><ion-icon name="file-tray-outline"></ion-icon></span>
        <span>${this.effEmptyMessage}</span>
      </div>
    `;
  }

  // Vista LISTA en CSS GRID (no <table>): permite ancho por columna y cabecera sticky.
  private renderTable(visible: Record<string, unknown>[]): unknown {
    if (visible.length === 0) return this.emptyState();
    const cols = this.visibleColumns;
    const tpl = { gridTemplateColumns: this.gridTemplate() };
    const allOn = this.selectable && visible.length > 0 && visible.every((r) => this.selection.has(this.keyOf(r)));
    const alignCls = (a?: string): string => (a === 'right' ? 'right' : a === 'center' ? 'center' : 'left');

    return html`
      <div class="scroll">
        <div class="grid" role="table">
          <!-- Cabecera -->
          <div class="grow ghead" role="row" style=${styleMap(tpl)}>
            ${this.selectable
              ? html`<span class="selcb"><ion-checkbox .checked=${allOn} aria-label=${this.t.selectAll} @ionChange=${() => this.toggleAll(visible)}></ion-checkbox></span>`
              : nothing}
            ${cols.map((c) => {
              const sortable = this.isSortable(c);
              const active = sortable && (this.serverSide ? this.sort === c.key : this.clientSort === c.key);
              const dir = this.serverSide ? this.sortDir : this.clientSortDir;
              // Icono 3-estados (como el Hub): neutral / asc / desc, con Ionicons.
              const caretIcon = !active ? 'swap-vertical-outline' : dir === 'asc' ? 'chevron-up-outline' : 'chevron-down-outline';
              return html`
                <div
                  class=${`gcell gh ${alignCls(c.align)}${sortable ? ' sortable' : ''}`}
                  role="columnheader"
                  @click=${() => this.onHeaderClick(c)}
                >
                  <span>${c.header}</span>
                  ${sortable
                    ? html`<span class=${`caret${active ? ' on' : ''}`}><ion-icon name=${caretIcon}></ion-icon></span>`
                    : nothing}
                </div>
              `;
            })}
            ${this.actions.length ? html`<div class="gcell gh right" role="columnheader">${this.t.actions}</div>` : nothing}
          </div>

          <!-- Filas -->
          ${repeat(
            visible,
            (row) => this.keyOf(row),
            (row) => {
              const key = this.keyOf(row);
              const selected = this.selectable && this.selection.has(key);
              return html`
                <div class=${`grow grow-data${selected ? ' selected' : ''}`} role="row" style=${styleMap(tpl)}>
                  ${this.selectable
                    ? html`<span class="selcb"><ion-checkbox .checked=${selected} aria-label=${this.t.selectRow} @ionChange=${() => this.toggleRow(key)}></ion-checkbox></span>`
                    : nothing}
                  ${cols.map(
                    (c) => html`<div class=${`gcell ${alignCls(c.align)}`} role="cell">${c.render ? c.render(row) : html`<span>${this.cell(c, row)}</span>`}</div>`,
                  )}
                  ${this.actions.length ? html`<div class="gcell right" role="cell">${this.actionButtons(row)}</div>` : nothing}
                </div>
              `;
            },
          )}
        </div>
      </div>
    `;
  }

  private renderCards(visible: Record<string, unknown>[]): unknown {
    if (visible.length === 0) return this.emptyState();
    const hasHead = !!this.cardTitle || !!this.cardIcon || this.selectable;
    return html`
      <div class="cards-grid">
        ${repeat(
          visible,
          (row) => this.keyOf(row),
          (row) => {
            const key = this.keyOf(row);
            const selected = this.selectable && this.selection.has(key);
            const icon = this.cardIcon?.(row);
            return html`
              <div class=${`rcard${selected ? ' selected' : ''}`}>
                ${hasHead
                  ? html`
                      <header class="rcard-head">
                        ${icon != null && icon !== ''
                          ? html`<span class="rc-icon">${typeof icon === 'string' ? html`<ion-icon name=${icon}></ion-icon>` : icon}</span>`
                          : nothing}
                        <span class="rc-title">${this.cardTitle ? this.cardTitle(row) : nothing}</span>
                        ${this.selectable
                          ? html`<ion-checkbox .checked=${selected} aria-label=${this.t.select} @ionChange=${() => this.toggleRow(key)}></ion-checkbox>`
                          : nothing}
                      </header>
                    `
                  : nothing}
                <div class="rcard-body">
                  ${this.renderCard
                    ? this.renderCard(row)
                    : this.visibleColumns.map(
                        (c) => html`<div class="rrow"><span class="rk">${c.header}</span><span class="rv">${c.render ? c.render(row) : this.cell(c, row)}</span></div>`,
                      )}
                </div>
                ${this.actions.length ? html`<div class="ractions">${this.actionButtons(row)}</div>` : nothing}
              </div>
            `;
          },
        )}
      </div>
    `;
  }
}

define('ok-data-table', OkDataTable);

declare global {
  interface HTMLElementTagNameMap {
    'ok-data-table': OkDataTable;
  }
}
