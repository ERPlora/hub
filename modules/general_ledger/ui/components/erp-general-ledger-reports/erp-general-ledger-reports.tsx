import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `general_ledger` (Stencil) — vista Reports.
// Balance de comprobación: cuentas activas con su debe/haber acumulado. Filtros por
// periodo y fecha tope. NO toca la BD: llama al SDK (erplora.query). El neto firmado
// por normal_balance y el cuadre global se calculan aquí a partir de los agregados.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface TrialBalanceRow {
  account_id: string;
  code: string;
  name: string;
  account_type: string;
  normal_balance: string;
  total_debit: string;
  total_credit: string;
}

interface LedgerPeriod {
  id: string;
  name: string;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-general-ledger-reports',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; flex-wrap:wrap; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .totals { display:flex; gap:1.5rem; margin:.75rem 0; font-weight:600; }
    .totals .ok { color:#2b8a3e; }
    .totals .bad { color:#d9480f; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpGeneralLedgerReports {
  @State() rows: TrialBalanceRow[] = [];
  @State() periods: LedgerPeriod[] = [];
  @State() loading = true;
  @State() error = '';
  @State() periodFilter = '';

  private columns: DataTableColumn[] = [
    { key: 'code', header: 'Código' },
    { key: 'name', header: 'Nombre' },
    { key: 'account_type', header: 'Tipo' },
    { key: 'total_debit', header: 'Debe', align: 'right', format: (r) => Number(r.total_debit).toFixed(2) },
    { key: 'total_credit', header: 'Haber', align: 'right', format: (r) => Number(r.total_credit).toFixed(2) },
    { key: 'net', header: 'Neto', align: 'right', format: (r) => this.net(r as unknown as TrialBalanceRow).toFixed(2) },
  ];

  async componentWillLoad() {
    await this.loadPeriods();
    await this.refresh();
  }

  private async loadPeriods() {
    try {
      this.periods = (await erplora().query<LedgerPeriod[]>('general_ledger.periods.list', { status: '' })) ?? [];
    } catch {
      this.periods = [];
    }
  }

  private async refresh() {
    this.loading = true;
    this.error = '';
    try {
      this.rows =
        (await erplora().query<TrialBalanceRow[]>('general_ledger.reports.trial_balance', {
          period_id: this.periodFilter,
          as_of_date: '',
        })) ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando el balance de comprobación';
    } finally {
      this.loading = false;
    }
  }

  private net(r: TrialBalanceRow): number {
    const d = Number(r.total_debit);
    const c = Number(r.total_credit);
    return r.normal_balance === 'debit' ? d - c : c - d;
  }

  private get grandDebit(): number {
    return this.rows.reduce((s, r) => s + Number(r.total_debit), 0);
  }

  private get grandCredit(): number {
    return this.rows.reduce((s, r) => s + Number(r.total_credit), 0);
  }

  render() {
    const balanced = this.grandDebit.toFixed(2) === this.grandCredit.toFixed(2);
    return (
      <div>
        <header>
          <h2>Balance de comprobación</h2>
          <ion-select
            placeholder="Periodo…"
            value={this.periodFilter}
            onIonChange={(e: any) => {
              this.periodFilter = e.target.value;
              this.refresh();
            }}
          >
            <ion-select-option value="">Todos los periodos</ion-select-option>
            {this.periods.map((p) => (
              <ion-select-option value={p.id} key={p.id}>
                {p.name}
              </ion-select-option>
            ))}
          </ion-select>
        </header>

        {this.error && <p class="err">{this.error}</p>}

        <div class="totals">
          <span>Total Debe: {this.grandDebit.toFixed(2)}</span>
          <span>Total Haber: {this.grandCredit.toFixed(2)}</span>
          <span class={balanced ? 'ok' : 'bad'}>{balanced ? 'Cuadrado' : 'Descuadrado'}</span>
        </div>

        <data-table
          columns={this.columns}
          rows={this.rows as unknown as Record<string, unknown>[]}
          searchKeys={['code', 'name', 'account_type']}
          searchPlaceholder="Buscar cuenta…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin cuentas activas.'}
        />
      </div>
    );
  }
}
