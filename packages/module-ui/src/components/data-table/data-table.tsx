import { Component, Prop, State, Event, EventEmitter, h } from '@stencil/core';

// data-table — DataTable reutilizable de hub (Stencil), construido con elementos Ionic.
// Lo usan TODOS los CRUD de los módulos. El WC nunca toca la BD.
//
// DOS MODOS:
//  • Cliente (por defecto): recibe TODAS las filas en `rows`; filtra (searchKeys) y pagina en
//    memoria. Para listas pequeñas / no paginadas (settings, catálogos cortos).
//  • Servidor (`serverSide`): NO filtra ni pagina en memoria. Renderiza tal cual las `rows` de
//    la página actual y usa `total`/`page`/`pageSize`/`sort`/`dir` para el pager y los carets.
//    Emite `pageChange`/`sortChange`/`searchChange`/`filterChange`; el módulo (vía
//    `createListController` del SDK) re-consulta al runtime. Soporta orden por columna y
//    filtro por columna (texto/select/rango) — "todo lo que hay en datatable".
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
  /** (server) Tipo de control de filtro. Por defecto 'text'.
   *  - text/number/date: input simple (op `eq`/`like` en el manifest).
   *  - select: desplegable (op `eq`).
   *  - range: rango numérico (dos inputs number) — op `range`.
   *  - daterange: rango de fechas (dos inputs date, ISO) — op `range` sobre columna fecha. */
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

@Component({
  tag: 'data-table',
  shadow: true,
  styles: `
    :host { display:block; color: var(--ink, #1c1b17); font-family: system-ui, sans-serif; }
    .card { border:1px solid var(--line,#e7e2d6); border-radius:12px; overflow:hidden; background:var(--surface,#fff); }
    .bar { display:flex; flex-direction:column; gap:.75rem; padding:.75rem 1rem; border-bottom:1px solid var(--line,#e7e2d6); }
    @media (min-width:640px){ .bar { flex-direction:row; align-items:center; justify-content:space-between; } }
    .search { flex:1; max-width:20rem; }
    ion-searchbar { --background: var(--surface-2,#f7f4ec); --border-radius:10px; padding:0; }
    .scroll { overflow-x:auto; }
    table { width:100%; border-collapse:collapse; font-size:14px; }
    thead tr { background: var(--surface-2,#f7f4ec); }
    th { text-align:left; padding:.75rem 1rem; font-size:12px; font-weight:600; text-transform:uppercase; letter-spacing:.04em; color:var(--muted,#8b897f); }
    th.right, td.right { text-align:right; }
    th.center, td.center { text-align:center; }
    th.sortable { cursor:pointer; user-select:none; white-space:nowrap; }
    th.sortable:hover { color:var(--ink,#1c1b17); }
    .caret { font-size:10px; opacity:.5; margin-left:.25rem; }
    .caret.on { opacity:1; }
    tr.filters th { padding:.4rem 1rem .6rem; text-transform:none; font-weight:400; }
    tr.filters input, tr.filters select { width:100%; box-sizing:border-box; font:inherit; font-size:13px; padding:.3rem .4rem; border:1px solid var(--line,#e7e2d6); border-radius:6px; background:var(--surface,#fff); color:var(--ink,#1c1b17); }
    .range { display:flex; gap:.25rem; }
    td { padding:.7rem 1rem; border-top:1px solid var(--line-soft,#efeae0); color:var(--ink,#1c1b17); }
    tbody tr:hover { background: var(--surface-2,#f7f4ec); }
    .empty { padding:4rem 1rem; text-align:center; color:var(--muted,#8b897f); }
    .actions { display:flex; gap:.25rem; justify-content:flex-end; }
    .pager { display:flex; align-items:center; justify-content:space-between; padding:.7rem 1rem; border-top:1px solid var(--line,#e7e2d6); font-size:13px; color:var(--muted,#8b897f); }
    .pager .nav { display:flex; align-items:center; gap:.25rem; }
    ion-button { --box-shadow:none; }
  `,
})
export class DataTable {
  /** Columnas a renderizar. */
  @Prop() columns: DataTableColumn[] = [];
  /** Filas (objetos planos). En modo servidor, solo las de la página actual. */
  @Prop() rows: Record<string, unknown>[] = [];
  /** (cliente) Campos sobre los que filtra el buscador en memoria. Vacío = sin buscador. */
  @Prop() searchKeys: string[] = [];
  /** Campo usado como key estable de fila. */
  @Prop() rowKeyField = 'id';
  /** Filas por página. */
  @Prop() pageSize = 10;
  /** Mensaje cuando no hay filas. */
  @Prop() emptyMessage = 'Sin resultados';
  /** Placeholder del buscador. */
  @Prop() searchPlaceholder = 'Buscar…';
  /** Acciones por fila (botones). */
  @Prop() actions: DataTableAction[] = [];

  // ── Modo servidor ────────────────────────────────────────────────────────────────────────
  /** Activa el modo servidor: el componente no filtra/pagina en memoria, solo emite eventos. */
  @Prop() serverSide = false;
  /** (server) Total de filas filtradas (lo da el runtime) para calcular el nº de páginas. */
  @Prop() total = 0;
  /** (server) Página actual (0-based), controlada por el padre. */
  @Prop() page = 0;
  /** (server) Muestra el buscador aunque no haya `searchKeys` (la búsqueda es server-side). */
  @Prop() searchable = false;
  /** (server) Columna de orden activa. */
  @Prop() sort?: string;
  /** (server) Dirección del orden activo. (`sortDir`, no `dir`: `dir` es reservado en el DOM.) */
  @Prop() sortDir: 'asc' | 'desc' = 'asc';

  // Estado interno SOLO del modo cliente.
  @State() q = '';
  @State() clientPage = 0;

  /** Click en un botón de acción de fila. */
  @Event() rowAction!: EventEmitter<{ actionId: string; row: Record<string, unknown> }>;
  /** (server) Cambio de página (nueva página 0-based). */
  @Event() pageChange!: EventEmitter<number>;
  /** (server) Cambio de orden. */
  @Event() sortChange!: EventEmitter<{ sort: string; dir: 'asc' | 'desc' }>;
  /** (server) Cambio del buscador global. */
  @Event() searchChange!: EventEmitter<string>;
  /** (server) Cambio de un filtro de columna (`value` null/'' = quitar filtro). */
  @Event() filterChange!: EventEmitter<{ col: string; value: unknown }>;

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

  private onSearch = (ev: Event) => {
    const value = (ev.target as HTMLInputElement).value ?? '';
    if (this.serverSide) {
      this.searchChange.emit(value);
    } else {
      this.q = value;
      this.clientPage = 0;
    }
  };

  private onHeaderClick(col: DataTableColumn) {
    if (!this.serverSide || !col.sortable) return;
    const dir = this.sort === col.key && this.sortDir === 'asc' ? 'desc' : 'asc';
    this.sortChange.emit({ sort: col.key, dir });
  }

  private onFilterInput(col: DataTableColumn, ev: Event) {
    const value = (ev.target as HTMLInputElement | HTMLSelectElement).value ?? '';
    this.filterChange.emit({ col: col.key, value });
  }

  private onRangeInput(col: DataTableColumn, edge: 'from' | 'to', ev: Event) {
    const raw = (ev.target as HTMLInputElement).value ?? '';
    // Rango numérico: emite Number para que el runtime compare con el tipo real (`>=`/`<=`).
    const v = raw === '' ? '' : Number(raw);
    this.filterChange.emit({ col: col.key, value: { [edge]: v } });
  }

  private onDateRangeInput(col: DataTableColumn, edge: 'from' | 'to', ev: Event) {
    // Rango de fechas: emite el string ISO (YYYY-MM-DD); el runtime compara texto (orden = cronológico).
    const v = (ev.target as HTMLInputElement).value ?? '';
    this.filterChange.emit({ col: col.key, value: { [edge]: v } });
  }

  private renderFilterControl(col: DataTableColumn) {
    if (!col.filterable) return <span />;
    const type = col.filterType ?? 'text';
    if (type === 'select') {
      return (
        <select onChange={(e) => this.onFilterInput(col, e)}>
          <option value="">—</option>
          {(col.options ?? []).map((o) => (
            <option value={o.value}>{o.label}</option>
          ))}
        </select>
      );
    }
    if (type === 'range') {
      return (
        <span class="range">
          <input type="number" placeholder="≥" onChange={(e) => this.onRangeInput(col, 'from', e)} />
          <input type="number" placeholder="≤" onChange={(e) => this.onRangeInput(col, 'to', e)} />
        </span>
      );
    }
    if (type === 'daterange') {
      return (
        <span class="range">
          <input type="date" onChange={(e) => this.onDateRangeInput(col, 'from', e)} />
          <input type="date" onChange={(e) => this.onDateRangeInput(col, 'to', e)} />
        </span>
      );
    }
    const inputType = type === 'number' ? 'number' : type === 'date' ? 'date' : 'text';
    return <input type={inputType} onInput={(e) => this.onFilterInput(col, e)} />;
  }

  render() {
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

    const goTo = (p: number) => {
      if (this.serverSide) this.pageChange.emit(p);
      else this.clientPage = p;
    };

    return (
      <div class="card">
        <div class="bar">
          <div class="search">
            {this.hasSearch ? (
              <ion-searchbar
                value={this.serverSide ? undefined : this.q}
                placeholder={this.searchPlaceholder}
                debounce={250}
                onIonInput={this.onSearch}
              />
            ) : (
              <span />
            )}
          </div>
          {/* El módulo proyecta aquí su botón "Nuevo"/acciones globales. */}
          <slot name="toolbar" />
        </div>

        <div class="scroll">
          <table>
            <thead>
              <tr>
                {this.columns.map((c) => {
                  const active = this.serverSide && c.sortable && this.sort === c.key;
                  return (
                    <th
                      key={c.key}
                      class={`${c.align ?? 'left'}${this.serverSide && c.sortable ? ' sortable' : ''}`}
                      onClick={() => this.onHeaderClick(c)}
                    >
                      {c.header}
                      {this.serverSide && c.sortable ? (
                        <span class={`caret${active ? ' on' : ''}`}>{active && this.sortDir === 'desc' ? '▼' : '▲'}</span>
                      ) : null}
                    </th>
                  );
                })}
                {this.actions.length ? <th class="right" /> : null}
              </tr>
              {this.hasFilterRow ? (
                <tr class="filters">
                  {this.columns.map((c) => (
                    <th key={`f-${c.key}`} class={c.align ?? 'left'}>
                      {this.renderFilterControl(c)}
                    </th>
                  ))}
                  {this.actions.length ? <th /> : null}
                </tr>
              ) : null}
            </thead>
            <tbody>
              {visible.length === 0 ? (
                <tr>
                  <td class="empty" colSpan={colSpan}>
                    {this.emptyMessage}
                  </td>
                </tr>
              ) : (
                visible.map((row) => (
                  <tr key={String(row[this.rowKeyField] ?? '')}>
                    {this.columns.map((c) => (
                      <td key={c.key} class={c.align ?? 'left'}>
                        {this.cell(c, row)}
                      </td>
                    ))}
                    {this.actions.length ? (
                      <td class="right">
                        <div class="actions">
                          {this.actions.map((a) => (
                            <ion-button
                              key={a.id}
                              size="small"
                              fill="clear"
                              color={a.color ?? 'medium'}
                              onClick={() => this.rowAction.emit({ actionId: a.id, row })}
                            >
                              {a.icon ? <ion-icon name={a.icon} slot="icon-only" /> : a.label}
                            </ion-button>
                          ))}
                        </div>
                      </td>
                    ) : null}
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {pages > 1 ? (
          <div class="pager">
            <span>{count} resultados</span>
            <div class="nav">
              <ion-button size="small" fill="clear" disabled={current === 0} onClick={() => goTo(current - 1)}>
                <ion-icon name="chevron-back" slot="icon-only" />
              </ion-button>
              <span>
                {current + 1} / {pages}
              </span>
              <ion-button
                size="small"
                fill="clear"
                disabled={current >= pages - 1}
                onClick={() => goTo(current + 1)}
              >
                <ion-icon name="chevron-forward" slot="icon-only" />
              </ion-button>
            </div>
          </div>
        ) : null}
      </div>
    );
  }
}
