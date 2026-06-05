import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `glovo` (Stencil). Vista de pedidos entrantes de Glovo:
// listado filtrable por tienda/estado + transición de estado del pedido. Parte de
// `ui.entry` (modules/glovo/dist/glovo.esm.js).
//
// El componente NO toca la BD: llama al SDK (erplora.query/command/on). La
// importación idempotente de pedidos y el contador atómico viven en Rust/WASM.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface GlovoOrder {
  id: string;
  store_id: string;
  order_code: string;
  order_number: string;
  customer_name: string;
  total_amount: string;
  currency: string;
  status: string;
  created_at: string | null;
}

interface GlovoStore {
  id: string;
  name: string;
}

const ORDER_STATUSES = ['new', 'accepted', 'preparing', 'ready', 'delivered', 'cancelled'];

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-glovo-orders',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .filters { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; }
    .filters ion-select { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:9rem; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpGlovoOrders {
  @State() orders: GlovoOrder[] = [];
  @State() stores: GlovoStore[] = [];
  @State() loading = true;
  @State() error = '';
  @State() filterStore = '';
  @State() filterStatus = '';

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'order_number', header: 'Nº' },
    { key: 'order_code', header: 'Código Glovo' },
    { key: 'customer_name', header: 'Cliente' },
    { key: 'store_id', header: 'Tienda', format: (r) => this.storeName(r.store_id as string) },
    {
      key: 'total_amount',
      header: 'Total',
      align: 'right',
      format: (r) => `${Number(r.total_amount).toFixed(2)} ${r.currency ?? ''}`,
    },
    { key: 'status', header: 'Estado' },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('glovo.order.imported', () => this.refresh());
      const off2 = erplora().on('glovo.order.status_changed', () => this.refresh());
      this.unsub = () => {
        off1();
        off2();
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
      const [orders, stores] = await Promise.all([
        erplora().query<GlovoOrder[]>('glovo.orders.list', {
          store_id: this.filterStore,
          status: this.filterStatus,
          limit: 100,
        }),
        erplora().query<GlovoStore[]>('glovo.stores.list', { active_only: '' }),
      ]);
      this.orders = orders ?? [];
      this.stores = stores ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando pedidos Glovo';
    } finally {
      this.loading = false;
    }
  }

  private async advance(order: GlovoOrder, newStatus: string) {
    this.error = '';
    try {
      await erplora().command('glovo.orders.update_status', {
        order_id: order.id,
        new_status: newStatus,
      });
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo cambiar el estado';
    }
  }

  private storeName(id: string): string {
    return this.stores.find((s) => s.id === id)?.name ?? '—';
  }

  render() {
    return (
      <div>
        <header>
          <h2>Pedidos Glovo</h2>
        </header>

        <div class="filters">
          <ion-select
            placeholder="Todas las tiendas"
            value={this.filterStore}
            onIonChange={(e: any) => {
              this.filterStore = e.target.value;
              this.refresh();
            }}
          >
            <ion-select-option value="">Todas las tiendas</ion-select-option>
            {this.stores.map((s) => (
              <ion-select-option value={s.id} key={s.id}>
                {s.name}
              </ion-select-option>
            ))}
          </ion-select>
          <ion-select
            placeholder="Todos los estados"
            value={this.filterStatus}
            onIonChange={(e: any) => {
              this.filterStatus = e.target.value;
              this.refresh();
            }}
          >
            <ion-select-option value="">Todos los estados</ion-select-option>
            {ORDER_STATUSES.map((st) => (
              <ion-select-option value={st} key={st}>
                {st}
              </ion-select-option>
            ))}
          </ion-select>
        </div>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.orders as unknown as Record<string, unknown>[]}
          searchKeys={['order_number', 'order_code', 'customer_name']}
          searchPlaceholder="Buscar pedido…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin pedidos Glovo.'}
          actions={[
            { id: 'accepted', label: 'Aceptar' },
            { id: 'preparing', label: 'En preparación' },
            { id: 'ready', label: 'Listo' },
            { id: 'delivered', label: 'Entregado' },
          ]}
          onRowAction={(e: CustomEvent<{ actionId: string; row: Record<string, unknown> }>) =>
            this.advance(e.detail.row as unknown as GlovoOrder, e.detail.actionId)
          }
        />
      </div>
    );
  }
}
