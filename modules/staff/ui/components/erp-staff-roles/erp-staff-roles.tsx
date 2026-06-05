import { Component, State, h } from '@stencil/core';
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `staff`: gestión de roles de staff (listado + alta).
// NO toca la BD: usa el SDK (erplora.query/command/on).

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface StaffRole {
  id: string;
  name: string;
  description: string;
  color: string;
  member_count: number;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-staff-roles',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .form { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; }
    .form ion-input { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:8rem; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpStaffRoles {
  @State() roles: StaffRole[] = [];
  @State() loading = true;
  @State() error = '';
  @State() newName = '';
  @State() newDesc = '';
  @State() newColor = '';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'name', header: 'Rol' },
    { key: 'description', header: 'Descripción' },
    { key: 'member_count', header: 'Miembros', align: 'right' },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      this.unsub = erplora().on('staff.role.created', () => this.refresh());
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
      const roles = await erplora().query<StaffRole[]>('staff.roles.list');
      this.roles = roles ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando roles';
    } finally {
      this.loading = false;
    }
  }

  private async createRole(ev: Event) {
    ev.preventDefault();
    if (!this.newName.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('staff.roles.create', {
        name: this.newName.trim(),
        description: this.newDesc.trim(),
        color: this.newColor.trim(),
        order: 0,
      });
      this.newName = '';
      this.newDesc = '';
      this.newColor = '';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear el rol';
    } finally {
      this.saving = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Roles</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createRole(e)}>
          <ion-input
            placeholder="Nombre del rol"
            value={this.newName}
            onIonInput={(e: any) => (this.newName = e.target.value)}
          />
          <ion-input
            placeholder="Descripción"
            value={this.newDesc}
            onIonInput={(e: any) => (this.newDesc = e.target.value)}
          />
          <ion-input
            placeholder="Color (#RRGGBB)"
            value={this.newColor}
            onIonInput={(e: any) => (this.newColor = e.target.value)}
          />
          <ion-button type="submit" size="small" disabled={this.saving || !this.newName}>
            {this.saving ? 'Guardando…' : 'Añadir'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.roles as unknown as Record<string, unknown>[]}
          searchKeys={['name', 'description']}
          searchPlaceholder="Buscar rol…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin roles definidos.'}
        />
      </div>
    );
  }
}
