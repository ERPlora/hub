import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn, DataTableAction } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `general_ledger` (Stencil) — vista Ledger.
// Lista de asientos por periodo/estado, con acción de postear un asiento en borrador.
// NO toca la BD: llama al SDK (erplora.query/command/on). El cuadre de partida doble y
// la generación del nº de asiento viven en el handler WASM (ver WASM-TODO.md).

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface LedgerEntry {
  id: string;
  entry_number: string;
  entry_date: string;
  period_id: string;
  reference: string;
  description: string;
  status: string;
  total_debit: string;
  total_credit: string;
}

interface LedgerPeriod {
  id: string;
  name: string;
  status: string;
}

const STATUSES = ['', 'draft', 'posted', 'reversed'];

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-general-ledger-ledger',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; flex-wrap:wrap; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpGeneralLedgerLedger {
  @State() entries: LedgerEntry[] = [];
  @State() periods: LedgerPeriod[] = [];
  @State() loading = true;
  @State() error = '';
  @State() periodFilter = '';
  @State() statusFilter = 'posted';
  @State() busyId = '';

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'entry_number', header: 'Nº' },
    { key: 'entry_date', header: 'Fecha' },
    { key: 'period_id', header: 'Periodo', format: (r) => this.periodName(r.period_id as string) },
    { key: 'reference', header: 'Referencia' },
    { key: 'status', header: 'Estado' },
    { key: 'total_debit', header: 'Debe', align: 'right', format: (r) => Number(r.total_debit).toFixed(2) },
    { key: 'total_credit', header: 'Haber', align: 'right', format: (r) => Number(r.total_credit).toFixed(2) },
  ];

  private rowActions: DataTableAction[] = [{ id: 'post', label: 'Postear', color: 'primary' }];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('general_ledger.entry.created', () => this.refresh());
      const off2 = erplora().on('general_ledger.entry.posted', () => this.refresh());
      const off3 = erplora().on('general_ledger.entry.reversed', () => this.refresh());
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
      const [periods, entries] = await Promise.all([
        erplora().query<LedgerPeriod[]>('general_ledger.periods.list', { status: '' }),
        erplora().query<LedgerEntry[]>('general_ledger.entries.list', {
          status: this.statusFilter,
          period_id: this.periodFilter,
          limit: 100,
        }),
      ]);
      this.periods = periods ?? [];
      this.entries = entries ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando asientos';
    } finally {
      this.loading = false;
    }
  }

  private async onRowAction(ev: CustomEvent<{ actionId: string; row: Record<string, unknown> }>) {
    const { actionId, row } = ev.detail;
    const entry = row as unknown as LedgerEntry;
    if (actionId !== 'post') return;
    if (entry.status !== 'draft') {
      this.error = 'Solo se pueden postear asientos en borrador';
      return;
    }
    this.busyId = entry.id;
    this.error = '';
    try {
      await erplora().command('general_ledger.entries.post', { entry_id: entry.id });
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo postear el asiento';
    } finally {
      this.busyId = '';
    }
  }

  private periodName(id: string): string {
    return this.periods.find((p) => p.id === id)?.name ?? '—';
  }

  render() {
    return (
      <div>
        <header>
          <h2>Libro de asientos</h2>
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
          <ion-select
            placeholder="Estado…"
            value={this.statusFilter}
            onIonChange={(e: any) => {
              this.statusFilter = e.target.value;
              this.refresh();
            }}
          >
            {STATUSES.map((s) => (
              <ion-select-option value={s} key={s || 'all'}>
                {s || 'todos'}
              </ion-select-option>
            ))}
          </ion-select>
        </header>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.entries as unknown as Record<string, unknown>[]}
          searchKeys={['entry_number', 'reference', 'description']}
          searchPlaceholder="Buscar asiento…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin asientos.'}
          actions={this.rowActions}
          onRowAction={(e: CustomEvent) => this.onRowAction(e)}
        />
      </div>
    );
  }
}
