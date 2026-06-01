// DataTable reutilizable: búsqueda + columnas + paginación simple + acciones de fila.
// (Versión inicial; bulk-select/sort se ampliará al portar las vistas reales.)
import { useMemo, useState, type ReactNode } from 'react';
import { Card } from './Card';
import { Searchbar } from './Searchbar';
import { Icon } from './Icon';

export interface Column<T> {
  key: string;
  header: string;
  render?: (row: T) => ReactNode;
  className?: string;
}

export interface DataTableProps<T> {
  columns: Column<T>[];
  rows: T[];
  /** Campos sobre los que filtra el buscador. */
  searchKeys?: (keyof T)[];
  rowKey: (row: T) => string;
  pageSize?: number;
  emptyMessage?: string;
  toolbar?: ReactNode;
}

export function DataTable<T extends Record<string, unknown>>({
  columns, rows, searchKeys, rowKey, pageSize = 10, emptyMessage = 'Sin resultados', toolbar,
}: DataTableProps<T>) {
  const [q, setQ] = useState('');
  const [page, setPage] = useState(0);

  const filtered = useMemo(() => {
    if (!q || !searchKeys?.length) return rows;
    const needle = q.toLowerCase();
    return rows.filter((r) => searchKeys.some((k) => String(r[k] ?? '').toLowerCase().includes(needle)));
  }, [q, rows, searchKeys]);

  const pages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const current = Math.min(page, pages - 1);
  const slice = filtered.slice(current * pageSize, current * pageSize + pageSize);

  return (
    <Card className="overflow-hidden">
      <div className="flex flex-col gap-3 border-b p-4 sm:flex-row sm:items-center sm:justify-between" style={{ borderColor: 'var(--line)' }}>
        <div className="sm:w-80">
          {searchKeys?.length ? <Searchbar value={q} onChange={(v) => { setQ(v); setPage(0); }} /> : <span />}
        </div>
        {toolbar}
      </div>

      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-[14px]">
          <thead>
            <tr style={{ background: 'var(--surface-2)' }}>
              {columns.map((c) => (
                <th key={c.key} className="px-4 py-3 text-left text-[12px] font-semibold uppercase tracking-[0.04em]" style={{ color: 'var(--muted)' }}>
                  {c.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {slice.length === 0 ? (
              <tr>
                <td colSpan={columns.length} className="px-4 py-16 text-center text-[14px]" style={{ color: 'var(--muted)' }}>{emptyMessage}</td>
              </tr>
            ) : (
              slice.map((row) => (
                <tr key={rowKey(row)} className="row-hover border-t" style={{ borderColor: 'var(--line-soft)' }}>
                  {columns.map((c) => (
                    <td key={c.key} className={`px-4 py-3 ${c.className ?? ''}`} style={{ color: 'var(--ink)' }}>
                      {c.render ? c.render(row) : String(row[c.key] ?? '')}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {pages > 1 && (
        <div className="flex items-center justify-between border-t px-4 py-3 text-[13px]" style={{ borderColor: 'var(--line)', color: 'var(--muted)' }}>
          <span>{filtered.length} resultados</span>
          <div className="flex items-center gap-1">
            <button disabled={current === 0} onClick={() => setPage(current - 1)} className="grid h-8 w-8 place-items-center rounded-lg disabled:opacity-40 hover:bg-[var(--surface-2)]"><Icon name="chevron-left" size={16} /></button>
            <span className="px-2">{current + 1} / {pages}</span>
            <button disabled={current >= pages - 1} onClick={() => setPage(current + 1)} className="grid h-8 w-8 place-items-center rounded-lg disabled:opacity-40 hover:bg-[var(--surface-2)]"><Icon name="chevron-right" size={16} /></button>
          </div>
        </div>
      )}
    </Card>
  );
}
