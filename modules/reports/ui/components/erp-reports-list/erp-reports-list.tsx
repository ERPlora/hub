import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn, DataTableAction } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `reports` (Stencil). Mini-app: lista de definiciones de
// informe + alta rápida + ejecución de un informe. Es la pieza `ui.entry` que el
// shell carga en runtime (modules/reports/dist/reports.esm.js).
//
// La lógica vive en Rust/WASM: este componente NO toca la BD; llama al SDK
// (erplora.query/command/on). El listado usa el DataTable compartido + Ionic.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface Report {
  id: string;
  code: string;
  name: string;
  description: string;
  report_type: string;
  data_source: string;
  is_public: number;
}

const REPORT_TYPES = ['table', 'pivot', 'timeseries', 'comparison', 'funnel'];

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-reports-list',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .form { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; }
    .form ion-input, .form ion-select { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:8rem; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpReportsList {
  @State() reports: Report[] = [];
  @State() loading = true;
  @State() error = '';
  @State() typeFilter = '';
  @State() newCode = '';
  @State() newName = '';
  @State() newSource = '';
  @State() newType = 'table';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'code', header: 'Código' },
    { key: 'name', header: 'Nombre' },
    { key: 'report_type', header: 'Tipo' },
    { key: 'data_source', header: 'Fuente' },
    { key: 'is_public', header: 'Público', format: (r) => (Number(r.is_public) ? 'Sí' : 'No') },
  ];

  private actions: DataTableAction[] = [{ id: 'run', label: 'Ejecutar', icon: 'play-outline' }];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('reports.report.created', () => this.refresh());
      const off2 = erplora().on('reports.report.updated', () => this.refresh());
      const off3 = erplora().on('reports.report.deleted', () => this.refresh());
      this.unsub = () => {
        off1();
        off2();
        off3();
      };
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
      const reports = await erplora().query<Report[]>('reports.reports.list', {
        report_type: this.typeFilter,
        data_source: '',
        owner_ref: '',
      });
      this.reports = reports ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando informes';
    } finally {
      this.loading = false;
    }
  }

  private async createReport(ev: Event) {
    ev.preventDefault();
    if (!this.newCode.trim() || !this.newName.trim() || !this.newSource.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('reports.reports.create', {
        code: this.newCode.trim(),
        name: this.newName.trim(),
        data_source: this.newSource.trim(),
        report_type: this.newType,
        columns: [],
        description: '',
        is_public: false,
      });
      this.newCode = '';
      this.newName = '';
      this.newSource = '';
      this.newType = 'table';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear el informe';
    } finally {
      this.saving = false;
    }
  }

  private async runReport(id: string) {
    this.error = '';
    try {
      await erplora().command('reports.reports.run', { report_id: id, output_format: 'json' });
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo ejecutar el informe';
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Informes</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createReport(e)}>
          <ion-input
            placeholder="Código"
            value={this.newCode}
            onIonInput={(e: any) => (this.newCode = e.target.value)}
          />
          <ion-input
            placeholder="Nombre"
            value={this.newName}
            onIonInput={(e: any) => (this.newName = e.target.value)}
          />
          <ion-input
            placeholder="Fuente de datos"
            value={this.newSource}
            onIonInput={(e: any) => (this.newSource = e.target.value)}
          />
          <ion-select
            placeholder="Tipo…"
            value={this.newType}
            onIonChange={(e: any) => (this.newType = e.target.value)}
          >
            {REPORT_TYPES.map((t) => (
              <ion-select-option value={t} key={t}>
                {t}
              </ion-select-option>
            ))}
          </ion-select>
          <ion-button
            type="submit"
            size="small"
            disabled={this.saving || !this.newCode || !this.newName || !this.newSource}
          >
            {this.saving ? 'Guardando…' : 'Añadir'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.reports as unknown as Record<string, unknown>[]}
          searchKeys={['code', 'name', 'data_source']}
          searchPlaceholder="Buscar código o nombre…"
          actions={this.actions}
          onRowAction={(e: CustomEvent<{ actionId: string; row: Record<string, unknown> }>) =>
            this.runReport(e.detail.row.id as string)
          }
          emptyMessage={this.loading ? 'Cargando…' : 'Sin informes.'}
        />
      </div>
    );
  }
}
