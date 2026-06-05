import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `reports` (Stencil): historial de ejecuciones (runs).
// Solo lectura: lista los runs con su estado, formato de salida y nº de filas.
// NO toca la BD; llama al SDK (erplora.query/on). Usa el DataTable compartido.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface ReportRun {
  id: string;
  report_id: string;
  run_number: string;
  status: string;
  total_rows: number;
  output_format: string;
  completed_at: string | null;
}

const STATUSES = ['', 'running', 'completed', 'failed'];

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-reports-runs',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .form { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; }
    .form ion-select { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:8rem; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpReportsRuns {
  @State() runs: ReportRun[] = [];
  @State() loading = true;
  @State() error = '';
  @State() statusFilter = '';

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'run_number', header: 'Nº ejecución' },
    { key: 'status', header: 'Estado' },
    { key: 'output_format', header: 'Formato' },
    { key: 'total_rows', header: 'Filas', align: 'right', format: (r) => String(r.total_rows ?? 0) },
    { key: 'completed_at', header: 'Completado', format: (r) => (r.completed_at as string) ?? '—' },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off = erplora().on('reports.run.completed', () => this.refresh());
      this.unsub = off;
    } catch {
      /* sin SDK (preview) → sin reactividad en vivo */
    }
  }

  disconnectedCallback() {
    this.unsub?.();
  }

  private async refresh() {
    this.loading = true;
    this.error = '';
    try {
      const runs = await erplora().query<ReportRun[]>('reports.runs.list', {
        report_id: '',
        status: this.statusFilter,
      });
      this.runs = runs ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando ejecuciones';
    } finally {
      this.loading = false;
    }
  }

  private async onStatusChange(value: string) {
    this.statusFilter = value;
    await this.refresh();
  }

  render() {
    return (
      <div>
        <header>
          <h2>Ejecuciones</h2>
        </header>

        <div class="form">
          <ion-select
            placeholder="Estado…"
            value={this.statusFilter}
            onIonChange={(e: any) => this.onStatusChange(e.target.value)}
          >
            {STATUSES.map((s) => (
              <ion-select-option value={s} key={s || 'all'}>
                {s || 'Todos'}
              </ion-select-option>
            ))}
          </ion-select>
        </div>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.runs as unknown as Record<string, unknown>[]}
          searchKeys={['run_number', 'status']}
          searchPlaceholder="Buscar nº de ejecución…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin ejecuciones.'}
        />
      </div>
    );
  }
}
