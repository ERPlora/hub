import { LitElement, html, css, nothing } from 'lit';
import { property, state } from 'lit/decorators.js';
import { repeat } from 'lit/directives/repeat.js';
import { define } from '../../base/define.js';

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
}

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
    .card { border: 1px solid var(--border-color); border-radius: var(--border-radius); overflow: hidden; background: var(--background); }
    .bar { display: flex; flex-direction: column; gap: 0.75rem; padding: 0.75rem 1rem; border-bottom: 1px solid var(--border-color); }
    @media (min-width: 640px) { .bar { flex-direction: row; align-items: center; justify-content: space-between; } }
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

  private renderFilterControl(col: DataTableColumn): unknown {
    if (!col.filterable) return html`<span></span>`;
    const type = col.filterType ?? 'text';
    if (type === 'select') {
      return html`
        <select @change=${(e: Event) => this.onFilterInput(col, e)}>
          <option value="">—</option>
          ${(col.options ?? []).map((o) => html`<option value=${o.value}>${o.label}</option>`)}
        </select>
      `;
    }
    if (type === 'range') {
      return html`
        <span class="range">
          <input type="number" placeholder="≥" @change=${(e: Event) => this.onRangeInput(col, 'from', e)} />
          <input type="number" placeholder="≤" @change=${(e: Event) => this.onRangeInput(col, 'to', e)} />
        </span>
      `;
    }
    if (type === 'daterange') {
      return html`
        <span class="range">
          <input type="date" @change=${(e: Event) => this.onDateRangeInput(col, 'from', e)} />
          <input type="date" @change=${(e: Event) => this.onDateRangeInput(col, 'to', e)} />
        </span>
      `;
    }
    const inputType = type === 'number' ? 'number' : type === 'date' ? 'date' : 'text';
    return html`<input type=${inputType} @input=${(e: Event) => this.onFilterInput(col, e)} />`;
  }

  render(): unknown {
    // Filas a pintar + paginación, según el modo.
    let visible: Record<string, unknown>[];
    let pages: number;
    let current: number;
    let count: number;
    if (this.serverSide) {
      visible = this.rows;
      count = this.total;
      pages = Math.max(1, Math.ceil(this.total / this.pageSize));
      current = Math.min(this.page, pages - 1);
    } else {
      const filtered = this.clientFiltered;
      count = filtered.length;
      pages = Math.max(1, Math.ceil(filtered.length / this.pageSize));
      current = Math.min(this.clientPage, pages - 1);
      visible = filtered.slice(current * this.pageSize, current * this.pageSize + this.pageSize);
    }
    const colSpan = this.columns.length + (this.actions.length ? 1 : 0);

    const goTo = (p: number): void => {
      if (this.serverSide) this.emit('pageChange', p);
      else this.clientPage = p;
    };

    const searchbar = this.serverSide
      ? html`<ion-searchbar placeholder=${this.searchPlaceholder} debounce="250" @ionInput=${this.onSearch}></ion-searchbar>`
      : html`<ion-searchbar .value=${this.q} placeholder=${this.searchPlaceholder} debounce="250" @ionInput=${this.onSearch}></ion-searchbar>`;

    return html`
      <div class="card">
        <div class="bar">
          <div class="search">${this.hasSearch ? searchbar : html`<span></span>`}</div>
          <!-- El módulo proyecta aquí su botón "Nuevo"/acciones globales. -->
          <slot name="toolbar"></slot>
        </div>

        <div class="scroll">
          <table>
            <thead>
              <tr>
                ${this.columns.map((c) => {
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
              ${this.hasFilterRow
                ? html`
                    <tr class="filters">
                      ${this.columns.map(
                        (c) => html`<th class=${c.align ?? 'left'}>${this.renderFilterControl(c)}</th>`,
                      )}
                      ${this.actions.length ? html`<th></th>` : nothing}
                    </tr>
                  `
                : nothing}
            </thead>
            <tbody>
              ${visible.length === 0
                ? html`<tr><td class="empty" colspan=${colSpan}>${this.emptyMessage}</td></tr>`
                : repeat(
                    visible,
                    (row) => String(row[this.rowKeyField] ?? ''),
                    (row) => html`
                      <tr>
                        ${this.columns.map(
                          (c) => html`<td class=${c.align ?? 'left'}>${this.cell(c, row)}</td>`,
                        )}
                        ${this.actions.length
                          ? html`
                              <td class="right">
                                <div class="actions">
                                  ${this.actions.map(
                                    (a) => html`
                                      <ion-button
                                        size="small"
                                        fill="clear"
                                        color=${a.color ?? 'medium'}
                                        @click=${() => this.emit('rowAction', { actionId: a.id, row })}
                                      >
                                        ${a.icon
                                          ? html`<ion-icon name=${a.icon} slot="icon-only"></ion-icon>`
                                          : a.label}
                                      </ion-button>
                                    `,
                                  )}
                                </div>
                              </td>
                            `
                          : nothing}
                      </tr>
                    `,
                  )}
            </tbody>
          </table>
        </div>

        ${pages > 1
          ? html`
              <div class="pager">
                <span>${count} resultados</span>
                <div class="nav">
                  <ion-button size="small" fill="clear" ?disabled=${current === 0} @click=${() => goTo(current - 1)}>
                    <ion-icon name="chevron-back" slot="icon-only"></ion-icon>
                  </ion-button>
                  <span>${current + 1} / ${pages}</span>
                  <ion-button size="small" fill="clear" ?disabled=${current >= pages - 1} @click=${() => goTo(current + 1)}>
                    <ion-icon name="chevron-forward" slot="icon-only"></ion-icon>
                  </ion-button>
                </div>
              </div>
            `
          : nothing}
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
