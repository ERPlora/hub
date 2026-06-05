import { Component, State, h } from '@stencil/core';
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `workforce_planning` (vista Planning). Lista las asignaciones
// de turno de la semana y permite crear una asignación. La creación va al command
// `workforce_planning.assignments.create` (handler WASM: detección de conflictos —
// doble reserva / horas extra / descanso — antes de insertar). NO toca la BD.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface Assignment {
  id: string;
  employee_id: string;
  employee_name: string;
  location_id: string;
  date: string;
  start_time: string;
  end_time: string;
  status: string;
}

interface Location {
  id: string;
  name: string;
}

interface CreateResult {
  id?: string;
  created?: boolean;
  error?: string;
  blocking_conflicts?: { type: string; message: string }[];
  hint?: string;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-workforce-planning-planning',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .form { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; }
    .err { color:#d9480f; font-weight:600; }
    .warn { color:#b45309; font-weight:600; }
  `,
})
export class ErpWorkforcePlanningPlanning {
  @State() assignments: Assignment[] = [];
  @State() locations: Location[] = [];
  @State() loading = true;
  @State() error = '';
  @State() warning = '';
  @State() saving = false;
  @State() newEmpId = '';
  @State() newEmpName = '';
  @State() newLocation = '';
  @State() newDate = '';
  @State() newStart = '';
  @State() newEnd = '';

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'date', header: 'Fecha' },
    { key: 'employee_name', header: 'Empleado' },
    { key: 'location_id', header: 'Sede', format: (r) => this.locName(r.location_id as string) },
    { key: 'start_time', header: 'Inicio' },
    { key: 'end_time', header: 'Fin' },
    { key: 'status', header: 'Estado' },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      this.unsub = erplora().on('workforce_planning.assignment.created', () => this.refresh());
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
      const [rows, locs] = await Promise.all([
        erplora().query<Assignment[]>('workforce_planning.assignments.list', {
          date_from: '',
          date_to: '',
          location_id: '',
          employee_id: '',
        }),
        erplora().query<Location[]>('workforce_planning.locations.list', { active_only: '1' }),
      ]);
      this.assignments = rows ?? [];
      this.locations = locs ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando planificación';
    } finally {
      this.loading = false;
    }
  }

  private async createAssignment(ev: Event, force = false) {
    ev.preventDefault();
    if (!this.newEmpId.trim() || !this.newEmpName.trim() || !this.newLocation || !this.newDate || !this.newStart || !this.newEnd) {
      return;
    }
    this.saving = true;
    this.error = '';
    this.warning = '';
    try {
      const res = await erplora().command<CreateResult>('workforce_planning.assignments.create', {
        employee_id: this.newEmpId.trim(),
        employee_name: this.newEmpName.trim(),
        location_id: this.newLocation,
        date: this.newDate,
        start_time: this.newStart,
        end_time: this.newEnd,
        force,
      });
      if (res?.error && res.blocking_conflicts?.length) {
        // Conflictos bloqueantes: el handler WASM los detectó y rechazó (sin force).
        this.warning = res.blocking_conflicts.map((c) => `${c.type}: ${c.message}`).join(' · ') + ' (pulsa "Forzar" para sobrescribir)';
        return;
      }
      if (res?.error) {
        this.error = res.error;
        return;
      }
      this.newEmpId = '';
      this.newEmpName = '';
      this.newDate = '';
      this.newStart = '';
      this.newEnd = '';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear la asignación';
    } finally {
      this.saving = false;
    }
  }

  private locName(id: string): string {
    return this.locations.find((l) => l.id === id)?.name ?? '—';
  }

  render() {
    return (
      <div>
        <header>
          <h2>Planificación de turnos</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createAssignment(e, false)}>
          <ion-input placeholder="ID empleado" value={this.newEmpId} onIonInput={(e: any) => (this.newEmpId = e.target.value)} />
          <ion-input placeholder="Nombre empleado" value={this.newEmpName} onIonInput={(e: any) => (this.newEmpName = e.target.value)} />
          <ion-select placeholder="Sede…" value={this.newLocation} onIonChange={(e: any) => (this.newLocation = e.target.value)}>
            {this.locations.map((l) => (
              <ion-select-option value={l.id} key={l.id}>
                {l.name}
              </ion-select-option>
            ))}
          </ion-select>
          <ion-input type="date" value={this.newDate} onIonInput={(e: any) => (this.newDate = e.target.value)} />
          <ion-input type="time" value={this.newStart} onIonInput={(e: any) => (this.newStart = e.target.value)} />
          <ion-input type="time" value={this.newEnd} onIonInput={(e: any) => (this.newEnd = e.target.value)} />
          <ion-button type="submit" size="small" disabled={this.saving}>
            {this.saving ? 'Guardando…' : 'Asignar'}
          </ion-button>
          {this.warning && (
            <ion-button type="button" size="small" color="warning" disabled={this.saving} onClick={(e: Event) => this.createAssignment(e, true)}>
              Forzar
            </ion-button>
          )}
        </form>

        {this.warning && <p class="warn">{this.warning}</p>}
        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.assignments as unknown as Record<string, unknown>[]}
          searchKeys={['employee_name', 'status']}
          searchPlaceholder="Buscar empleado…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin asignaciones.'}
        />
      </div>
    );
  }
}
