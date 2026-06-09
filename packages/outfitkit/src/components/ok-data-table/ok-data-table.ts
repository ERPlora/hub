import { LitElement, html, css, nothing } from 'lit';
import { property, state } from 'lit/decorators.js';
import { repeat } from 'lit/directives/repeat.js';
import { define } from '../../base/define.js';
// Internamente usa ion-button / ion-icon NATIVOS (los registra el host). OutfitKit construye SOBRE
// Ionic; no envolvemos lo que Ionic ya da.

// ok-data-table — DataTable reutilizable de ERPlora (Lit), construido con elementos Ionic
// (ion-searchbar/ion-button/ion-icon, registrados por el host). Port 1:1 del antiguo
// <data-table> de @erplora/module-ui: MISMA API (props/eventos/tipos). El WC nunca toca la BD.
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
  filterType?: 'text' | 'select' | 'number' | 'date' | 'range' | 'daterange';
  /** (server) Opciones para `filterType: 'select'`. */
  options?: { value: string; label: string }[];
  /** Render de celda a medida (devuelve un TemplateResult de Lit, p.ej. un `ok-toggle` o un chip).
   *  Tiene prioridad sobre `format`/valor crudo. El módulo lo crea con su `html` (lit deduplicado). */
  render?: (row: Record<string, unknown>) => unknown;
  /** Oculta la columna por defecto (el usuario la reactiva en el selector de columnas). */
  hidden?: boolean;
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

export class OkDataTable extends LitElement {
  static styles = css`
    :host {
      /* Vars overridable (estilo Ionic), default = cadena --ok-* → --ion-* → hex */
      --background: var(--ok-surface, var(--ion-card-background, #ffffff));
      --color: var(--ok-text, var(--ion-text-color, #1c1b17));
      --color-muted: var(--ok-muted, rgba(var(--ion-text-color-rgb, 24, 24, 27), 0.55));
      --border-color: var(--ok-border, rgba(var(--ion-text-color-rgb, 24, 24, 27), 0.12));
      --border-color-soft: var(--ok-border-soft, rgba(var(--ion-text-color-rgb, 24, 24, 27), 0.07));
      --header-background: var(--ok-surface-2, rgba(var(--ion-text-color-rgb, 24, 24, 27), 0.04));
      --border-radius: var(--ok-radius, 12px);
      --font: var(--ok-font, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif);

      display: block;
      color: var(--color);
      font-family: var(--font);
    }
    .card { position: relative; border: 1px solid var(--border-color); border-radius: var(--border-radius); overflow: hidden; background: var(--background); }
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
    .fblock { display: flex; flex-direction: column; gap: 0.25rem; }
    .flabel { font-size: 12px; color: var(--color-muted); }
    .frange { display: flex; gap: 0.5rem; }
    /* Modo fill: la tabla ocupa el alto del contenedor; filas con scroll interno; pager fijo. */
    :host([fill]) { display: flex; flex-direction: column; height: 100%; min-height: 0; }
    :host([fill]) .card { flex: 1 1 auto; min-height: 0; display: flex; flex-direction: column; }
    :host([fill]) .bar, :host([fill]) .panel, :host([fill]) .pager { flex: 0 0 auto; }
    :host([fill]) .scroll, :host([fill]) .cards-grid { flex: 1 1 auto; min-height: 0; overflow: auto; }
    :host([fill]) thead th {
      position: sticky; top: 0; z-index: 2;
      background-color: var(--background);
      background-image: linear-gradient(var(--header-background), var(--header-background));
    }
    .bar { display: flex; flex-direction: column; gap: 0.75rem; padding: 0.75rem 1rem; border-bottom: 1px solid var(--border-color); }
    @media (min-width: 640px) { .bar { flex-direction: row; align-items: center; justify-content: space-between; } }
    .bar-end { display: flex; align-items: center; gap: 0.25rem; }
    .bar-end ion-button { --padding-start: 0.5rem; --padding-end: 0.5rem; margin: 0; }
    .tk-cols { min-width: 6.5rem; max-width: 9rem; font-size: 13px; border: 1px solid var(--border-color); border-radius: 8px; --padding-start: 0.6rem; --padding-end: 0.4rem; --padding-top: 0.3rem; --padding-bottom: 0.3rem; }
    .vsep { width: 1px; align-self: stretch; background: var(--border-color); margin: 0.3rem 0.25rem; }
    /* Acordeones (alta / filtros en modo tarjetas) */
    .panel { padding: 0.85rem 1rem; border-bottom: 1px solid var(--border-color); background: var(--header-background); }
    .filters-panel { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 0.6rem; }
    .filters-panel .fp { display: flex; flex-direction: column; gap: 0.2rem; font-size: 12px; color: var(--color-muted); }
    .filters-panel input, .filters-panel select { font: inherit; font-size: 13px; padding: 0.3rem 0.4rem; border: 1px solid var(--border-color); border-radius: 6px; background: var(--background); color: var(--color); }
    /* Vista tarjetas */
    .cards-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap: 0.75rem; padding: 1rem; }
    .rcard { border: 1px solid var(--border-color); border-radius: 10px; padding: 0.85rem; display: flex; flex-direction: column; gap: 0.4rem; background: var(--background); }
    .rrow { display: flex; justify-content: space-between; gap: 0.5rem; font-size: 13px; }
    .rrow .rk { color: var(--color-muted); }
    .rrow .rv { font-weight: 500; text-align: right; }
    .ractions { display: flex; justify-content: flex-end; gap: 0.25rem; margin-top: 0.35rem; border-top: 1px solid var(--border-color-soft); padding-top: 0.4rem; }
    /* Pager + selector de tamaño de página */
    .pager .left { display: flex; align-items: center; gap: 0.6rem; }
    .psize { font: inherit; font-size: 12.5px; padding: 0.2rem 0.35rem; border: 1px solid var(--border-color); border-radius: 6px; background: var(--background); color: var(--color); }
    .search { flex: 1; max-width: 20rem; }
    ion-searchbar { --background: var(--header-background); --border-radius: 10px; padding: 0; }
    .scroll { overflow-x: auto; }
    table { width: 100%; border-collapse: collapse; font-size: 14px; }
    thead tr { background: var(--header-background); }
    th { text-align: left; padding: 0.75rem 1rem; font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; color: var(--color-muted); }
    th.right, td.right { text-align: right; }
    th.center, td.center { text-align: center; }
    th.sortable { cursor: pointer; user-select: none; white-space: nowrap; }
    th.sortable:hover { color: var(--color); }
    .caret { font-size: 10px; opacity: 0.5; margin-left: 0.25rem; }
    .caret.on { opacity: 1; }
    tr.filters th { padding: 0.4rem 1rem 0.6rem; text-transform: none; font-weight: 400; }
    tr.filters input, tr.filters select { width: 100%; box-sizing: border-box; font: inherit; font-size: 13px; padding: 0.3rem 0.4rem; border: 1px solid var(--border-color); border-radius: 6px; background: var(--background); color: var(--color); }
    .range { display: flex; gap: 0.25rem; }
    td { padding: 0.7rem 1rem; border-top: 1px solid var(--border-color-soft); color: var(--color); }
    tbody tr:hover { background: var(--header-background); }
    .empty { padding: 4rem 1rem; text-align: center; color: var(--color-muted); }
    .actions { display: flex; gap: 0.25rem; justify-content: flex-end; }
    .pager { display: flex; align-items: center; justify-content: space-between; padding: 0.7rem 1rem; border-top: 1px solid var(--border-color); font-size: 13px; color: var(--color-muted); }
    .pager .nav { display: flex; align-items: center; gap: 0.25rem; }
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
  /** Filas por página. */
  @property({ type: Number, attribute: 'page-size' }) pageSize = 10;
  /** Mensaje cuando no hay filas. */
  @property({ attribute: 'empty-message' }) emptyMessage = 'Sin resultados';
  /** Placeholder del buscador. */
  @property({ attribute: 'search-placeholder' }) searchPlaceholder = 'Buscar…';
  /** Acciones por fila (botones). */
  @property({ attribute: false }) actions: DataTableAction[] = [];
  /** Muestra el botón "+" que despliega un acordeón con el slot `create` (formulario de alta). */
  @property({ type: Boolean }) addable = false;
  /** Muestra el conmutador de vista lista/tarjetas. */
  @property({ type: Boolean }) views = false;
  /** Opciones del selector de "filas por página". Vacío = sin selector. */
  @property({ attribute: false }) pageSizeOptions: number[] = [10, 25, 50, 100];
  /** Modo "llenar el contenedor": la tabla ocupa el alto disponible, las filas hacen scroll DENTRO
   *  (cabecera sticky) y el pager queda SIEMPRE visible. Requiere que el contenedor tenga alto. */
  @property({ type: Boolean, reflect: true }) fill = false;
  /** Muestra un multiselect (ion-select) en la barra para elegir qué columnas se ven. */
  @property({ type: Boolean }) columnPicker = false;
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

  // Estado interno SOLO del modo cliente.
  @state() private q = '';
  @state() private clientPage = 0;
  @state() private clientPageSize = 0; // 0 = usa `pageSize`
  // Panel lateral derecho (drawer) DENTRO de la tabla: filtros o alta/edición. No empuja la tabla;
  // funciona igual en vista lista y tarjetas. Inspirado en el Filters Tool Panel de AG Grid.
  @state() private panel: 'none' | 'filters' | 'create' = 'none';
  @state() private viewMode: 'table' | 'cards' = 'table';
  // Columnas ocultas por el usuario (column chooser). Vacío = todas visibles.
  @state() private hiddenKeys = new Set<string>();

  /** Columnas actualmente visibles (respeta el column chooser). */
  private get visibleColumns(): DataTableColumn[] {
    return this.hiddenKeys.size ? this.columns.filter((c) => !this.hiddenKeys.has(c.key)) : this.columns;
  }
  private setVisibleColumns(keys: string[]): void {
    const visible = new Set(keys);
    this.hiddenKeys = new Set(this.columns.map((c) => c.key).filter((k) => !visible.has(k)));
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
    input.value = '';
  }

  private toggle(p: 'filters' | 'create'): void {
    this.panel = this.panel === p ? 'none' : p;
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

  private get hasFilterRow(): boolean {
    return this.serverSide && this.columns.some((c) => c.filterable);
  }

  private get clientFiltered(): Record<string, unknown>[] {
    const needle = this.q.trim().toLowerCase();
    if (!needle || !this.searchKeys.length) return this.rows;
    return this.rows.filter((r) =>
      this.searchKeys.some((k) => String(r[k] ?? '').toLowerCase().includes(needle)),
    );
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

  private onHeaderClick(col: DataTableColumn): void {
    if (!this.serverSide || !col.sortable) return;
    const dir = this.sort === col.key && this.sortDir === 'asc' ? 'desc' : 'asc';
    this.emit('sortChange', { sort: col.key, dir });
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

  // Control de filtro de una columna, con componentes Ionic (mismos inputs que el form de alta).
  private renderFilterControl(col: DataTableColumn): unknown {
    if (!col.filterable) return nothing;
    const type = col.filterType ?? 'text';
    if (type === 'select') {
      return html`
        <ion-select
          label=${col.header}
          label-placement="stacked"
          interface="popover"
          placeholder="—"
          @ionChange=${(e: CustomEvent) =>
            this.emit('filterChange', { col: col.key, value: (e.detail as { value: unknown }).value ?? '' })}
        >
          <ion-select-option value="">—</ion-select-option>
          ${(col.options ?? []).map((o) => html`<ion-select-option value=${o.value}>${o.label}</ion-select-option>`)}
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
            <ion-input type=${t} fill="outline" placeholder=${type === 'daterange' ? 'Desde' : '≥'}
              @ionInput=${(e: Event) => onEdge(col, 'from', e)}></ion-input>
            <ion-input type=${t} fill="outline" placeholder=${type === 'daterange' ? 'Hasta' : '≤'}
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
        placeholder="Filtrar…"
        @ionInput=${(e: Event) => this.onFilterInput(col, e)}
      ></ion-input>
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
  private toolButton(icon: string, on: boolean, onClick: () => void, label: string): unknown {
    return html`
      <ion-button size="small" fill=${on ? 'solid' : 'clear'} title=${label} aria-label=${label} @click=${onClick}><ion-icon slot="icon-only" name=${icon}></ion-icon></ion-button>
    `;
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
    const colSpan = this.visibleColumns.length + (this.actions.length ? 1 : 0);

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
      ? html`<ion-searchbar placeholder=${this.searchPlaceholder} debounce="250" @ionInput=${this.onSearch}></ion-searchbar>`
      : html`<ion-searchbar .value=${this.q} placeholder=${this.searchPlaceholder} debounce="250" @ionInput=${this.onSearch}></ion-searchbar>`;

    return html`
      <div class="card">
        <div class="bar">
          <div class="search">${this.hasSearch ? searchbar : html`<span></span>`}</div>
          <div class="bar-end">
            ${this.views
              ? html`
                  ${this.toolButton('list-outline', this.viewMode === 'table', () => (this.viewMode = 'table'), 'Ver como lista')}
                  ${this.toolButton('grid-outline', this.viewMode === 'cards', () => (this.viewMode = 'cards'), 'Ver como tarjetas')}
                  <span class="vsep"></span>
                `
              : nothing}
            ${this.columnPicker
              ? html`
                  <ion-select
                    class="tk-cols"
                    multiple
                    interface="popover"
                    aria-label="Columnas visibles"
                    .value=${this.visibleColumns.map((c) => c.key)}
                    .selectedText=${'Columnas'}
                    @ionChange=${(e: CustomEvent) => this.setVisibleColumns((e.detail as { value: string[] }).value)}
                  >
                    ${this.columns.map((c) => html`<ion-select-option value=${c.key}>${c.header}</ion-select-option>`)}
                  </ion-select>
                `
              : nothing}
            ${this.csv
              ? html`
                  ${this.toolButton('download-outline', false, () => this.exportCsv(), 'Exportar CSV')}
                  ${this.toolButton('cloud-upload-outline', false, () => (this.renderRoot.querySelector('.tk-file') as HTMLInputElement)?.click(), 'Importar CSV')}
                  <input class="tk-file" type="file" accept=".csv,text/csv" hidden @change=${(e: Event) => this.onImportFile(e)} />
                `
              : nothing}
            ${this.hasFilterRow ? this.toolButton('funnel-outline', this.panel === 'filters', () => this.toggle('filters'), 'Filtros') : nothing}
            ${this.addable ? this.toolButton('add', this.panel === 'create', () => this.toggle('create'), 'Añadir') : nothing}
            <!-- El módulo proyecta aquí acciones globales adicionales. -->
            <slot name="toolbar"></slot>
          </div>
        </div>

        ${this.viewMode === 'cards' ? this.renderCards(visible) : this.renderTable(visible, colSpan)}

        ${pages > 1 || this.pageSizeOptions.length
          ? html`
              <div class="pager">
                <div class="left">
                  <span>${count} resultados</span>
                  ${this.pageSizeOptions.length
                    ? html`
                        <select class="psize" @change=${(e: Event) => setPageSize(Number((e.target as HTMLSelectElement).value))}>
                          ${this.pageSizeOptions.map((n) => html`<option value=${n} ?selected=${n === ps}>${n} / pág.</option>`)}
                        </select>
                      `
                    : nothing}
                </div>
                ${pages > 1
                  ? html`
                      <div class="nav">
                        <ion-button size="small" fill="clear" ?disabled=${current === 0} @click=${() => goTo(current - 1)}><ion-icon slot="icon-only" name="chevron-back"></ion-icon></ion-button>
                        <span>${current + 1} / ${pages}</span>
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
    return html`
      <div class="tk-scrim" @click=${() => this.close()}></div>
      <aside class="drawer" role="dialog" aria-label=${isFilters ? 'Filtros' : 'Formulario'}>
        <header class="dh">
          <strong>${isFilters ? 'Filtros' : 'Nuevo'}</strong>
          <ion-button fill="clear" size="small" aria-label="Cerrar" @click=${() => this.close()}><ion-icon slot="icon-only" name="close"></ion-icon></ion-button>
        </header>
        <div class="db">
          ${isFilters
            ? this.visibleColumns.filter((c) => c.filterable).map((c) => html`<div class="fblock">${this.renderFilterControl(c)}</div>`)
            : html`<slot name="create"></slot>`}
        </div>
      </aside>
    `;
  }

  private renderTable(visible: Record<string, unknown>[], colSpan: number): unknown {
    return html`
      <div class="scroll">
        <table>
          <thead>
            <tr>
              ${this.visibleColumns.map((c) => {
                const active = this.serverSide && c.sortable && this.sort === c.key;
                const cls = `${c.align ?? 'left'}${this.serverSide && c.sortable ? ' sortable' : ''}`;
                return html`
                  <th class=${cls} @click=${() => this.onHeaderClick(c)}>
                    ${c.header}
                    ${this.serverSide && c.sortable
                      ? html`<span class=${`caret${active ? ' on' : ''}`}>${active && this.sortDir === 'desc' ? '▼' : '▲'}</span>`
                      : nothing}
                  </th>
                `;
              })}
              ${this.actions.length ? html`<th class="right"></th>` : nothing}
            </tr>
          </thead>
          <tbody>
            ${visible.length === 0
              ? html`<tr><td class="empty" colspan=${colSpan}>${this.emptyMessage}</td></tr>`
              : repeat(
                  visible,
                  (row) => String(row[this.rowKeyField] ?? ''),
                  (row) => html`
                    <tr>
                      ${this.visibleColumns.map((c) => html`<td class=${c.align ?? 'left'}>${c.render ? c.render(row) : this.cell(c, row)}</td>`)}
                      ${this.actions.length ? html`<td class="right">${this.actionButtons(row)}</td>` : nothing}
                    </tr>
                  `,
                )}
          </tbody>
        </table>
      </div>
    `;
  }

  private renderCards(visible: Record<string, unknown>[]): unknown {
    if (visible.length === 0) return html`<div class="empty">${this.emptyMessage}</div>`;
    return html`
      <div class="cards-grid">
        ${repeat(
          visible,
          (row) => String(row[this.rowKeyField] ?? ''),
          (row) => html`
            <div class="rcard">
              ${this.visibleColumns.map(
                (c) => html`<div class="rrow"><span class="rk">${c.header}</span><span class="rv">${c.render ? c.render(row) : this.cell(c, row)}</span></div>`,
              )}
              ${this.actions.length ? html`<div class="ractions">${this.actionButtons(row)}</div>` : nothing}
            </div>
          `,
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
