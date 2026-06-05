import { Component, State, h } from '@stencil/core';
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `workforce_planning` (vista Coverage). Lista los requisitos
// de cobertura por sede y permite alta rápida. NO toca la BD.
// El cruce con asignaciones reales (huecos) es lógica de cálculo → handler WASM.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface CoverageRequirement {
  id: string;
  location_id: string;
  day_of_week: number | null;
  shift_template_id: string | null;
  min_employees: number;
  role_required: string | null;
  is_active: number;
}

interface Location {
  id: string;
  name: string;
}

const DAYS = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo'];

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-workforce-planning-coverage',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .form { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpWorkforcePlanningCoverage {
  @State() requirements: CoverageRequirement[] = [];
  @State() locations: Location[] = [];
  @State() loading = true;
  @State() error = '';
  @State() saving = false;
  @State() newLocation = '';
  @State() newDay = '';
  @State() newMin = '1';
  @State() newRole = '';

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'location_id', header: 'Sede', format: (r) => this.locName(r.location_id as string) },
    { key: 'day_of_week', header: 'Día', format: (r) => this.dayName(r.day_of_week as number | null) },
    { key: 'min_employees', header: 'Mín. empleados', align: 'right' },
    { key: 'role_required', header: 'Rol' },
    { key: 'is_active', header: 'Activo', align: 'right', format: (r) => (r.is_active ? 'Sí' : 'No') },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      this.unsub = erplora().on('workforce_planning.coverage.created', () => this.refresh());
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
      const [reqs, locs] = await Promise.all([
        erplora().query<CoverageRequirement[]>('workforce_planning.coverage.list', { location_id: '' }),
        erplora().query<Location[]>('workforce_planning.locations.list', { active_only: '1' }),
      ]);
      this.requirements = reqs ?? [];
      this.locations = locs ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando cobertura';
    } finally {
      this.loading = false;
    }
  }

  private async createRequirement(ev: Event) {
    ev.preventDefault();
    if (!this.newLocation) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('workforce_planning.coverage.create', {
        location_id: this.newLocation,
        day_of_week: this.newDay === '' ? null : Number(this.newDay),
        min_employees: Number(this.newMin) || 1,
        role_required: this.newRole.trim() || null,
      });
      this.newDay = '';
      this.newMin = '1';
      this.newRole = '';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear el requisito';
    } finally {
      this.saving = false;
    }
  }

  private locName(id: string): string {
    return this.locations.find((l) => l.id === id)?.name ?? '—';
  }

  private dayName(d: number | null): string {
    return d === null || d === undefined ? 'Cualquiera' : (DAYS[d] ?? String(d));
  }

  render() {
    return (
      <div>
        <header>
          <h2>Requisitos de cobertura</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createRequirement(e)}>
          <ion-select placeholder="Sede…" value={this.newLocation} onIonChange={(e: any) => (this.newLocation = e.target.value)}>
            {this.locations.map((l) => (
              <ion-select-option value={l.id} key={l.id}>
                {l.name}
              </ion-select-option>
            ))}
          </ion-select>
          <ion-select placeholder="Día…" value={this.newDay} onIonChange={(e: any) => (this.newDay = e.target.value)}>
            <ion-select-option value="">Cualquiera</ion-select-option>
            {DAYS.map((d, i) => (
              <ion-select-option value={String(i)} key={i}>
                {d}
              </ion-select-option>
            ))}
          </ion-select>
          <ion-input type="number" min="1" placeholder="Mín." value={this.newMin} onIonInput={(e: any) => (this.newMin = e.target.value)} />
          <ion-input placeholder="Rol (opcional)" value={this.newRole} onIonInput={(e: any) => (this.newRole = e.target.value)} />
          <ion-button type="submit" size="small" disabled={this.saving || !this.newLocation}>
            {this.saving ? 'Guardando…' : 'Añadir'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.requirements as unknown as Record<string, unknown>[]}
          searchKeys={['role_required']}
          searchPlaceholder="Buscar requisito…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin requisitos de cobertura.'}
        />
      </div>
    );
  }
}
