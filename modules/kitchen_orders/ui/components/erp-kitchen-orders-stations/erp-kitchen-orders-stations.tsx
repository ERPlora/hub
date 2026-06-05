import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild lo
// empaquete dentro del bundle del módulo. El shell provee los `ion-*`. (4 niveles, SIEMPRE.)
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn, DataTableAction } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `kitchen_orders` (Stencil): gestión de estaciones de producción.
// Lista las estaciones con su recuento de líneas pendientes + alta rápida + borrado.
// NO toca la BD: todo va por el SDK (erplora.query/command/on). Las guardas de borrado
// (sin enrutados ni líneas en curso) las valida el handler WASM (ver WASM-TODO.md).

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface Station {
  id: string;
  name: string;
  color: string;
  icon: string;
  printer_name: string;
  is_active: number;
  pending_count?: number;
}

interface PendingCount {
  station_id: string;
  pending_count: number;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-kitchen-orders-stations',
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
export class ErpKitchenOrdersStations {
  @State() stations: Station[] = [];
  @State() loading = true;
  @State() error = '';
  @State() newName = '';
  @State() newPrinter = '';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'name', header: 'Estación' },
    { key: 'printer_name', header: 'Impresora', format: (r) => (r.printer_name as string) || '—' },
    { key: 'pending_count', header: 'En curso', align: 'right', format: (r) => String(r.pending_count ?? 0) },
    { key: 'is_active', header: 'Activa', format: (r) => (Number(r.is_active) ? 'Sí' : 'No') },
  ];

  private rowActions: DataTableAction[] = [{ id: 'delete', label: 'Eliminar', color: 'danger' }];

  async componentWillLoad() {
    await this.refresh();
    try {
      const offs = [
        erplora().on('kitchen_orders.station.created', () => this.refresh()),
        erplora().on('kitchen_orders.station.updated', () => this.refresh()),
        erplora().on('kitchen_orders.station.deleted', () => this.refresh()),
        erplora().on('kitchen_orders.routing.changed', () => this.refresh()),
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
      const [stations, pending] = await Promise.all([
        erplora().query<Station[]>('kitchen_orders.stations.list', { is_active: '' }),
        erplora().query<PendingCount[]>('kitchen_orders.stations.pending_counts'),
      ]);
      const counts = new Map((pending ?? []).map((p) => [p.station_id, p.pending_count]));
      this.stations = (stations ?? []).map((s) => ({ ...s, pending_count: counts.get(s.id) ?? 0 }));
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando estaciones';
    } finally {
      this.loading = false;
    }
  }

  private async createStation(ev: Event) {
    ev.preventDefault();
    if (!this.newName.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('kitchen_orders.stations.create', {
        name: this.newName.trim(),
        printer_name: this.newPrinter.trim(),
      });
      this.newName = '';
      this.newPrinter = '';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear la estación';
    } finally {
      this.saving = false;
    }
  }

  private async onRowAction(ev: CustomEvent<{ actionId: string; row: Record<string, unknown> }>) {
    if (ev.detail.actionId !== 'delete') return;
    this.error = '';
    try {
      await erplora().command('kitchen_orders.stations.delete', {
        station_id: (ev.detail.row as unknown as Station).id,
      });
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo eliminar la estación';
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Estaciones de producción</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createStation(e)}>
          <ion-input
            placeholder="Nombre (Plancha)"
            value={this.newName}
            onIonInput={(e: any) => (this.newName = e.target.value)}
          />
          <ion-input
            placeholder="Impresora (opcional)"
            value={this.newPrinter}
            onIonInput={(e: any) => (this.newPrinter = e.target.value)}
          />
          <ion-button type="submit" size="small" disabled={this.saving || !this.newName}>
            {this.saving ? 'Guardando…' : 'Añadir'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.stations as unknown as Record<string, unknown>[]}
          searchKeys={['name', 'printer_name']}
          searchPlaceholder="Buscar estación…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin estaciones.'}
          actions={this.rowActions}
          onRowAction={(e: CustomEvent<{ actionId: string; row: Record<string, unknown> }>) => this.onRowAction(e)}
        />
      </div>
    );
  }
}
