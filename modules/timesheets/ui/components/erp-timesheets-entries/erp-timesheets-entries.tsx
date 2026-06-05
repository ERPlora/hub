import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `timesheets` (Stencil). Vista "My Time": lista de
// registros de tiempo + alta rápida. Pieza `ui.entry` que el shell carga en
// runtime (modules/timesheets/dist/timesheets.esm.js).
//
// La lógica de negocio (validar fecha futura, capturar tarifa) vive en el handler
// WASM (command timesheets.entries.create). Este componente NO toca la BD: llama
// al SDK (erplora.query/command/on). El listado usa el DataTable compartido + Ionic.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface TimeEntry {
  id: string;
  employee_id: string;
  employee_name: string;
  date: string;
  duration_minutes: number;
  description: string;
  status: string;
  billable: number;
  project_name: string;
  client_name: string;
  rate_amount: string | null;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-timesheets-entries',
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
export class ErpTimesheetsEntries {
  @State() entries: TimeEntry[] = [];
  @State() loading = true;
  @State() error = '';
  @State() statusFilter = '';
  @State() newEmployeeId = '';
  @State() newEmployeeName = '';
  @State() newDate = '';
  @State() newMinutes = '';
  @State() newDescription = '';
  @State() newProject = '';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'date', header: 'Fecha' },
    { key: 'employee_name', header: 'Empleado' },
    { key: 'project_name', header: 'Proyecto' },
    { key: 'duration_minutes', header: 'Horas', align: 'right', format: (r) => (Number(r.duration_minutes) / 60).toFixed(2) },
    { key: 'billable', header: 'Facturable', format: (r) => (Number(r.billable) ? 'Sí' : 'No') },
    { key: 'status', header: 'Estado' },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('timesheets.entry.created', () => this.refresh());
      const off2 = erplora().on('timesheets.entry.updated', () => this.refresh());
      const off3 = erplora().on('timesheets.entry.deleted', () => this.refresh());
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
      const rows = await erplora().query<TimeEntry[]>('timesheets.entries.list', {
        employee_id: '',
        status: this.statusFilter,
        date_from: '',
        date_to: '',
        project_name: '',
        billable: -1,
        limit: 50,
      });
      this.entries = rows ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando registros de tiempo';
    } finally {
      this.loading = false;
    }
  }

  private async createEntry(ev: Event) {
    ev.preventDefault();
    if (!this.newEmployeeId.trim() || !this.newEmployeeName.trim() || !this.newDate || !this.newMinutes) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('timesheets.entries.create', {
        employee_id: this.newEmployeeId.trim(),
        employee_name: this.newEmployeeName.trim(),
        date: this.newDate,
        duration_minutes: Number(this.newMinutes) || 0,
        description: this.newDescription.trim(),
        project_name: this.newProject.trim(),
        client_name: '',
        billable: true,
        hourly_rate_id: '',
      });
      this.newEmployeeId = '';
      this.newEmployeeName = '';
      this.newDate = '';
      this.newMinutes = '';
      this.newDescription = '';
      this.newProject = '';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear el registro';
    } finally {
      this.saving = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Mis registros de tiempo</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createEntry(e)}>
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
          <ion-input
            type="date"
            value={this.newDate}
            onIonInput={(e: any) => (this.newDate = e.target.value)}
          />
          <ion-input
            type="number"
            min="1"
            placeholder="Minutos"
            value={this.newMinutes}
            onIonInput={(e: any) => (this.newMinutes = e.target.value)}
          />
          <ion-input
            placeholder="Proyecto"
            value={this.newProject}
            onIonInput={(e: any) => (this.newProject = e.target.value)}
          />
          <ion-input
            placeholder="Descripción"
            value={this.newDescription}
            onIonInput={(e: any) => (this.newDescription = e.target.value)}
          />
          <ion-button
            type="submit"
            size="small"
            disabled={this.saving || !this.newEmployeeId || !this.newEmployeeName || !this.newDate || !this.newMinutes}
          >
            {this.saving ? 'Guardando…' : 'Añadir'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.entries as unknown as Record<string, unknown>[]}
          searchKeys={['employee_name', 'project_name', 'date']}
          searchPlaceholder="Buscar empleado, proyecto o fecha…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin registros de tiempo.'}
        />
      </div>
    );
  }
}
