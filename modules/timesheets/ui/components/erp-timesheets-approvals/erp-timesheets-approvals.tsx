import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn, DataTableAction } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `timesheets` (Stencil). Vista "Approvals": lotes de
// aprobación de periodos por empleado. La transición (máquina de estados + sello
// approved_at/approved_by + evento) vive en el handler WASM (command
// timesheets.approvals.approve). NO toca la BD: llama al SDK.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface TimesheetApproval {
  id: string;
  employee_id: string;
  employee_name: string;
  period_start: string;
  period_end: string;
  status: string;
  total_hours: string;
  billable_hours: string;
  notes: string;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-timesheets-approvals',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpTimesheetsApprovals {
  @State() approvals: TimesheetApproval[] = [];
  @State() loading = true;
  @State() error = '';
  @State() statusFilter = 'pending';

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'employee_name', header: 'Empleado' },
    { key: 'period_start', header: 'Desde' },
    { key: 'period_end', header: 'Hasta' },
    { key: 'total_hours', header: 'Horas', align: 'right', format: (r) => Number(r.total_hours).toFixed(2) },
    { key: 'billable_hours', header: 'Facturables', align: 'right', format: (r) => Number(r.billable_hours).toFixed(2) },
    { key: 'status', header: 'Estado' },
  ];

  // El DataTable compartido NO permite onClick por columna: las acciones de fila
  // van por la prop `actions` + el evento `rowAction`.
  private actions: DataTableAction[] = [
    { id: 'approve', label: 'Aprobar', icon: 'checkmark-circle-outline', color: 'primary' },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      this.unsub = erplora().on('timesheets.period_approved', () => this.refresh());
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
      const rows = await erplora().query<TimesheetApproval[]>('timesheets.approvals.list', {
        employee_id: '',
        status: this.statusFilter,
        limit: 50,
      });
      this.approvals = rows ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando aprobaciones';
    } finally {
      this.loading = false;
    }
  }

  private async onRowAction(ev: CustomEvent<{ actionId: string; row: Record<string, unknown> }>) {
    const { actionId, row } = ev.detail;
    if (actionId !== 'approve') return;
    if (String(row.status) !== 'pending') return;
    this.error = '';
    try {
      await erplora().command('timesheets.approvals.approve', { approval_id: String(row.id) });
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo aprobar el periodo';
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Aprobaciones de periodos</h2>
        </header>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.approvals as unknown as Record<string, unknown>[]}
          actions={this.actions}
          searchKeys={['employee_name', 'status']}
          searchPlaceholder="Buscar empleado o estado…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin aprobaciones pendientes.'}
          onRowAction={(e: CustomEvent<{ actionId: string; row: Record<string, unknown> }>) => this.onRowAction(e)}
        />
      </div>
    );
  }
}
