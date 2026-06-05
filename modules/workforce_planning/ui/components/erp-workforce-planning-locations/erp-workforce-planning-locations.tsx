import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `workforce_planning` (vista Locations). Lista las sedes
// y permite alta rápida. NO toca la BD: llama al SDK (erplora.query/command/on).

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface Location {
  id: string;
  name: string;
  address: string | null;
  phone: string | null;
  email: string | null;
  timezone: string;
  color: string;
  is_active: number;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-workforce-planning-locations',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .form { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpWorkforcePlanningLocations {
  @State() locations: Location[] = [];
  @State() loading = true;
  @State() error = '';
  @State() saving = false;
  @State() newName = '';
  @State() newPhone = '';
  @State() newEmail = '';

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'name', header: 'Sede' },
    { key: 'address', header: 'Dirección' },
    { key: 'phone', header: 'Teléfono' },
    { key: 'email', header: 'Email' },
    { key: 'timezone', header: 'Zona horaria' },
    { key: 'is_active', header: 'Activa', align: 'right', format: (r) => (r.is_active ? 'Sí' : 'No') },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      this.unsub = erplora().on('workforce_planning.location.created', () => this.refresh());
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
      const rows = await erplora().query<Location[]>('workforce_planning.locations.list', { active_only: '' });
      this.locations = rows ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando sedes';
    } finally {
      this.loading = false;
    }
  }

  private async createLocation(ev: Event) {
    ev.preventDefault();
    if (!this.newName.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('workforce_planning.locations.create', {
        name: this.newName.trim(),
        phone: this.newPhone.trim() || null,
        email: this.newEmail.trim() || null,
      });
      this.newName = '';
      this.newPhone = '';
      this.newEmail = '';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear la sede';
    } finally {
      this.saving = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Sedes</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createLocation(e)}>
          <ion-input placeholder="Nombre de la sede" value={this.newName} onIonInput={(e: any) => (this.newName = e.target.value)} />
          <ion-input placeholder="Teléfono" value={this.newPhone} onIonInput={(e: any) => (this.newPhone = e.target.value)} />
          <ion-input placeholder="Email" value={this.newEmail} onIonInput={(e: any) => (this.newEmail = e.target.value)} />
          <ion-button type="submit" size="small" disabled={this.saving || !this.newName}>
            {this.saving ? 'Guardando…' : 'Añadir'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.locations as unknown as Record<string, unknown>[]}
          searchKeys={['name', 'address', 'email']}
          searchPlaceholder="Buscar sede…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin sedes.'}
        />
      </div>
    );
  }
}
