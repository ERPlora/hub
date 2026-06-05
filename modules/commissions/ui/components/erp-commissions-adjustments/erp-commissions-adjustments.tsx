import { Component, State, h } from '@stencil/core';
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn, DataTableAction } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `commissions` — vista "Adjustments". Lista los ajustes manuales
// (bonus/correction/deduction/...) y permite alta rápida + borrado lógico.
// NO toca la BD: usa el SDK (erplora.query/command/on).

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface CommissionAdjustment {
  id: string;
  staff_id: string;
  staff_name: string;
  adjustment_type: string;
  amount: string;
  reason: string;
  adjustment_date: string;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

@Component({
  tag: 'erp-commissions-adjustments',
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
export class ErpCommissionsAdjustments {
  @State() rows: CommissionAdjustment[] = [];
  @State() loading = true;
  @State() error = '';
  @State() saving = false;
  @State() busyId = '';
  @State() newStaffId = '';
  @State() newStaffName = '';
  @State() newType = 'correction';
  @State() newAmount = '';
  @State() newReason = '';

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'adjustment_date', header: 'Fecha' },
    { key: 'staff_name', header: 'Staff' },
    { key: 'adjustment_type', header: 'Tipo' },
    { key: 'amount', header: 'Importe', align: 'right', format: (r) => Number(r.amount).toFixed(2) },
    { key: 'reason', header: 'Motivo' },
  ];

  private actions: DataTableAction[] = [{ id: 'delete', label: 'Borrar', color: 'danger' }];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('commissions.adjustment.created', () => this.refresh());
      const off2 = erplora().on('commissions.adjustment.deleted', () => this.refresh());
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
      const rows = await erplora().query<CommissionAdjustment[]>('commissions.adjustments.list', {
        adjustment_type: '',
        staff_id: '',
        limit: 100,
      });
      this.rows = rows ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando ajustes';
    } finally {
      this.loading = false;
    }
  }

  private async createAdjustment(ev: Event) {
    ev.preventDefault();
    if (!this.newStaffId.trim() || !this.newAmount || !this.newReason.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('commissions.adjustments.create', {
        staff_id: this.newStaffId.trim(),
        staff_name: this.newStaffName.trim() || this.newStaffId.trim(),
        adjustment_type: this.newType,
        amount: Number(this.newAmount) || 0,
        reason: this.newReason.trim(),
        payout_id: null,
        adjustment_date: today(),
      });
      this.newStaffId = '';
      this.newStaffName = '';
      this.newAmount = '';
      this.newReason = '';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear el ajuste';
    } finally {
      this.saving = false;
    }
  }

  private async handleAction(ev: CustomEvent<{ actionId: string; row: Record<string, unknown> }>) {
    if (ev.detail.actionId !== 'delete') return;
    const row = ev.detail.row as unknown as CommissionAdjustment;
    this.busyId = row.id;
    this.error = '';
    try {
      await erplora().command('commissions.adjustments.delete', { adjustment_id: row.id });
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo borrar';
    } finally {
      this.busyId = '';
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Ajustes de comisión</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createAdjustment(e)}>
          <ion-input
            placeholder="ID staff"
            value={this.newStaffId}
            onIonInput={(e: any) => (this.newStaffId = e.target.value)}
          />
          <ion-input
            placeholder="Nombre staff"
            value={this.newStaffName}
            onIonInput={(e: any) => (this.newStaffName = e.target.value)}
          />
          <ion-select
            placeholder="Tipo…"
            value={this.newType}
            onIonChange={(e: any) => (this.newType = e.target.value)}
          >
            <ion-select-option value="bonus">Bonus</ion-select-option>
            <ion-select-option value="correction">Corrección</ion-select-option>
            <ion-select-option value="deduction">Deducción</ion-select-option>
            <ion-select-option value="refund_adjustment">Ajuste devolución</ion-select-option>
            <ion-select-option value="other">Otro</ion-select-option>
          </ion-select>
          <ion-input
            type="number"
            step="0.01"
            placeholder="Importe"
            value={this.newAmount}
            onIonInput={(e: any) => (this.newAmount = e.target.value)}
          />
          <ion-input
            placeholder="Motivo"
            value={this.newReason}
            onIonInput={(e: any) => (this.newReason = e.target.value)}
          />
          <ion-button
            type="submit"
            size="small"
            disabled={this.saving || !this.newStaffId || !this.newAmount || !this.newReason}
          >
            {this.saving ? 'Guardando…' : 'Añadir'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.rows as unknown as Record<string, unknown>[]}
          searchKeys={['staff_name', 'reason', 'adjustment_type']}
          searchPlaceholder="Buscar ajuste…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin ajustes.'}
          actions={this.actions}
          onRowAction={(e: CustomEvent<{ actionId: string; row: Record<string, unknown> }>) => this.handleAction(e)}
        />
      </div>
    );
  }
}
