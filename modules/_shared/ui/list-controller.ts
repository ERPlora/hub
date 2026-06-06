// list-controller — estado (página/orden/búsqueda/filtros/total) + re-consulta al runtime.
// Agnóstico de framework: lo usan TODOS los CRUD para alimentar el `<data-table serverSide>`
// sin reimplementar el estado en cada vista. La vista pasa un `onChange` que fuerza repintado
// (en Stencil: incrementar un @State) y lee `rows/total/loading/error/state` en render.
//
// El cliente es `globalThis.erplora` (lo monta el shell); solo se usa su método `queryPage`,
// que ya aplana los filtros a `f_<col>` y devuelve `{rows,total,limit,offset}`.

export interface ListPage<T> {
  rows: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface ListParams {
  limit?: number;
  offset?: number;
  search?: string;
  sort?: string;
  dir?: 'asc' | 'desc';
  filters?: Record<string, unknown>;
  /** Params de contexto obligatorios (p.ej. `{ bom_id }` para una sub-lista de hijos). */
  params?: Record<string, unknown>;
}

/** Subconjunto del cliente SDK que necesita el controlador (inyectable para tests). */
export interface ListClient {
  queryPage<R = unknown>(name: string, params: ListParams): Promise<ListPage<R>>;
}

export interface ListControllerOptions {
  /** Filas por página (default 50). */
  pageSize?: number;
  /** Orden inicial. */
  sort?: string;
  dir?: 'asc' | 'desc';
  /** Filtros iniciales (`col -> valor` o `col -> {from,to}`). */
  filters?: Record<string, unknown>;
  /** Params de contexto obligatorios iniciales (sub-listas: `{ bom_id }`). */
  context?: Record<string, unknown>;
}

export interface ListControllerState {
  page: number; // 0-based
  pageSize: number;
  search: string;
  sort?: string;
  dir: 'asc' | 'desc';
  filters: Record<string, unknown>;
  /** Params de contexto obligatorios (sub-lista de hijos de un padre seleccionado). */
  context: Record<string, unknown>;
}

function isEmpty(v: unknown): boolean {
  return v === null || v === undefined || v === '';
}

export class ListController<T = Record<string, unknown>> {
  rows: T[] = [];
  total = 0;
  loading = false;
  error = '';
  readonly state: ListControllerState;
  /** Descarta respuestas obsoletas si llegan fuera de orden (race de cargas concurrentes). */
  private seq = 0;

  constructor(
    private readonly client: ListClient,
    private readonly queryName: string,
    private readonly onChange: () => void = () => {},
    opts: ListControllerOptions = {},
  ) {
    this.state = {
      page: 0,
      pageSize: opts.pageSize ?? 50,
      search: '',
      sort: opts.sort,
      dir: opts.dir ?? 'asc',
      filters: { ...(opts.filters ?? {}) },
      context: { ...(opts.context ?? {}) },
    };
  }

  /** Nº de páginas según el total del servidor (mínimo 1). */
  get pageCount(): number {
    return Math.max(1, Math.ceil(this.total / this.state.pageSize));
  }

  /** (Re)carga la página actual desde el servidor. */
  async load(): Promise<void> {
    const s = this.state;
    const mySeq = ++this.seq;
    this.loading = true;
    this.error = '';
    this.onChange();
    try {
      const page = await this.client.queryPage<T>(this.queryName, {
        limit: s.pageSize,
        offset: s.page * s.pageSize,
        search: s.search,
        sort: s.sort,
        dir: s.dir,
        filters: s.filters,
        params: s.context,
      });
      if (mySeq !== this.seq) return; // llegó una carga más reciente
      this.rows = page.rows ?? [];
      this.total = page.total ?? this.rows.length;
    } catch (e) {
      if (mySeq !== this.seq) return;
      this.rows = [];
      this.total = 0;
      this.error = e instanceof Error ? e.message : 'Error cargando datos';
    } finally {
      if (mySeq === this.seq) {
        this.loading = false;
        this.onChange();
      }
    }
  }

  setPage(page: number): void {
    this.state.page = Math.max(0, page);
    void this.load();
  }

  setSort(sort: string, dir: 'asc' | 'desc'): void {
    this.state.sort = sort;
    this.state.dir = dir;
    this.state.page = 0;
    void this.load();
  }

  setSearch(search: string): void {
    this.state.search = search;
    this.state.page = 0;
    void this.load();
  }

  /** Aplica/quita un filtro de columna; valores vacíos lo eliminan. Vuelve a la página 0. */
  setFilter(col: string, value: unknown): void {
    if (isEmpty(value)) {
      delete this.state.filters[col];
    } else if (typeof value === 'object' && value !== null) {
      // Rango parcial {from}/{to}: fusiona con lo existente para no perder el otro extremo.
      const prev = (this.state.filters[col] as Record<string, unknown>) ?? {};
      const merged = { ...prev, ...(value as Record<string, unknown>) };
      const cleaned = Object.fromEntries(Object.entries(merged).filter(([, v]) => !isEmpty(v)));
      if (Object.keys(cleaned).length === 0) delete this.state.filters[col];
      else this.state.filters[col] = cleaned;
    } else {
      this.state.filters[col] = value;
    }
    this.state.page = 0;
    void this.load();
  }

  /** Fija/actualiza los params de contexto obligatorios (p.ej. al seleccionar el padre).
   *  Vuelve a la página 0 y recarga. Pasa `{}` o keys con valor vacío para limpiar. */
  setContext(context: Record<string, unknown>): void {
    this.state.context = { ...context };
    this.state.page = 0;
    void this.load();
  }

  reset(): void {
    this.state.page = 0;
    this.state.search = '';
    this.state.filters = {};
    void this.load();
  }
}

/** Fábrica del controlador de lista (azúcar sobre `new ListController`). */
export function createListController<T = Record<string, unknown>>(
  client: ListClient,
  queryName: string,
  onChange: () => void = () => {},
  opts: ListControllerOptions = {},
): ListController<T> {
  return new ListController<T>(client, queryName, onChange, opts);
}
