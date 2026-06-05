import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn, DataTableAction } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `leave` (Stencil). Mini-app: lista de solicitudes de
// ausencia con filtro por estado + alta rápida + aprobar/rechazar. Es la pieza
// `ui.entry` que el shell carga en runtime (modules/leave/dist/leave.esm.js).
//
// El grueso de la lógica vive en Rust/WASM: este componente NO toca la BD; llama
// al SDK (erplora.query/command/on). El listado usa el DataTable compartido + Ionic.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface LeaveRequest {
  id: string;
  employee_id: string;
  employee_name: string;
  leave_type_id: string;
  leave_type_name: string;
  start_date: string;
  end_date: string;
  days_count: string;
  status: string;
  reason: string;
}

interface LeaveType {
  id: string;
  name: string;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-leave-requests',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .form { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; }
    .form ion-input, .form ion-select { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:8rem; }
    .err { color:#d9480f; font-weight:600; }
    .actions { display:flex; gap:.35rem; }
  `,
})
export class ErpLeaveRequests {
  @State() requests: LeaveRequest[] = [];
  @State() types: LeaveType[] = [];
  @State() loading = true;
  @State() error = '';
  @State() filterStatus = '';
  @State() newEmployeeId = '';
  @State() newEmployeeName = '';
  @State() newType = '';
  @State() newStart = '';
  @State() newEnd = '';
  @State() newReason = '';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'employee_name', header: 'Empleado' },
    { key: 'leave_type_name', header: 'Tipo' },
    { key: 'start_date', header: 'Desde' },
    { key: 'end_date', header: 'Hasta' },
    { key: 'days_count', header: 'Días', align: 'right' },
    { key: 'status', header: 'Estado' },
  ];

  // Botones de fila (el DataTable emite `rowAction` con {actionId, row}).
  // Se muestran siempre; el guard de estado lo aplica el runtime (solo 'pending'
  // transiciona; en otros estados la command devuelve error sin efecto).
  private rowActions: DataTableAction[] = [
    { id: 'approve', label: 'Aprobar', icon: 'checkmark-outline', color: 'success' },
    { id: 'reject', label: 'Rechazar', icon: 'close-outline', color: 'danger' },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const offs = [
        erplora().on('leave.request.created', () => this.refresh()),
        erplora().on('leave.request_approved', () => this.refresh()),
        erplora().on('leave.request_rejected', () => this.refresh()),
        erplora().on('leave.request.cancelled', () => this.refresh()),
        erplora().on('leave.request.updated', () => this.refresh()),
      ];
      this.unsub = () => offs.forEach((o) => o());
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
      const [requests, types] = await Promise.all([
        erplora().query<LeaveRequest[]>('leave.requests.list', {
          status: this.filterStatus,
          employee_id: '',
          date_from: '',
          date_to: '',
        }),
        erplora().query<LeaveType[]>('leave.types.list'),
      ]);
      this.requests = requests ?? [];
      this.types = types ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando solicitudes';
    } finally {
      this.loading = false;
    }
  }

  private async createRequest(ev: Event) {
    ev.preventDefault();
    if (!this.newEmployeeId.trim() || !this.newEmployeeName.trim() || !this.newType || !this.newStart || !this.newEnd) {
      return;
    }
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('leave.requests.create', {
        employee_id: this.newEmployeeId.trim(),
        employee_name: this.newEmployeeName.trim(),
        leave_type_id: this.newType,
        start_date: this.newStart,
        end_date: this.newEnd,
        is_half_day: false,
        half_day_period: '',
        reason: this.newReason.trim(),
      });
      this.newEmployeeId = '';
      this.newEmployeeName = '';
      this.newType = '';
      this.newStart = '';
      this.newEnd = '';
      this.newReason = '';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear la solicitud';
    } finally {
      this.saving = false;
    }
  }

  private async onRowAction(ev: CustomEvent<{ actionId: string; row: Record<string, unknown> }>) {
    const { actionId, row } = ev.detail;
    const id = row.id as string;
    this.error = '';
    try {
      if (actionId === 'approve') {
        await erplora().command('leave.requests.approve', { request_id: id });
      } else if (actionId === 'reject') {
        await erplora().command('leave.requests.reject', { request_id: id, reason: '' });
      }
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo completar la acción';
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Solicitudes de ausencia</h2>
          <ion-select
            placeholder="Todos"
            value={this.filterStatus}
            onIonChange={(e: any) => {
              this.filterStatus = e.target.value;
              this.refresh();
            }}
          >
            <ion-select-option value="">Todos</ion-select-option>
            <ion-select-option value="pending">Pendientes</ion-select-option>
            <ion-select-option value="approved">Aprobadas</ion-select-option>
            <ion-select-option value="rejected">Rechazadas</ion-select-option>
            <ion-select-option value="cancelled">Canceladas</ion-select-option>
          </ion-select>
        </header>

        <form class="form" onSubmit={(e) => this.createRequest(e)}>
          <ion-input
            placeholder="ID empleado"
            value={this.newEmployeeId}
            onIonInput={(e: any) => (this.newEmployeeId = e.target.value)}
          />
          <ion-input
            placeholder="Nombre empleado"
            value={this.newEmployeeName}
            onIonInput={(e: any) => (this.newEmployeeName = e.target.value)}
          />
          <ion-select
            placeholder="Tipo…"
            value={this.newType}
            onIonChange={(e: any) => (this.newType = e.target.value)}
          >
            {this.types.map((t) => (
              <ion-select-option value={t.id} key={t.id}>
                {t.name}
              </ion-select-option>
            ))}
          </ion-select>
          <ion-input
            type="date"
            value={this.newStart}
            onIonInput={(e: any) => (this.newStart = e.target.value)}
          />
          <ion-input
            type="date"
            value={this.newEnd}
            onIonInput={(e: any) => (this.newEnd = e.target.value)}
          />
          <ion-input
            placeholder="Motivo"
            value={this.newReason}
            onIonInput={(e: any) => (this.newReason = e.target.value)}
          />
          <ion-button
            type="submit"
            size="small"
            disabled={this.saving || !this.newEmployeeId || !this.newEmployeeName || !this.newType || !this.newStart || !this.newEnd}
          >
            {this.saving ? 'Guardando…' : 'Solicitar'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.requests as unknown as Record<string, unknown>[]}
          searchKeys={['employee_name', 'leave_type_name', 'status']}
          searchPlaceholder="Buscar empleado o estado…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin solicitudes.'}
          actions={this.rowActions}
          onRowAction={(e: CustomEvent<{ actionId: string; row: Record<string, unknown> }>) => this.onRowAction(e)}
        />
      </div>
    );
  }
}
