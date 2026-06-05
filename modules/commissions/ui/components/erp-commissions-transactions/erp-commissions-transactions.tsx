import { Component, State, h } from '@stencil/core';
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn, DataTableAction } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `commissions` — vista "Transactions". Lista las transacciones
// de comisión devengadas, con filtro por estado, y permite aprobar pendientes.
// NO toca la BD: usa el SDK (erplora.query/command/on).

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface CommissionTransaction {
  id: string;
  staff_name: string;
  sale_reference: string;
  sale_amount: string;
  commission_rate: string;
  commission_amount: string;
  net_commission: string;
  status: string;
  transaction_date: string;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-commissions-transactions',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .filters { display:flex; gap:.5rem; align-items:end; margin:.5rem 0 1rem; }
    .filters ion-select { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:10rem; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpCommissionsTransactions {
  @State() rows: CommissionTransaction[] = [];
  @State() loading = true;
  @State() error = '';
  @State() status = '';
  @State() busyId = '';

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'transaction_date', header: 'Fecha' },
    { key: 'staff_name', header: 'Staff' },
    { key: 'sale_reference', header: 'Venta' },
    { key: 'commission_amount', header: 'Comisión', align: 'right', format: (r) => Number(r.commission_amount).toFixed(2) },
    { key: 'net_commission', header: 'Neto', align: 'right', format: (r) => Number(r.net_commission).toFixed(2) },
    { key: 'status', header: 'Estado' },
  ];

  private actions: DataTableAction[] = [{ id: 'approve', label: 'Aprobar', color: 'primary' }];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('commissions.transaction.approved', () => this.refresh());
      const off2 = erplora().on('commissions.transaction.created', () => this.refresh());
      this.unsub = () => {
        off1();
        off2();
      };
    } catch {
      /* sin SDK (preview) */
    }
  }

  disconnectedCallback() {
    this.unsub?.();
  }

  private async refresh() {
    this.loading = true;
    this.error = '';
    try {
      const rows = await erplora().query<CommissionTransaction[]>('commissions.transactions.list', {
        status: this.status,
        staff_id: '',
        date_from: '',
        date_to: '',
        limit: 100,
      });
      this.rows = rows ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando transacciones';
    } finally {
      this.loading = false;
    }
  }

  private async handleAction(ev: CustomEvent<{ actionId: string; row: Record<string, unknown> }>) {
    if (ev.detail.actionId !== 'approve') return;
    const row = ev.detail.row as unknown as CommissionTransaction;
    if (row.status !== 'pending') {
      this.error = 'Solo se pueden aprobar transacciones pendientes.';
      return;
    }
    this.busyId = row.id;
    this.error = '';
    try {
      await erplora().command('commissions.transactions.approve', { transaction_id: row.id });
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo aprobar';
    } finally {
      this.busyId = '';
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Transacciones de comisión</h2>
        </header>

        <div class="filters">
          <ion-select
            placeholder="Estado…"
            value={this.status}
            onIonChange={(e: any) => {
              this.status = e.target.value;
              this.refresh();
            }}
          >
            <ion-select-option value="">Todos</ion-select-option>
            <ion-select-option value="pending">Pendiente</ion-select-option>
            <ion-select-option value="approved">Aprobada</ion-select-option>
            <ion-select-option value="paid">Pagada</ion-select-option>
            <ion-select-option value="cancelled">Cancelada</ion-select-option>
            <ion-select-option value="adjusted">Ajustada</ion-select-option>
          </ion-select>
        </div>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.rows as unknown as Record<string, unknown>[]}
          searchKeys={['staff_name', 'sale_reference']}
          searchPlaceholder="Buscar staff o venta…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin transacciones.'}
          actions={this.actions}
          onRowAction={(e: CustomEvent<{ actionId: string; row: Record<string, unknown> }>) => this.handleAction(e)}
        />
      </div>
    );
  }
}
