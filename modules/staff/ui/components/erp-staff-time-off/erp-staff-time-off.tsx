import { Component, State, h } from '@stencil/core';
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn, DataTableAction } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `staff`: solicitudes de ausencia (time off).
// Lista + cambio de estado (aprobar/rechazar/cancelar). NO toca la BD: usa el SDK.
// El alta con detección de solapamiento la resuelve el command WASM staff.time_off.create.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface TimeOff {
  id: string;
  staff_id: string;
  staff_name: string;
  leave_type: string;
  start_date: string;
  end_date: string;
  is_full_day: number;
  status: string;
  reason: string;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-staff-time-off',
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
export class ErpStaffTimeOff {
  @State() requests: TimeOff[] = [];
  @State() loading = true;
  @State() error = '';
  @State() statusFilter = '';
  @State() busyId = '';

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'staff_name', header: 'Miembro' },
    { key: 'leave_type', header: 'Tipo' },
    { key: 'start_date', header: 'Desde' },
    { key: 'end_date', header: 'Hasta' },
    { key: 'status', header: 'Estado' },
  ];

  private actions: DataTableAction[] = [
    { id: 'approve', label: 'Aprobar', color: 'primary' },
    { id: 'reject', label: 'Rechazar', color: 'medium' },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('staff.time_off.created', () => this.refresh());
      const off2 = erplora().on('staff.time_off.status_changed', () => this.refresh());
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
      const rows = await erplora().query<TimeOff[]>('staff.time_off.list', {
        staff_id: '',
        status: this.statusFilter,
      });
      this.requests = rows ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando ausencias';
    } finally {
      this.loading = false;
    }
  }

  private async onRowAction(actionId: string, row: Record<string, unknown>) {
    if ((row.status as string) !== 'pending') return;
    const status = actionId === 'approve' ? 'approved' : 'rejected';
    const id = row.id as string;
    this.busyId = id;
    this.error = '';
    try {
      await erplora().command('staff.time_off.set_status', { time_off_id: id, status });
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo cambiar el estado';
    } finally {
      this.busyId = '';
    }
  }

  private async onFilter(value: string) {
    this.statusFilter = value;
    await this.refresh();
  }

  render() {
    return (
      <div>
        <header>
          <h2>Ausencias</h2>
          <ion-select
            placeholder="Estado…"
            value={this.statusFilter}
            onIonChange={(e: any) => this.onFilter(e.target.value)}
          >
            <ion-select-option value="">Todas</ion-select-option>
            <ion-select-option value="pending">Pendientes</ion-select-option>
            <ion-select-option value="approved">Aprobadas</ion-select-option>
            <ion-select-option value="rejected">Rechazadas</ion-select-option>
            <ion-select-option value="cancelled">Canceladas</ion-select-option>
          </ion-select>
        </header>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.requests as unknown as Record<string, unknown>[]}
          actions={this.actions}
          searchKeys={['staff_name', 'leave_type']}
          searchPlaceholder="Buscar miembro…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin solicitudes de ausencia.'}
          onRowAction={(e: CustomEvent<{ actionId: string; row: Record<string, unknown> }>) =>
            this.onRowAction(e.detail.actionId, e.detail.row)
          }
        />
      </div>
    );
  }
}
