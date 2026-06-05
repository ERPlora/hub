import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `audit_log` (Stencil). Vista "reports": lista de informes de
// cumplimiento + generación de un informe nuevo sobre un rango de fechas. Parte de la pieza
// `ui.entry` (modules/audit_log/dist/audit_log.esm.js).
//
// El componente NUNCA toca la BD. La lógica de conteo / numeración del informe vive en el
// handler WASM (audit_log.reports.generate); aquí solo se invoca vía erplora.command.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface AuditReport {
  id: string;
  report_number: string;
  generated_at: string;
  generated_by_ref: string;
  period_start: string;
  period_end: string;
  total_events: number;
  status: string;
  output_location: string;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-audit-log-reports',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .form { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; }
    .form ion-input { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:10rem; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpAuditLogReports {
  @State() reports: AuditReport[] = [];
  @State() loading = true;
  @State() error = '';
  @State() periodStart = '';
  @State() periodEnd = '';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'report_number', header: 'Nº informe' },
    { key: 'generated_at', header: 'Generado', format: (r) => this.fmtDate(r.generated_at as string) },
    { key: 'period_start', header: 'Desde', format: (r) => this.fmtDate(r.period_start as string) },
    { key: 'period_end', header: 'Hasta', format: (r) => this.fmtDate(r.period_end as string) },
    { key: 'total_events', header: 'Eventos', align: 'right' },
    { key: 'status', header: 'Estado' },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off = erplora().on('audit_log.report.generated', () => this.refresh());
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
      const reports = await erplora().query<AuditReport[]>('audit_log.reports.list', {
        status: '',
        limit: 100,
      });
      this.reports = reports ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando informes';
    } finally {
      this.loading = false;
    }
  }

  private async generate(ev: Event) {
    ev.preventDefault();
    if (!this.periodStart || !this.periodEnd) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('audit_log.reports.generate', {
        period_start: this.periodStart,
        period_end: this.periodEnd,
        filters: {},
      });
      this.periodStart = '';
      this.periodEnd = '';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo generar el informe';
    } finally {
      this.saving = false;
    }
  }

  private fmtDate(iso: string): string {
    if (!iso) return '—';
    const d = new Date(iso);
    return isNaN(d.getTime()) ? iso : d.toLocaleString();
  }

  render() {
    return (
      <div>
        <header>
          <h2>Informes de cumplimiento</h2>
        </header>

        <form class="form" onSubmit={(e) => this.generate(e)}>
          <ion-input
            type="date"
            placeholder="Desde"
            value={this.periodStart}
            onIonInput={(e: any) => (this.periodStart = e.target.value)}
          />
          <ion-input
            type="date"
            placeholder="Hasta"
            value={this.periodEnd}
            onIonInput={(e: any) => (this.periodEnd = e.target.value)}
          />
          <ion-button type="submit" size="small" disabled={this.saving || !this.periodStart || !this.periodEnd}>
            {this.saving ? 'Generando…' : 'Generar informe'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.reports as unknown as Record<string, unknown>[]}
          searchKeys={['report_number', 'status']}
          searchPlaceholder="Buscar nº o estado…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin informes.'}
        />
      </div>
    );
  }
}
