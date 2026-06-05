import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn, DataTableAction } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `attendance` (Stencil). Mini-app: lista de fichajes
// + alta rápida de clock-in y cierre (clock-out). Es la pieza `ui.entry` que el
// shell carga en runtime (modules/attendance/dist/attendance.esm.js).
//
// La lógica (cálculo de horas, validación de fichaje abierto, soft-delete de
// fichaje cerrado) vive en Rust/WASM: este componente NO toca la BD; sólo llama
// al SDK (erplora.query/command/on). El listado usa el DataTable compartido.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface AttendanceRecord {
  id: string;
  employee_id: string;
  employee_name: string;
  clock_in: string;
  clock_out: string | null;
  break_minutes: number;
  total_hours: string;
  status: string;
  notes: string;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-attendance-records',
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
export class ErpAttendanceRecords {
  @State() records: AttendanceRecord[] = [];
  @State() loading = true;
  @State() error = '';
  @State() saving = false;
  @State() newEmployeeId = '';
  @State() newEmployeeName = '';
  @State() newStatus = 'present';

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'employee_name', header: 'Empleado' },
    { key: 'clock_in', header: 'Entrada', format: (r) => this.fmt(r.clock_in as string) },
    {
      key: 'clock_out',
      header: 'Salida',
      format: (r) => (r.clock_out ? this.fmt(r.clock_out as string) : 'Abierto'),
    },
    { key: 'total_hours', header: 'Horas', align: 'right', format: (r) => Number(r.total_hours).toFixed(2) },
    { key: 'status', header: 'Estado' },
  ];

  private actions: DataTableAction[] = [{ id: 'clock_out', label: 'Salida', color: 'primary' }];

  private onRowAction(ev: CustomEvent<{ actionId: string; row: Record<string, unknown> }>) {
    const { actionId, row } = ev.detail;
    if (actionId === 'clock_out' && row.clock_out == null) {
      this.clockOut(row.employee_id as string);
    }
  }

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('attendance.record.clocked_in', () => this.refresh());
      const off2 = erplora().on('attendance.record.clocked_out', () => this.refresh());
      const off3 = erplora().on('attendance.record.updated', () => this.refresh());
      const off4 = erplora().on('attendance.record.deleted', () => this.refresh());
      this.unsub = () => {
        off1();
        off2();
        off3();
        off4();
      };
    } catch {
      /* sin SDK (preview) → sin reactividad en vivo */
    }
  }

  disconnectedCallback() {
    this.unsub?.();
  }

  private fmt(iso: string): string {
    try {
      return new Date(iso).toLocaleString();
    } catch {
      return iso;
    }
  }

  private async refresh() {
    this.loading = true;
    this.error = '';
    try {
      const rows = await erplora().query<AttendanceRecord[]>('attendance.records.list', {
        employee_id: '',
        status: '',
        date_from: '',
        date_to: '',
      });
      this.records = rows ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando fichajes';
    } finally {
      this.loading = false;
    }
  }

  private async clockIn(ev: Event) {
    ev.preventDefault();
    if (!this.newEmployeeId.trim() || !this.newEmployeeName.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('attendance.records.clock_in', {
        employee_id: this.newEmployeeId.trim(),
        employee_name: this.newEmployeeName.trim(),
        status: this.newStatus,
        notes: '',
      });
      this.newEmployeeId = '';
      this.newEmployeeName = '';
      this.newStatus = 'present';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo fichar la entrada';
    } finally {
      this.saving = false;
    }
  }

  private async clockOut(employeeId: string) {
    this.error = '';
    try {
      await erplora().command('attendance.records.clock_out', {
        employee_id: employeeId,
        break_minutes: 0,
        notes: '',
      });
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo fichar la salida';
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Fichajes</h2>
        </header>

        <form class="form" onSubmit={(e) => this.clockIn(e)}>
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
            placeholder="Estado…"
            value={this.newStatus}
            onIonChange={(e: any) => (this.newStatus = e.target.value)}
          >
            <ion-select-option value="present">Presente</ion-select-option>
            <ion-select-option value="late">Tarde</ion-select-option>
            <ion-select-option value="half_day">Media jornada</ion-select-option>
            <ion-select-option value="remote">Remoto</ion-select-option>
          </ion-select>
          <ion-button
            type="submit"
            size="small"
            disabled={this.saving || !this.newEmployeeId || !this.newEmployeeName}
          >
            {this.saving ? 'Guardando…' : 'Fichar entrada'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.records as unknown as Record<string, unknown>[]}
          searchKeys={['employee_name', 'status']}
          searchPlaceholder="Buscar empleado o estado…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin fichajes.'}
          actions={this.actions}
          onRowAction={(e: CustomEvent) => this.onRowAction(e)}
        />
      </div>
    );
  }
}
