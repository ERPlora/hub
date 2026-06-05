import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `kitchen` (Stencil). Vista principal del Kitchen Display System:
// muestra la auditoría reciente de acciones sobre órdenes (recibida, bumped, servida…) y el
// estado de la configuración del display. Es la pieza `ui.entry` que el shell carga en runtime
// (modules/kitchen/dist/kitchen.esm.js).
//
// 90% de la lógica vive en Rust: este componente NO toca la BD; llama al SDK
// (erplora.query/command/on). El cliente se obtiene de `globalThis.erplora` (lo monta el shell
// en el boot, eligiendo HttpWsTransport en cloud o IpcTransport en Tauri). El listado usa el
// DataTable compartido + Ionic.
//
// NOTA: el display "en vivo" de órdenes activas + bump/recall pertenece al módulo `orders`
// (kitchen_orders_*); aquí no se consultan tablas de otro módulo. Esa lógica se porta a WASM /
// queries cruzadas del módulo orders (ver WASM-TODO.md).

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface KitchenLog {
  id: string;
  order_id: string;
  action: string;
  station_id: string | null;
  notes: string;
  created_at: string;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-kitchen-display',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ion-text-color, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    ion-select { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:12rem; }
    .err { color:#d9480f; font-weight:600; }
    .badge { display:inline-block; padding:.1rem .5rem; border-radius:999px; background:#eef6fb; color:#1496d6; font-size:.75rem; font-weight:600; }
  `,
})
export class ErpKitchenDisplay {
  @State() logs: KitchenLog[] = [];
  @State() loading = true;
  @State() error = '';
  @State() actionFilter = '';

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'action', header: 'Acción' },
    { key: 'order_id', header: 'Orden' },
    { key: 'notes', header: 'Notas' },
    { key: 'created_at', header: 'Cuándo' },
  ];

  async componentWillLoad() {
    await this.refresh();
    // Reactividad: cuando llega cualquier evento de ciclo de vida de órdenes del módulo
    // `orders`, el listener declarado en module.json crea un log → recargamos la lista.
    try {
      const offs = [
        erplora().on('kitchen_orders.order_fired', () => this.refresh()),
        erplora().on('kitchen_orders.order_ready', () => this.refresh()),
        erplora().on('kitchen_orders.order_served', () => this.refresh()),
        erplora().on('kitchen_orders.order_cancelled', () => this.refresh()),
      ];
      this.unsub = () => offs.forEach((off) => off());
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
      const rows = await erplora().query<KitchenLog[]>('kitchen.logs.list', {
        order_id: '',
        action: this.actionFilter,
        station_id: '',
      });
      this.logs = rows ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando la auditoría';
    } finally {
      this.loading = false;
    }
  }

  private onFilter(value: string) {
    this.actionFilter = value;
    void this.refresh();
  }

  render() {
    return (
      <div>
        <header>
          <h2>Kitchen Display</h2>
          <ion-select
            placeholder="Todas las acciones"
            value={this.actionFilter}
            onIonChange={(e: any) => this.onFilter(e.target.value)}
          >
            <ion-select-option value="">Todas las acciones</ion-select-option>
            <ion-select-option value="received">Recibidas</ion-select-option>
            <ion-select-option value="bumped">Listas (bump)</ion-select-option>
            <ion-select-option value="served">Servidas</ion-select-option>
            <ion-select-option value="recalled">Recuperadas</ion-select-option>
            <ion-select-option value="cancelled">Canceladas</ion-select-option>
          </ion-select>
        </header>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.logs as unknown as Record<string, unknown>[]}
          searchKeys={['action', 'order_id', 'notes']}
          searchPlaceholder="Buscar acción, orden o notas…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin actividad reciente en cocina.'}
        />
      </div>
    );
  }
}
