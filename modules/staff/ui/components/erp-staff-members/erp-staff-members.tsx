import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `staff`: lista de miembros del staff + alta rápida.
// Es la pieza `ui.entry` que el shell carga en runtime (modules/staff/dist/staff.esm.js).
// 90% de la lógica vive en Rust: este componente NO toca la BD; llama al SDK
// (erplora.query/command/on). El listado usa el DataTable compartido + Ionic.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface StaffMember {
  id: string;
  first_name: string;
  last_name: string;
  full_name: string;
  email: string;
  phone: string;
  role_id: string | null;
  role_name: string | null;
  status: string;
  is_bookable: number;
  hourly_rate: string;
}

interface StaffRole {
  id: string;
  name: string;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-staff-members',
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
export class ErpStaffMembers {
  @State() members: StaffMember[] = [];
  @State() roles: StaffRole[] = [];
  @State() loading = true;
  @State() error = '';
  @State() search = '';
  @State() newFirst = '';
  @State() newLast = '';
  @State() newEmail = '';
  @State() newRole = '';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'full_name', header: 'Nombre' },
    { key: 'role_name', header: 'Rol', format: (r) => (r.role_name as string) || '—' },
    { key: 'email', header: 'Email' },
    { key: 'phone', header: 'Teléfono' },
    { key: 'status', header: 'Estado' },
    { key: 'hourly_rate', header: '€/h', align: 'right', format: (r) => Number(r.hourly_rate).toFixed(2) },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('staff.member.created', () => this.refresh());
      const off2 = erplora().on('staff.member.updated', () => this.refresh());
      const off3 = erplora().on('staff.member.terminated', () => this.refresh());
      const off4 = erplora().on('staff.member.deactivated', () => this.refresh());
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

  private async refresh() {
    this.loading = true;
    this.error = '';
    try {
      const [members, roles] = await Promise.all([
        erplora().query<StaffMember[]>('staff.members.list', {
          status: '',
          role_id: '',
          is_bookable: -1,
          search: this.search,
        }),
        erplora().query<StaffRole[]>('staff.roles.list'),
      ]);
      this.members = members ?? [];
      this.roles = roles ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando staff';
    } finally {
      this.loading = false;
    }
  }

  private async createMember(ev: Event) {
    ev.preventDefault();
    if (!this.newFirst.trim() || !this.newLast.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('staff.members.create', {
        first_name: this.newFirst.trim(),
        last_name: this.newLast.trim(),
        email: this.newEmail.trim(),
        role_id: this.newRole || null,
        is_bookable: 1,
        status: 'active',
      });
      this.newFirst = '';
      this.newLast = '';
      this.newEmail = '';
      this.newRole = '';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear el miembro';
    } finally {
      this.saving = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Staff</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createMember(e)}>
          <ion-input
            placeholder="Nombre"
            value={this.newFirst}
            onIonInput={(e: any) => (this.newFirst = e.target.value)}
          />
          <ion-input
            placeholder="Apellidos"
            value={this.newLast}
            onIonInput={(e: any) => (this.newLast = e.target.value)}
          />
          <ion-input
            type="email"
            placeholder="Email"
            value={this.newEmail}
            onIonInput={(e: any) => (this.newEmail = e.target.value)}
          />
          <ion-select
            placeholder="Rol…"
            value={this.newRole}
            onIonChange={(e: any) => (this.newRole = e.target.value)}
          >
            {this.roles.map((r) => (
              <ion-select-option value={r.id} key={r.id}>
                {r.name}
              </ion-select-option>
            ))}
          </ion-select>
          <ion-button type="submit" size="small" disabled={this.saving || !this.newFirst || !this.newLast}>
            {this.saving ? 'Guardando…' : 'Añadir'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.members as unknown as Record<string, unknown>[]}
          searchKeys={['full_name', 'email', 'phone']}
          searchPlaceholder="Buscar miembro…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin miembros del staff.'}
        />
      </div>
    );
  }
}
