import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn, DataTableAction } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `leave` (Stencil). Catálogo de tipos de ausencia:
// lista + alta + borrado lógico. NO toca la BD; llama al SDK (erplora.query/command/on).

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface LeaveType {
  id: string;
  name: string;
  days_per_year: number;
  is_paid: number;
  color: string;
  is_active: number;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-leave-types',
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
export class ErpLeaveTypes {
  @State() types: LeaveType[] = [];
  @State() loading = true;
  @State() error = '';
  @State() newName = '';
  @State() newDays = '';
  @State() newColor = '#3b82f6';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'name', header: 'Nombre' },
    { key: 'days_per_year', header: 'Días/año', align: 'right' },
    { key: 'is_paid', header: 'Pagada', format: (r) => (r.is_paid ? 'Sí' : 'No') },
    { key: 'color', header: 'Color' },
  ];

  private rowActions: DataTableAction[] = [
    { id: 'delete', label: 'Eliminar', icon: 'trash-outline', color: 'danger' },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const offs = [
        erplora().on('leave.type.created', () => this.refresh()),
        erplora().on('leave.type.updated', () => this.refresh()),
        erplora().on('leave.type.deleted', () => this.refresh()),
      ];
      this.unsub = () => offs.forEach((o) => o());
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
      const types = await erplora().query<LeaveType[]>('leave.types.list');
      this.types = types ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando tipos';
    } finally {
      this.loading = false;
    }
  }

  private async createType(ev: Event) {
    ev.preventDefault();
    if (!this.newName.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('leave.types.create', {
        name: this.newName.trim(),
        days_per_year: Number(this.newDays) || 0,
        is_paid: true,
        color: this.newColor || '#3b82f6',
      });
      this.newName = '';
      this.newDays = '';
      this.newColor = '#3b82f6';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear el tipo';
    } finally {
      this.saving = false;
    }
  }

  private async onRowAction(ev: CustomEvent<{ actionId: string; row: Record<string, unknown> }>) {
    const { actionId, row } = ev.detail;
    if (actionId !== 'delete') return;
    this.error = '';
    try {
      await erplora().command('leave.types.delete', { leave_type_id: row.id as string });
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo eliminar';
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Tipos de ausencia</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createType(e)}>
          <ion-input
            placeholder="Nombre (Vacaciones)"
            value={this.newName}
            onIonInput={(e: any) => (this.newName = e.target.value)}
          />
          <ion-input
            type="number"
            placeholder="Días/año"
            value={this.newDays}
            onIonInput={(e: any) => (this.newDays = e.target.value)}
          />
          <ion-input
            type="text"
            placeholder="#3b82f6"
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
          rows={this.types as unknown as Record<string, unknown>[]}
          searchKeys={['name']}
          searchPlaceholder="Buscar tipo…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin tipos de ausencia.'}
          actions={this.rowActions}
          onRowAction={(e: CustomEvent<{ actionId: string; row: Record<string, unknown> }>) => this.onRowAction(e)}
        />
      </div>
    );
  }
}
