import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn, DataTableAction } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `financial_statements` (Stencil). Mini-app: lista de informes
// generados (Balance / P&L / Cash Flow), filtrable por tipo, con acción de finalizar
// (draft → final). La generación de informes y la comparación viven en Rust/WASM; este
// componente NO toca la BD: llama al SDK (erplora.query/command/on).

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface GeneratedReport {
  id: string;
  template_id: string;
  report_type: string;
  period_start: string | null;
  period_end: string | null;
  status: string;
}

const REPORT_TYPE_FILTERS = ['', 'balance_sheet', 'profit_loss', 'cash_flow', 'custom'];

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-financial-statements-reports',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .filters { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; }
    .filters ion-select { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:10rem; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpFinancialStatementsReports {
  @State() reports: GeneratedReport[] = [];
  @State() loading = true;
  @State() error = '';
  @State() filterType = '';

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'report_type', header: 'Tipo' },
    { key: 'period_start', header: 'Desde', format: (r) => (r.period_start as string) ?? '—' },
    { key: 'period_end', header: 'Hasta', format: (r) => (r.period_end as string) ?? '—' },
    { key: 'status', header: 'Estado' },
  ];

  // Acción por fila: finalizar (draft → final). El botón se muestra siempre; el guard de
  // estado lo aplica el SQL (WHERE status='draft') y el handler de la acción aquí.
  private actions: DataTableAction[] = [{ id: 'finalize', label: 'Finalizar', color: 'primary' }];

  private onRowAction(ev: CustomEvent<{ actionId: string; row: Record<string, unknown> }>) {
    const { actionId, row } = ev.detail;
    if (actionId === 'finalize' && row.status === 'draft') {
      this.finalize(row.id as string);
    }
  }

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('financial_statements.report.generated', () => this.refresh());
      const off2 = erplora().on('financial_statements.report.finalized', () => this.refresh());
      this.unsub = () => {
        off1();
        off2();
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
      const reports = await erplora().query<GeneratedReport[]>('financial_statements.reports.list', {
        report_type: this.filterType,
        period_start: '',
        period_end: '',
        limit: 100,
      });
      this.reports = reports ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando informes';
    } finally {
      this.loading = false;
    }
  }

  private async finalize(reportId: string) {
    if (!reportId) return;
    this.error = '';
    try {
      await erplora().command('financial_statements.reports.finalize', { report_id: reportId });
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo finalizar el informe';
    }
  }

  private async onFilterChange(value: string) {
    this.filterType = value;
    await this.refresh();
  }

  render() {
    return (
      <div>
        <header>
          <h2>Informes generados</h2>
        </header>

        <div class="filters">
          <ion-select
            placeholder="Tipo…"
            value={this.filterType}
            onIonChange={(e: any) => this.onFilterChange(e.target.value)}
          >
            {REPORT_TYPE_FILTERS.map((t) => (
              <ion-select-option value={t} key={t || 'all'}>
                {t || 'Todos'}
              </ion-select-option>
            ))}
          </ion-select>
        </div>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.reports as unknown as Record<string, unknown>[]}
          actions={this.actions}
          searchKeys={['report_type', 'status']}
          searchPlaceholder="Buscar informe…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin informes generados.'}
          onRowAction={(e: CustomEvent) => this.onRowAction(e)}
        />
      </div>
    );
  }
}
