import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `tables` (Stencil). Mini-app: plano de sala —
// lista de mesas con su estado (disponible / ocupada / reservada / bloqueada),
// buscador y alta rápida de mesa. Es la pieza `ui.entry` que el shell carga
// en runtime (modules/tables/dist/tables.esm.js).
//
// La lógica de negocio (abrir/cerrar/transferir sesión, alta masiva, guardas de
// borrado) vive en Rust/WASM: este componente NO toca la BD; llama al SDK
// (erplora.query/command/on). Toda escritura la valida y ejecuta el runtime.
// El cliente se obtiene de `globalThis.erplora` (lo monta el shell en el boot).
// El listado usa el DataTable compartido + Ionic en el formulario de alta.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface Table {
  id: string;
  number: string;
  name: string;
  capacity: number;
  shape: string;
  status: string;
  is_active: number;
  zone: string | null;
  zone_id: string | null;
}

const STATUS_LABELS: Record<string, string> = {
  available: 'Disponible',
  occupied: 'Ocupada',
  reserved: 'Reservada',
  blocked: 'Bloqueada',
};

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-tables-floor-plan',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ion-text-color, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .form { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; }
    .form ion-input { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:8rem; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpTablesFloorPlan {
  @State() tables: Table[] = [];
  @State() loading = true;
  @State() error = '';
  @State() newNumber = '';
  @State() newCapacity = '4';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'number', header: 'Número' },
    { key: 'name', header: 'Nombre', format: (r) => (r.name as string) || '—' },
    { key: 'zone', header: 'Zona', format: (r) => (r.zone as string) || '—' },
    { key: 'capacity', header: 'Aforo', align: 'right', format: (r) => `${r.capacity} pax` },
    { key: 'status', header: 'Estado', format: (r) => STATUS_LABELS[r.status as string] ?? (r.status as string) },
  ];

  async componentWillLoad() {
    await this.refresh();
    // Reactividad: recargamos cuando el runtime emite eventos de dominio.
    try {
      const offs = [
        erplora().on('tables.table.created', () => this.refresh()),
        erplora().on('tables.table.updated', () => this.refresh()),
        erplora().on('tables.table.deleted', () => this.refresh()),
        erplora().on('tables.session.opened', () => this.refresh()),
        erplora().on('tables.session.closed', () => this.refresh()),
        erplora().on('tables.session.transferred', () => this.refresh()),
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
      const rows = await erplora().query<Table[]>('tables.tables.list');
      this.tables = rows ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando mesas';
    } finally {
      this.loading = false;
    }
  }

  private async createTable(ev: Event) {
    ev.preventDefault();
    if (!this.newNumber.trim()) return;
    this.saving = true;
    try {
      await erplora().command('tables.tables.create', {
        number: this.newNumber.trim(),
        name: '',
        capacity: Number(this.newCapacity) || 4,
        zone_id: null,
        shape: 'square',
        position_x: 0,
        position_y: 0,
        width: 10,
        height: 10,
      });
      this.newNumber = '';
      this.newCapacity = '4';
      await this.refresh(); // (además del evento; garantiza refresco inmediato)
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear la mesa';
    } finally {
      this.saving = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Plano de sala</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createTable(e)}>
          <ion-input
            placeholder="Número"
            value={this.newNumber}
            onIonInput={(e: any) => (this.newNumber = e.target.value)}
          />
          <ion-input
            type="number"
            min="1"
            placeholder="Aforo"
            value={this.newCapacity}
            onIonInput={(e: any) => (this.newCapacity = e.target.value)}
          />
          <ion-button type="submit" size="small" disabled={this.saving || !this.newNumber}>
            {this.saving ? 'Guardando…' : 'Añadir mesa'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.tables as unknown as Record<string, unknown>[]}
          searchKeys={['number', 'name', 'zone']}
          searchPlaceholder="Buscar mesa o zona…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin mesas.'}
        />
      </div>
    );
  }
}
