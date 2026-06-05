import { Component, State, h } from '@stencil/core';
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn, DataTableAction } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `commissions` — vista "Payouts". Lista los lotes de pago
// y permite aprobar (pending→approved) y procesar (approved→completed).
// La creación del lote (agregación batch de transacciones) y el procesado real viven
// en WASM (ver WASM-TODO.md). NO toca la BD: usa el SDK.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface CommissionPayout {
  id: string;
  reference: string;
  staff_name: string;
  period_start: string;
  period_end: string;
  gross_amount: string;
  net_amount: string;
  transaction_count: number;
  status: string;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-commissions-payouts',
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
export class ErpCommissionsPayouts {
  @State() rows: CommissionPayout[] = [];
  @State() loading = true;
  @State() error = '';
  @State() status = '';
  @State() busyId = '';

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'reference', header: 'Referencia' },
    { key: 'staff_name', header: 'Staff' },
    { key: 'period_end', header: 'Fin periodo' },
    { key: 'transaction_count', header: 'Nº trans.', align: 'right' },
    { key: 'gross_amount', header: 'Bruto', align: 'right', format: (r) => Number(r.gross_amount).toFixed(2) },
    { key: 'net_amount', header: 'Neto', align: 'right', format: (r) => Number(r.net_amount).toFixed(2) },
    { key: 'status', header: 'Estado' },
  ];

  private actions: DataTableAction[] = [
    { id: 'approve', label: 'Aprobar', color: 'primary' },
    { id: 'process', label: 'Procesar', color: 'success' },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('commissions.payout.approved', () => this.refresh());
      const off2 = erplora().on('commissions.payout.completed', () => this.refresh());
      const off3 = erplora().on('commissions.payout.created', () => this.refresh());
      this.unsub = () => {
        off1();
        off2();
        off3();
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
      const rows = await erplora().query<CommissionPayout[]>('commissions.payouts.list', {
        status: this.status,
        staff_id: '',
        limit: 100,
      });
      this.rows = rows ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando lotes';
    } finally {
      this.loading = false;
    }
  }

  private async handleAction(ev: CustomEvent<{ actionId: string; row: Record<string, unknown> }>) {
    const row = ev.detail.row as unknown as CommissionPayout;
    this.busyId = row.id;
    this.error = '';
    try {
      if (ev.detail.actionId === 'approve') {
        if (row.status !== 'pending') throw new Error('Solo lotes pendientes se pueden aprobar.');
        await erplora().command('commissions.payouts.approve', { payout_id: row.id });
      } else if (ev.detail.actionId === 'process') {
        if (row.status !== 'approved') throw new Error('Solo lotes aprobados se pueden procesar.');
        await erplora().command('commissions.payouts.process', {
          payout_id: row.id,
          payment_method: '',
          payment_reference: '',
        });
      }
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo completar la acción';
    } finally {
      this.busyId = '';
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Lotes de pago</h2>
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
            <ion-select-option value="draft">Borrador</ion-select-option>
            <ion-select-option value="pending">Pendiente</ion-select-option>
            <ion-select-option value="approved">Aprobado</ion-select-option>
            <ion-select-option value="completed">Completado</ion-select-option>
            <ion-select-option value="cancelled">Cancelado</ion-select-option>
          </ion-select>
        </div>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.rows as unknown as Record<string, unknown>[]}
          searchKeys={['reference', 'staff_name']}
          searchPlaceholder="Buscar referencia o staff…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin lotes de pago.'}
          actions={this.actions}
          onRowAction={(e: CustomEvent<{ actionId: string; row: Record<string, unknown> }>) => this.handleAction(e)}
        />
      </div>
    );
  }
}
