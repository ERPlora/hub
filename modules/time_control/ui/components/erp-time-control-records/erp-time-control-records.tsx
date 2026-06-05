import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `time_control` (Stencil). Mini-app: lista de fichajes
// (clock records) + fichaje rápido (clock in/out). Es una de las piezas `ui.entry`
// que el shell carga en runtime (modules/time_control/dist/time_control.esm.js).
//
// La lógica de negocio (validación de estado, geofence, resumen diario) vive en Rust
// /WASM: este componente NO toca la BD; llama al SDK (erplora.query/command/on).

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface ClockRecord {
  id: string;
  employee_id: string;
  employee_name: string;
  timestamp: string;
  record_type: string;
  method: string;
  workplace_id: string | null;
  is_within_geofence: number | null;
  notes: string;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-time-control-records',
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
export class ErpTimeControlRecords {
  @State() records: ClockRecord[] = [];
  @State() loading = true;
  @State() error = '';
  @State() saving = false;

  // Filtros y formulario de fichaje rápido.
  @State() filterEmployee = '';
  @State() newEmployeeId = '';
  @State() newEmployeeName = '';
  @State() newAction = 'clock_in';

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'timestamp', header: 'Fecha/hora', format: (r) => this.fmtDate(r.timestamp as string) },
    { key: 'employee_name', header: 'Empleado' },
    { key: 'record_type', header: 'Tipo', format: (r) => this.typeLabel(r.record_type as string) },
    { key: 'method', header: 'Método' },
    {
      key: 'is_within_geofence',
      header: 'Geocerca',
      format: (r) =>
        r.is_within_geofence === null || r.is_within_geofence === undefined
          ? '—'
          : r.is_within_geofence
          ? 'Dentro'
          : 'Fuera',
    },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('time_control.clock.recorded', () => this.refresh());
      const off2 = erplora().on('time_control.summary.recalculated', () => this.refresh());
      this.unsub = () => {
        off1();
        off2();
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
      const records = await erplora().query<ClockRecord[]>('time_control.records.list', {
        employee_id: this.filterEmployee.trim(),
        record_type: '',
        date_from: '',
        date_to: '',
        limit: 50,
      });
      this.records = records ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando fichajes';
    } finally {
      this.loading = false;
    }
  }

  private async clock(ev: Event) {
    ev.preventDefault();
    if (!this.newEmployeeId.trim() || !this.newEmployeeName.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('time_control.records.clock', {
        employee_id: this.newEmployeeId.trim(),
        employee_name: this.newEmployeeName.trim(),
        action_type: this.newAction,
        workplace_id: '',
        latitude: null,
        longitude: null,
        notes: '',
        method: 'api',
      });
      this.newEmployeeId = '';
      this.newEmployeeName = '';
      this.newAction = 'clock_in';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo registrar el fichaje';
    } finally {
      this.saving = false;
    }
  }

  private fmtDate(iso: string): string {
    if (!iso) return '—';
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
  }

  private typeLabel(t: string): string {
    return (
      {
        clock_in: 'Entrada',
        clock_out: 'Salida',
        break_start: 'Inicio pausa',
        break_end: 'Fin pausa',
      }[t] ?? t
    );
  }

  render() {
    return (
      <div>
        <header>
          <h2>Fichajes</h2>
        </header>

        <form class="form" onSubmit={(e) => this.clock(e)}>
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
            value={this.newAction}
            onIonChange={(e: any) => (this.newAction = e.target.value)}
          >
            <ion-select-option value="clock_in">Entrada</ion-select-option>
            <ion-select-option value="clock_out">Salida</ion-select-option>
          </ion-select>
          <ion-button
            type="submit"
            size="small"
            disabled={this.saving || !this.newEmployeeId || !this.newEmployeeName}
          >
            {this.saving ? 'Registrando…' : 'Fichar'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.records as unknown as Record<string, unknown>[]}
          searchKeys={['employee_name', 'record_type', 'method']}
          searchPlaceholder="Buscar empleado o tipo…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin fichajes.'}
        />
      </div>
    );
  }
}
