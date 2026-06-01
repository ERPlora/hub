// DataTable — componente central de todos los CRUDs del Hub.
// Vista tabla + vista tarjetas, topbar con búsqueda/filtros/export/import, modal de
// filtros (multi-select + rango de fechas con calendario), paginación y aprovechamiento
// total del alto (basta con `ion-padding` en el IonContent). CSP-safe.
import {
  useEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode,
} from 'react';
import { IonCheckbox } from '@ionic/react';
import {
  LuSearch, LuFilter, LuUpload, LuDownload, LuPlus, LuList, LuLayoutGrid,
  LuCheck, LuChevronLeft, LuChevronRight, LuInbox, LuTriangleAlert, LuX,
  LuChevronsUpDown, LuChevronUp, LuChevronDown,
} from 'react-icons/lu';
import { Modal } from './Modal';
import { toCsv, downloadCsv, parseCsv } from '../lib/csv';
import { useTheme } from '../lib/theme';

const BORDER = 'border-[color:var(--ion-color-step-150,#dcdcdc)]';
const MUTED = 'text-[color:var(--ion-color-medium)]';
const SURFACE = 'bg-[color:var(--ion-color-step-100,#f4f4f5)]';
// Fondo de la card y de las zonas header/footer (un pelín distinto al body para dar relieve).
const CARD = 'bg-[color:var(--ion-card-background,var(--ion-background-color,#fff))]';
// step-100 (no step-50): step-50 == --ion-background-color, asi que header/footer se
// fundian con el lienzo. step-100 esta definido en claro y oscuro → relieve en ambos.
const HEADBG = 'bg-[color:var(--ion-color-step-100,#f4f4f5)]';

export type DataTableFilterKind = 'select' | 'dateRange';

export interface DataTableColumn<Row> {
  key: string;
  header: ReactNode;
  /** Render de celda. Si se omite, se usa row[key]. */
  cell?: (row: Row) => ReactNode;
  /** Valor para ordenar/buscar/filtrar/exportar. Si se omite, se usa row[key]. */
  value?: (row: Row) => string | number;
  /** Ordenable. Por defecto TODAS las columnas lo son; pon `false` para desactivar. */
  sortable?: boolean;
  align?: 'start' | 'center' | 'end';
  /** Ancho CSS (e.g. '12rem', '20%'). */
  width?: string;
  /** Habilita filtrado por esta columna en el modal de filtros. */
  filter?: DataTableFilterKind;
  /** Etiqueta en el modal de filtros (por defecto, el header si es string). */
  filterLabel?: string;
  /** Excluir de la búsqueda global. */
  noSearch?: boolean;
  /** Excluir del export CSV. */
  noExport?: boolean;
}

export type DataTableView = 'table' | 'card';

export interface DataTableProps<Row> {
  columns: Array<DataTableColumn<Row>>;
  rows: Row[];
  rowKey: (row: Row) => string;
  title?: ReactNode;

  // Búsqueda
  search?: string;
  onSearchChange?: (value: string) => void;
  searchable?: boolean;
  searchPlaceholder?: string;

  // Vistas
  /** Cuerpo de la tarjeta (sin la cabecera). Habilita la vista tarjetas. */
  renderCard?: (row: Row) => ReactNode;
  /** Título de la cabecera de la tarjeta (junto al icono y el checkbox). */
  cardTitle?: (row: Row) => ReactNode;
  /** Icono de la cabecera de la tarjeta. */
  cardIcon?: (row: Row) => ReactNode;
  view?: DataTableView;
  defaultView?: DataTableView;
  onViewChange?: (view: DataTableView) => void;

  // Selección
  selectable?: boolean;
  selectedKeys?: Set<string>;
  onSelectionChange?: (keys: Set<string>) => void;

  // Acciones de topbar
  primaryAction?: { label: string; icon?: ReactNode; onClick: () => void };
  toolbar?: ReactNode;
  /** Acciones por fila (editar, borrar…). Se renderizan en una columna final. */
  rowActions?: (row: Row) => ReactNode;

  // Export / Import
  enableExport?: boolean;
  exportFilename?: string;
  enableImport?: boolean;
  onImport?: (rows: Array<Record<string, string>>) => void | Promise<void>;

  // Paginación
  pageSize?: number;

  onRowClick?: (row: Row) => void;
  emptyMessage?: ReactNode;
  loading?: boolean;
  dense?: boolean;
  /** Rellena el alto del contenedor con scroll interno (por defecto true). */
  fill?: boolean;
}

type ColumnFilterState =
  | { kind: 'select'; values: Set<string> }
  | { kind: 'dateRange'; from: string; to: string };

function rawValue<Row>(col: DataTableColumn<Row>, row: Row): string | number | undefined {
  if (col.value) return col.value(row);
  return (row as Record<string, unknown>)[col.key] as string | number | undefined;
}
function colLabel<Row>(col: DataTableColumn<Row>): string {
  return col.filterLabel ?? (typeof col.header === 'string' ? col.header : col.key);
}
const cx = (...p: Array<string | false | null | undefined>) => p.filter(Boolean).join(' ');

// --- Botón de toolbar: solo icono (cuadrado), con tooltip/aria-label. -------
function ToolButton({
  label, icon, onClick, active, primary, badge,
}: { label: string; icon: ReactNode; onClick: () => void; active?: boolean; primary?: boolean; badge?: number }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      title={label}
      className={cx(
        'relative grid h-9 w-9 place-items-center rounded-lg transition active:scale-[.98]',
        primary
          ? 'bg-[color:var(--ion-color-primary)] text-white hover:brightness-105'
          : active
            ? 'bg-[color:var(--ion-color-primary)]/12 text-[color:var(--ion-color-primary)] ring-1 ring-[color:var(--ion-color-primary)]/40'
            : `border ${BORDER} ${SURFACE} hover:brightness-95`,
      )}
    >
      {icon}
      {badge != null && badge > 0 && (
        <span className="absolute -right-1 -top-1 grid h-4 min-w-4 place-items-center rounded-full bg-[color:var(--ion-color-primary)] px-1 text-[10px] font-bold text-white">
          {badge}
        </span>
      )}
    </button>
  );
}

export function DataTable<Row>({
  columns, rows, rowKey, title,
  search, onSearchChange, searchable = true, searchPlaceholder = 'Buscar…',
  renderCard, cardTitle, cardIcon, view, defaultView = 'table', onViewChange,
  selectable = false, selectedKeys, onSelectionChange,
  primaryAction, toolbar, rowActions,
  enableExport = false, exportFilename = 'export', enableImport = false, onImport,
  pageSize,
  onRowClick, emptyMessage = 'Sin resultados', loading = false, dense, fill = true,
}: DataTableProps<Row>) {
  // El modo compacto global (Apariencia) aprieta las filas salvo override explícito.
  const { compact } = useTheme();
  const isDense = dense ?? compact;
  const [internalSearch, setInternalSearch] = useState('');
  const [internalView, setInternalView] = useState<DataTableView>(defaultView);
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc');
  const [filters, setFilters] = useState<Record<string, ColumnFilterState>>({});
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [page, setPage] = useState(0);

  const effectiveSearch = search ?? internalSearch;
  const effectiveView = view ?? internalView;
  const canCardView = !!renderCard;

  const filterColumns = useMemo(() => columns.filter((c) => c.filter), [columns]);
  const activeFilterCount = useMemo(
    () => Object.values(filters).filter((f) => (f.kind === 'select' ? f.values.size > 0 : f.from || f.to)).length,
    [filters],
  );

  const processed = useMemo(() => {
    let result = [...rows];
    const q = effectiveSearch.trim().toLowerCase();
    if (q) {
      result = result.filter((row) =>
        columns.some((col) => !col.noSearch && String(rawValue(col, row) ?? '').toLowerCase().includes(q)),
      );
    }
    for (const col of filterColumns) {
      const f = filters[col.key];
      if (!f) continue;
      if (f.kind === 'select' && f.values.size > 0) {
        result = result.filter((row) => f.values.has(String(rawValue(col, row) ?? '')));
      } else if (f.kind === 'dateRange' && (f.from || f.to)) {
        const from = f.from ? new Date(f.from).getTime() : -Infinity;
        const to = f.to ? new Date(f.to).getTime() + 86_400_000 - 1 : Infinity;
        result = result.filter((row) => {
          const raw = rawValue(col, row);
          const t = raw == null ? NaN : new Date(raw).getTime();
          return !Number.isNaN(t) && t >= from && t <= to;
        });
      }
    }
    if (sortKey) {
      const col = columns.find((c) => c.key === sortKey);
      if (col) {
        result.sort((a, b) => {
          const va = rawValue(col, a); const vb = rawValue(col, b);
          if (va == null) return 1;
          if (vb == null) return -1;
          if (va < vb) return sortDir === 'asc' ? -1 : 1;
          if (va > vb) return sortDir === 'asc' ? 1 : -1;
          return 0;
        });
      }
    }
    return result;
  }, [rows, columns, filterColumns, filters, effectiveSearch, sortKey, sortDir]);

  const totalPages = pageSize && pageSize > 0 ? Math.max(1, Math.ceil(processed.length / pageSize)) : 1;
  const clampedPage = Math.min(page, totalPages - 1);
  useEffect(() => { if (page !== clampedPage) setPage(clampedPage); }, [page, clampedPage]);
  const visibleRows = pageSize && pageSize > 0
    ? processed.slice(clampedPage * pageSize, clampedPage * pageSize + pageSize)
    : processed;

  const allSelected = selectable && visibleRows.length > 0 && visibleRows.every((r) => selectedKeys?.has(rowKey(r)));

  function setView(v: DataTableView) { setInternalView(v); onViewChange?.(v); }
  function setSearchValue(v: string) { setInternalSearch(v); onSearchChange?.(v); setPage(0); }
  function isSortable(col: DataTableColumn<Row>) { return col.sortable !== false; }
  function toggleSort(key: string) {
    const col = columns.find((c) => c.key === key);
    if (!col || !isSortable(col)) return;
    if (sortKey === key) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    else { setSortKey(key); setSortDir('asc'); }
  }
  function toggleAll() {
    if (!onSelectionChange) return;
    onSelectionChange(allSelected ? new Set() : new Set([...(selectedKeys ?? []), ...visibleRows.map(rowKey)]));
  }
  function toggleOne(key: string) {
    if (!onSelectionChange) return;
    const next = new Set(selectedKeys);
    if (next.has(key)) next.delete(key); else next.add(key);
    onSelectionChange(next);
  }
  function handleExport() {
    const csvCols = columns.filter((c) => !c.noExport).map((c) => ({ header: colLabel(c), value: (row: Row) => rawValue(c, row) }));
    downloadCsv(exportFilename, toCsv(processed, csvCols));
  }

  const hasTopbar = !!title || searchable || canCardView || filterColumns.length > 0 || enableExport || enableImport || !!primaryAction || !!toolbar;
  const selCount = selectedKeys?.size ?? 0;
  const showFooter = (pageSize && pageSize > 0 && processed.length > 0) || selectable;

  // CSS grid de la vista lista: [checkbox] [columnas…] [acciones]. Sin <table>.
  const gridTemplate = [
    selectable ? '2.75rem' : null,
    ...columns.map((c) => c.width ?? 'minmax(8rem,1fr)'),
    rowActions ? 'auto' : null,
  ].filter(Boolean).join(' ');
  const gridStyle: CSSProperties = { gridTemplateColumns: gridTemplate };
  const alignCls = (a?: 'start' | 'center' | 'end') =>
    a === 'end' ? 'justify-end text-right' : a === 'center' ? 'justify-center text-center' : 'justify-start text-left';

  return (
    <div
      className={cx(
        'flex flex-col overflow-hidden rounded-2xl border shadow-sm', BORDER, CARD,
        fill && 'h-full min-h-0',
      )}
    >
      {/* ───────────── HEADER (card-header) ───────────── */}
      {hasTopbar && (
        <header className={cx('flex flex-col gap-3 border-b px-4 py-3', BORDER, HEADBG)}>
          <div className="flex flex-wrap items-center gap-2">
            {title && (
              <div className="mr-auto flex items-baseline gap-2">
                <h2 className="text-[15px] font-semibold leading-none">{title}</h2>
                <span className={cx('text-xs font-medium', MUTED)}>{processed.length}</span>
              </div>
            )}
            {searchable && (
              <div className={cx('flex h-9 min-w-[12rem] flex-1 items-center gap-2 rounded-lg border px-3 transition focus-within:border-[color:var(--ion-color-primary)]', BORDER, CARD, title ? 'sm:max-w-xs' : '')}>
                <LuSearch size={16} className={MUTED} />
                <input
                  value={effectiveSearch}
                  onChange={(e) => setSearchValue(e.target.value)}
                  placeholder={searchPlaceholder}
                  className="h-full w-full bg-transparent text-[14px] outline-none"
                />
                {effectiveSearch && (
                  <button aria-label="Limpiar" onClick={() => setSearchValue('')} className={cx('grid h-5 w-5 place-items-center rounded', MUTED)}>
                    <LuX size={14} />
                  </button>
                )}
              </div>
            )}
            <div className="flex items-center gap-2">
              {filterColumns.length > 0 && (
                <ToolButton label="Filtros" icon={<LuFilter size={17} />} active={activeFilterCount > 0} badge={activeFilterCount} onClick={() => setFiltersOpen(true)} />
              )}
              {enableImport && <ToolButton label="Importar" icon={<LuUpload size={17} />} onClick={() => setImportOpen(true)} />}
              {enableExport && <ToolButton label="Exportar" icon={<LuDownload size={17} />} onClick={handleExport} />}
              {canCardView && (
                <div className={cx('inline-flex items-center gap-0.5 rounded-lg border p-0.5', BORDER, CARD)}>
                  {([['table', <LuList size={16} key="t" />], ['card', <LuLayoutGrid size={16} key="c" />]] as const).map(([v, ic]) => (
                    <button
                      key={v}
                      aria-label={v === 'table' ? 'Vista tabla' : 'Vista tarjetas'}
                      onClick={() => setView(v)}
                      className={cx(
                        'grid h-7 w-8 place-items-center rounded-md transition',
                        effectiveView === v ? cx(CARD, 'text-[color:var(--ion-color-primary)] shadow-sm ring-1', BORDER) : MUTED,
                      )}
                    >
                      {ic}
                    </button>
                  ))}
                </div>
              )}
              {primaryAction && (
                <ToolButton label={primaryAction.label} icon={primaryAction.icon ?? <LuPlus size={18} />} primary onClick={primaryAction.onClick} />
              )}
            </div>
          </div>

          {/* Barra contextual de selección */}
          {selectable && selCount > 0 && (
            <div className="flex items-center gap-3 rounded-lg bg-[color:var(--ion-color-primary)]/10 px-3 py-1.5 text-[13px] text-[color:var(--ion-color-primary)]">
              <span className="font-semibold">{selCount} seleccionados</span>
              <button onClick={() => onSelectionChange?.(new Set())} className="ml-auto inline-flex items-center gap-1 font-medium hover:underline">
                <LuX size={13} /> Limpiar
              </button>
            </div>
          )}
        </header>
      )}

      {/* ───────────── BODY (scrollable) ───────────── */}
      <div className={cx('relative min-h-0', fill ? 'flex-1 overflow-auto' : 'overflow-x-auto')}>
        {loading && (
          <div className="absolute inset-0 z-20 flex items-center justify-center bg-[color:var(--ion-background-color)]/60 backdrop-blur-[1px]">
            <span className="h-6 w-6 animate-spin rounded-full border-2 border-[color:var(--ion-color-primary)] border-t-transparent" />
          </div>
        )}

        {processed.length === 0 && !loading ? (
          <div className={cx('flex flex-col items-center justify-center gap-3 px-4 py-20 text-center', MUTED)}>
            <span className="grid h-14 w-14 place-items-center rounded-full bg-[color:var(--ion-color-step-100,#eee)]">
              <LuInbox size={26} className="opacity-60" />
            </span>
            <span className="text-sm">{emptyMessage}</span>
          </div>
        ) : effectiveView === 'card' && canCardView ? (
          <div className="grid grid-cols-1 gap-3 p-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {visibleRows.map((row) => {
              const key = rowKey(row);
              const selected = selectedKeys?.has(key);
              return (
                <div
                  key={key}
                  onClick={() => onRowClick?.(row)}
                  className={cx(
                    'flex flex-col overflow-hidden rounded-xl border shadow-sm transition', BORDER, CARD,
                    onRowClick && 'cursor-pointer hover:-translate-y-0.5 hover:border-[color:var(--ion-color-primary)] hover:shadow-md',
                    selected && '!border-[color:var(--ion-color-primary)] ring-2 ring-[color:var(--ion-color-primary)]/40',
                  )}
                >
                  {(cardTitle || cardIcon || selectable) && (
                    <header className={cx('flex items-center gap-2 border-b px-3 py-2.5', BORDER, HEADBG)}>
                      {cardIcon && <span className="shrink-0 text-[color:var(--ion-color-primary)]">{cardIcon(row)}</span>}
                      <span className="min-w-0 flex-1 truncate font-semibold">{cardTitle?.(row)}</span>
                      {selectable && (
                        <IonCheckbox
                          checked={!!selected}
                          onIonChange={() => toggleOne(key)}
                          onClick={(e) => e.stopPropagation()}
                          aria-label="Seleccionar"
                          className="shrink-0"
                        />
                      )}
                    </header>
                  )}
                  <div className="flex-1">{renderCard!(row)}</div>
                  {rowActions && (
                    <div
                      className={cx('flex items-center justify-end gap-0.5 border-t px-2 py-1', BORDER, HEADBG)}
                      onClick={(e) => e.stopPropagation()}
                    >
                      {rowActions(row)}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        ) : (
          // Vista LISTA: NO <table>. Divs con CSS grid (cabecera + filas alineadas).
          <div role="table" className="min-w-[34rem] text-sm">
            {/* Cabecera */}
            <div
              role="row"
              style={gridStyle}
              className={cx('sticky top-0 z-[1] grid items-center gap-2 border-b px-3 py-2.5', BORDER, HEADBG)}
            >
              {selectable && (
                <IonCheckbox checked={allSelected} onIonChange={toggleAll} aria-label="Seleccionar todo" />
              )}
              {columns.map((col) => {
                const sortable = isSortable(col);
                const active = sortKey === col.key;
                return (
                  <div
                    key={col.key}
                    role="columnheader"
                    onClick={() => toggleSort(col.key)}
                    className={cx(
                      'flex items-center gap-1 truncate text-[11px] font-semibold uppercase tracking-[0.05em]', MUTED,
                      alignCls(col.align),
                      sortable && 'cursor-pointer select-none hover:text-[color:var(--ion-text-color)]',
                    )}
                  >
                    <span className="truncate">{col.header}</span>
                    {sortable && (
                      <span aria-hidden className={cx('shrink-0', active ? 'text-[color:var(--ion-color-primary)]' : 'opacity-30')}>
                        {active ? (sortDir === 'asc' ? <LuChevronUp size={13} /> : <LuChevronDown size={13} />) : <LuChevronsUpDown size={13} />}
                      </span>
                    )}
                  </div>
                );
              })}
              {rowActions && (
                <div role="columnheader" className={cx('text-right text-[11px] font-semibold uppercase tracking-[0.05em]', MUTED)}>
                  Acciones
                </div>
              )}
            </div>

            {/* Filas */}
            {visibleRows.map((row) => {
              const key = rowKey(row);
              const selected = selectedKeys?.has(key);
              return (
                <div
                  key={key}
                  role="row"
                  style={gridStyle}
                  onClick={() => onRowClick?.(row)}
                  className={cx(
                    'grid items-center gap-2 border-b px-3 transition-colors last:border-0', BORDER,
                    isDense ? 'py-1.5' : 'py-2.5',
                    onRowClick && 'cursor-pointer',
                    selected ? 'bg-[color:var(--ion-color-primary)]/10' : 'hover:bg-[color:var(--ion-color-step-50,#f7f7f7)]',
                  )}
                >
                  {selectable && (
                    <IonCheckbox
                      checked={!!selected}
                      onIonChange={() => toggleOne(key)}
                      onClick={(e) => e.stopPropagation()}
                      aria-label="Seleccionar fila"
                    />
                  )}
                  {columns.map((col) => (
                    <div key={col.key} role="cell" className={cx('flex min-w-0 items-center', alignCls(col.align))}>
                      <span className="truncate">{col.cell ? col.cell(row) : String(rawValue(col, row) ?? '')}</span>
                    </div>
                  ))}
                  {rowActions && (
                    <div role="cell" className="flex items-center justify-end gap-0.5" onClick={(e) => e.stopPropagation()}>
                      {rowActions(row)}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* ───────────── FOOTER (contador + paginación) ───────────── */}
      {showFooter && (
        <footer className={cx('flex items-center justify-between gap-3 border-t px-4 py-2.5 text-xs', BORDER, HEADBG, MUTED)}>
          <span>
            {pageSize && pageSize > 0 && totalPages > 1 && (
              <>Mostrando {clampedPage * pageSize + 1}–{Math.min((clampedPage + 1) * pageSize, processed.length)} de </>
            )}
            <span className="font-semibold text-[color:var(--ion-text-color)]">{processed.length}</span> {processed.length === 1 ? 'registro' : 'registros'}
          </span>
          {pageSize && pageSize > 0 && totalPages > 1 && (
            <div className="flex items-center gap-1">
              <button aria-label="Anterior" disabled={clampedPage === 0} onClick={() => setPage((p) => Math.max(0, p - 1))} className={cx('grid h-7 w-7 place-items-center rounded-md border disabled:opacity-40', BORDER, CARD, 'hover:bg-[color:var(--ion-color-step-100,#eee)]')}>
                <LuChevronLeft size={16} />
              </button>
              <span className="px-2 font-medium text-[color:var(--ion-text-color)]">{clampedPage + 1} / {totalPages}</span>
              <button aria-label="Siguiente" disabled={clampedPage >= totalPages - 1} onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))} className={cx('grid h-7 w-7 place-items-center rounded-md border disabled:opacity-40', BORDER, CARD, 'hover:bg-[color:var(--ion-color-step-100,#eee)]')}>
                <LuChevronRight size={16} />
              </button>
            </div>
          )}
        </footer>
      )}

      <FiltersModal
        open={filtersOpen}
        onClose={() => setFiltersOpen(false)}
        columns={filterColumns}
        rows={rows}
        filters={filters}
        onApply={(next) => { setFilters(next); setPage(0); setFiltersOpen(false); }}
      />

      {enableImport && (
        <ImportModal
          open={importOpen}
          onClose={() => setImportOpen(false)}
          onImport={async (parsed) => { await onImport?.(parsed); setImportOpen(false); }}
          expectedHeaders={columns.filter((c) => !c.noExport).map((c) => colLabel(c))}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Modal de filtros: multi-select por columna + rango de fechas con calendario.
// ---------------------------------------------------------------------------
function FiltersModal<Row>({
  open, onClose, columns, rows, filters, onApply,
}: {
  open: boolean; onClose: () => void; columns: Array<DataTableColumn<Row>>; rows: Row[];
  filters: Record<string, ColumnFilterState>; onApply: (next: Record<string, ColumnFilterState>) => void;
}) {
  const [draft, setDraft] = useState<Record<string, ColumnFilterState>>(filters);
  useEffect(() => { if (open) setDraft(filters); }, [open, filters]);

  const distinctByCol = useMemo(() => {
    const map: Record<string, string[]> = {};
    for (const col of columns) {
      if (col.filter !== 'select') continue;
      const set = new Set<string>();
      for (const row of rows) {
        const v = rawValue(col, row);
        if (v != null && v !== '') set.add(String(v));
      }
      map[col.key] = [...set].sort((a, b) => a.localeCompare(b));
    }
    return map;
  }, [columns, rows]);

  function toggleValue(key: string, value: string) {
    setDraft((d) => {
      const cur = d[key];
      const values = new Set(cur?.kind === 'select' ? cur.values : []);
      if (values.has(value)) values.delete(value); else values.add(value);
      return { ...d, [key]: { kind: 'select', values } };
    });
  }
  function setRange(key: string, part: 'from' | 'to', value: string) {
    setDraft((d) => {
      const cur = d[key];
      const base = cur?.kind === 'dateRange' ? cur : { kind: 'dateRange' as const, from: '', to: '' };
      return { ...d, [key]: { ...base, [part]: value } };
    });
  }

  const activeCount = Object.values(draft).filter((f) => (f.kind === 'select' ? f.values.size > 0 : f.from || f.to)).length;
  const dateInput = `rounded-lg border ${BORDER} ${SURFACE} px-3 py-2 text-sm outline-none focus:border-[color:var(--ion-color-primary)]`;

  return (
    <Modal
      open={open} onClose={onClose} title="Filtros" icon={<LuFilter size={18} />}
      footer={
        <>
          <button onClick={() => setDraft({})} disabled={activeCount === 0} className={cx('h-9 rounded-lg px-3 text-[13px] font-medium disabled:opacity-40', MUTED, `hover:bg-[color:var(--ion-color-step-50,#f7f7f7)]`)}>
            Limpiar
          </button>
          <button onClick={() => onApply(draft)} className="inline-flex h-9 items-center rounded-lg bg-[color:var(--ion-color-primary)] px-4 text-[13px] font-medium text-white hover:brightness-105">
            Aplicar{activeCount > 0 && ` (${activeCount})`}
          </button>
        </>
      }
    >
      <div className="flex flex-col gap-5">
        {columns.map((col) => (
          <div key={col.key} className="flex flex-col gap-2">
            <span className="text-sm font-medium">{colLabel(col)}</span>
            {col.filter === 'select' ? (
              <div className="flex flex-wrap gap-1.5">
                {(distinctByCol[col.key] ?? []).map((v) => {
                  const cur = draft[col.key];
                  const checked = cur?.kind === 'select' && cur.values.has(v);
                  return (
                    <button
                      key={v}
                      onClick={() => toggleValue(col.key, v)}
                      className={cx(
                        'inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs transition-colors',
                        checked
                          ? 'border-[color:var(--ion-color-primary)] bg-[color:var(--ion-color-primary)]/15 text-[color:var(--ion-color-primary)]'
                          : `${BORDER} ${MUTED} hover:text-[color:var(--ion-text-color)]`,
                      )}
                    >
                      {checked && <LuCheck size={12} />}{v}
                    </button>
                  );
                })}
                {(distinctByCol[col.key]?.length ?? 0) === 0 && <span className={cx('text-xs', MUTED)}>Sin valores</span>}
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <label className={cx('flex flex-1 flex-col gap-1 text-xs', MUTED)}>
                  Desde
                  <input type="date" value={draft[col.key]?.kind === 'dateRange' ? (draft[col.key] as { from: string }).from : ''} onChange={(e) => setRange(col.key, 'from', e.target.value)} className={dateInput} />
                </label>
                <label className={cx('flex flex-1 flex-col gap-1 text-xs', MUTED)}>
                  Hasta
                  <input type="date" value={draft[col.key]?.kind === 'dateRange' ? (draft[col.key] as { to: string }).to : ''} onChange={(e) => setRange(col.key, 'to', e.target.value)} className={dateInput} />
                </label>
              </div>
            )}
          </div>
        ))}
      </div>
    </Modal>
  );
}

// ---------------------------------------------------------------------------
// Modal de import: drag & drop elegante + preview de las primeras filas.
// ---------------------------------------------------------------------------
function ImportModal({
  open, onClose, onImport, expectedHeaders,
}: {
  open: boolean; onClose: () => void;
  onImport: (rows: Array<Record<string, string>>) => void | Promise<void>;
  expectedHeaders: string[];
}) {
  const [parsed, setParsed] = useState<{ headers: string[]; rows: Array<Record<string, string>> } | null>(null);
  const [fileName, setFileName] = useState('');
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) { setParsed(null); setFileName(''); setError(''); setDragging(false); }
  }, [open]);

  async function readFile(file: File) {
    setError('');
    if (!file.name.toLowerCase().endsWith('.csv')) { setError('El archivo debe ser .csv'); return; }
    try {
      const result = parseCsv(await file.text());
      if (result.rows.length === 0) { setError('El CSV no contiene filas'); return; }
      setFileName(file.name);
      setParsed(result);
    } catch { setError('No se pudo leer el archivo'); }
  }
  async function confirm() {
    if (!parsed) return;
    setBusy(true);
    try { await onImport(parsed.rows); } finally { setBusy(false); }
  }

  const previewCols = parsed?.headers.slice(0, 5) ?? [];

  return (
    <Modal
      open={open} onClose={onClose} size="lg" title="Importar CSV" icon={<LuUpload size={18} />}
      footer={
        <>
          <button onClick={onClose} className={cx('h-9 rounded-lg px-3 text-[13px] font-medium', MUTED, `hover:bg-[color:var(--ion-color-step-50,#f7f7f7)]`)}>Cancelar</button>
          <button onClick={confirm} disabled={!parsed || busy} className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-[color:var(--ion-color-primary)] px-4 text-[13px] font-medium text-white hover:brightness-105 disabled:opacity-40">
            {busy ? <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" /> : <LuCheck size={15} />}
            Importar {parsed ? `${parsed.rows.length} filas` : ''}
          </button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => { e.preventDefault(); setDragging(false); const f = e.dataTransfer.files?.[0]; if (f) readFile(f); }}
          className={cx(
            'flex flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed px-6 py-10 text-center transition-colors',
            dragging
              ? 'border-[color:var(--ion-color-primary)] bg-[color:var(--ion-color-primary)]/10'
              : `${BORDER} hover:border-[color:var(--ion-color-primary)]/60 hover:bg-[color:var(--ion-color-step-50,#f7f7f7)]`,
          )}
        >
          <span className="grid h-12 w-12 place-items-center rounded-full bg-[color:var(--ion-color-primary)]/15 text-[color:var(--ion-color-primary)]">
            <LuUpload size={22} />
          </span>
          <div>
            <p className="font-medium">{fileName || 'Arrastra un CSV o haz clic para elegir'}</p>
            <p className={cx('text-xs', MUTED)}>Codificación UTF-8 · separador coma</p>
          </div>
          <input ref={inputRef} type="file" accept=".csv,text/csv" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f) readFile(f); e.target.value = ''; }} />
        </button>

        {error && (
          <p className="flex items-center gap-2 rounded-lg bg-[color:var(--ion-color-danger,#eb445a)]/10 px-3 py-2 text-sm text-[color:var(--ion-color-danger,#eb445a)]">
            <LuTriangleAlert size={16} /> {error}
          </p>
        )}

        {expectedHeaders.length > 0 && (
          <p className={cx('text-xs', MUTED)}>Columnas esperadas: {expectedHeaders.join(', ')}</p>
        )}

        {parsed && (
          <div className="flex flex-col gap-2">
            <span className="text-sm font-medium">Vista previa · {parsed.rows.length} filas</span>
            <div className={cx('overflow-x-auto rounded-lg border', BORDER)}>
              <table className="w-full text-xs">
                <thead>
                  <tr className={cx('border-b', BORDER, SURFACE)}>
                    {previewCols.map((h) => (
                      <th key={h} className={cx('whitespace-nowrap px-2.5 py-1.5 text-left font-semibold', MUTED)}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {parsed.rows.slice(0, 4).map((row, i) => (
                    <tr key={i} className={cx('border-b last:border-0', BORDER)}>
                      {previewCols.map((h) => (<td key={h} className="whitespace-nowrap px-2.5 py-1.5">{row[h]}</td>))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </Modal>
  );
}
