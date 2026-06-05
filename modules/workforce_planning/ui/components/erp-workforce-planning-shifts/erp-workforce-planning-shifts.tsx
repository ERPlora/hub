import { Component, State, h } from '@stencil/core';
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `workforce_planning` (vista Shifts). Lista plantillas de
// turno y permite alta rápida. NO toca la BD: usa el SDK (erplora.query/command/on).

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface ShiftTemplate {
  id: string;
  name: string;
  location_id: string | null;
  start_time: string;
  end_time: string;
  break_minutes: number;
  min_staff: number;
  max_staff: number;
  role_required: string | null;
}

interface Location {
  id: string;
  name: string;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-workforce-planning-shifts',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .form { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpWorkforcePlanningShifts {
  @State() templates: ShiftTemplate[] = [];
  @State() locations: Location[] = [];
  @State() loading = true;
  @State() error = '';
  @State() saving = false;
  @State() newName = '';
  @State() newStart = '';
  @State() newEnd = '';
  @State() newLocation = '';

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'name', header: 'Turno' },
    { key: 'location_id', header: 'Sede', format: (r) => this.locName(r.location_id as string | null) },
    { key: 'start_time', header: 'Inicio' },
    { key: 'end_time', header: 'Fin' },
    { key: 'break_minutes', header: 'Descanso (min)', align: 'right' },
    { key: 'min_staff', header: 'Mín.', align: 'right' },
    { key: 'role_required', header: 'Rol' },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      this.unsub = erplora().on('workforce_planning.shift_template.created', () => this.refresh());
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
      const [tpls, locs] = await Promise.all([
        erplora().query<ShiftTemplate[]>('workforce_planning.shift_templates.list', { location_id: '' }),
        erplora().query<Location[]>('workforce_planning.locations.list', { active_only: '1' }),
      ]);
      this.templates = tpls ?? [];
      this.locations = locs ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando turnos';
    } finally {
      this.loading = false;
    }
  }

  private async createTemplate(ev: Event) {
    ev.preventDefault();
    if (!this.newName.trim() || !this.newStart || !this.newEnd) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('workforce_planning.shift_templates.create', {
        name: this.newName.trim(),
        location_id: this.newLocation || null,
        start_time: this.newStart,
        end_time: this.newEnd,
      });
      this.newName = '';
      this.newStart = '';
      this.newEnd = '';
      this.newLocation = '';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear el turno';
    } finally {
      this.saving = false;
    }
  }

  private locName(id: string | null): string {
    if (!id) return 'Cualquiera';
    return this.locations.find((l) => l.id === id)?.name ?? '—';
  }

  render() {
    return (
      <div>
        <header>
          <h2>Plantillas de turno</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createTemplate(e)}>
          <ion-input placeholder="Nombre (Mañana)" value={this.newName} onIonInput={(e: any) => (this.newName = e.target.value)} />
          <ion-input type="time" value={this.newStart} onIonInput={(e: any) => (this.newStart = e.target.value)} />
          <ion-input type="time" value={this.newEnd} onIonInput={(e: any) => (this.newEnd = e.target.value)} />
          <ion-select placeholder="Sede…" value={this.newLocation} onIonChange={(e: any) => (this.newLocation = e.target.value)}>
            {this.locations.map((l) => (
              <ion-select-option value={l.id} key={l.id}>
                {l.name}
              </ion-select-option>
            ))}
          </ion-select>
          <ion-button type="submit" size="small" disabled={this.saving || !this.newName || !this.newStart || !this.newEnd}>
            {this.saving ? 'Guardando…' : 'Añadir'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.templates as unknown as Record<string, unknown>[]}
          searchKeys={['name', 'role_required']}
          searchPlaceholder="Buscar turno…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin plantillas de turno.'}
        />
      </div>
    );
  }
}
