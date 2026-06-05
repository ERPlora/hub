import { Component, Prop, State, Event, EventEmitter, h } from '@stencil/core';

// data-table — DataTable reutilizable de hub-next, versión Web Component (Stencil),
// portada del DataTable React de packages/ui (mismo API: columns/rows/searchKeys/
// pageSize/emptyMessage + toolbar) y construida con elementos Ionic (ion-searchbar,
// ion-button). El shell (@ionic/react) registra los `ion-*` globalmente; no se bundlean.
//
// Lo usan TODOS los CRUD de los módulos: cada módulo pasa `columns` + `rows` (obtenidos
// vía erplora.query) y escucha `rowAction` para sus botones de fila. El WC nunca toca la BD.
//
// Filas NO clicables (navegación vía botones de fila): se pasan `actions` y el módulo
// reacciona al evento `rowAction` ({actionId, row}).

export interface DataTableColumn {
  /** Clave del campo en la fila (o id lógico si se usa `format`). */
  key: string;
  /** Cabecera de la columna. */
  header: string;
  /** Formateador → string a mostrar. Si se omite, se usa row[key]. */
  format?: (row: Record<string, unknown>) => string;
  /** Alineación del contenido de la celda. */
  align?: 'left' | 'right' | 'center';
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
  /** Filas (objetos planos). */
  @Prop() rows: Record<string, unknown>[] = [];
  /** Campos sobre los que filtra el buscador. Vacío = sin buscador. */
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

  @State() q = '';
  @State() page = 0;

  /** Click en un botón de acción de fila. */
  @Event() rowAction!: EventEmitter<{ actionId: string; row: Record<string, unknown> }>;

  private get filtered(): Record<string, unknown>[] {
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
    this.q = (ev.target as HTMLInputElement).value ?? '';
    this.page = 0;
  };

  render() {
    const rows = this.filtered;
    const pages = Math.max(1, Math.ceil(rows.length / this.pageSize));
    const current = Math.min(this.page, pages - 1);
    const slice = rows.slice(current * this.pageSize, current * this.pageSize + this.pageSize);
    const colSpan = this.columns.length + (this.actions.length ? 1 : 0);

    return (
      <div class="card">
        <div class="bar">
          <div class="search">
            {this.searchKeys.length ? (
              <ion-searchbar
                value={this.q}
                placeholder={this.searchPlaceholder}
                debounce={150}
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
                {this.columns.map((c) => (
                  <th key={c.key} class={c.align ?? 'left'}>
                    {c.header}
                  </th>
                ))}
                {this.actions.length ? <th class="right" /> : null}
              </tr>
            </thead>
            <tbody>
              {slice.length === 0 ? (
                <tr>
                  <td class="empty" colSpan={colSpan}>
                    {this.emptyMessage}
                  </td>
                </tr>
              ) : (
                slice.map((row) => (
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
            <span>{rows.length} resultados</span>
            <div class="nav">
              <ion-button
                size="small"
                fill="clear"
                disabled={current === 0}
                onClick={() => (this.page = current - 1)}
              >
                <ion-icon name="chevron-back" slot="icon-only" />
              </ion-button>
              <span>
                {current + 1} / {pages}
              </span>
              <ion-button
                size="small"
                fill="clear"
                disabled={current >= pages - 1}
                onClick={() => (this.page = current + 1)}
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
