import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild lo
// empaquete dentro del bundle del módulo. El shell provee los `ion-*` (4 niveles).
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `delivery` (Stencil): listado de pedidos de reparto/recogida
// + alta rápida. Es una de las piezas `ui.entry` (modules/delivery/dist/delivery.esm.js).
//
// La lógica vive en Rust/WASM: este componente NO toca la BD. Llama al SDK
// (erplora.query/command/on). El alta de pedido dispara el handler WASM `create_order`
// (genera número atómico, calcula totales, valida zona/fee). El listado usa el DataTable.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface DeliveryOrder {
  id: string;
  number: string;
  order_type: string;
  customer_name: string;
  customer_phone: string;
  status: string;
  total: string;
  paid: number;
}

const STATUS_LABELS: Record<string, string> = {
  pending: 'Pendiente',
  preparing: 'Preparando',
  ready: 'Listo',
  in_transit: 'En camino',
  delivered: 'Entregado',
  picked_up: 'Recogido',
  cancelled: 'Cancelado',
};

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-delivery-orders',
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
export class ErpDeliveryOrders {
  @State() orders: DeliveryOrder[] = [];
  @State() loading = true;
  @State() error = '';
  @State() saving = false;
  @State() newName = '';
  @State() newPhone = '';
  @State() newType = 'delivery';
  @State() newAddress = '';

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'number', header: 'Nº' },
    { key: 'order_type', header: 'Tipo', format: (r) => (r.order_type === 'takeaway' ? 'Recogida' : 'Reparto') },
    { key: 'customer_name', header: 'Cliente' },
    { key: 'customer_phone', header: 'Teléfono' },
    { key: 'status', header: 'Estado', format: (r) => STATUS_LABELS[r.status as string] ?? (r.status as string) },
    { key: 'total', header: 'Total', align: 'right', format: (r) => Number(r.total).toFixed(2) },
    { key: 'paid', header: 'Pagado', format: (r) => (r.paid ? 'Sí' : 'No') },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('delivery.order.created', () => this.refresh());
      const off2 = erplora().on('delivery.order.updated', () => this.refresh());
      const off3 = erplora().on('delivery.order.deleted', () => this.refresh());
      this.unsub = () => {
        off1();
        off2();
        off3();
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
      const orders = await erplora().query<DeliveryOrder[]>('delivery.orders.list', {
        status: '',
        order_type: '',
        search: '',
        limit: 50,
      });
      this.orders = orders ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando pedidos';
    } finally {
      this.loading = false;
    }
  }

  private async createOrder(ev: Event) {
    ev.preventDefault();
    if (!this.newName.trim() || !this.newPhone.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('delivery.orders.create', {
        customer_name: this.newName.trim(),
        customer_phone: this.newPhone.trim(),
        order_type: this.newType,
        delivery_address: this.newAddress.trim(),
        items: [],
      });
      this.newName = '';
      this.newPhone = '';
      this.newAddress = '';
      this.newType = 'delivery';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear el pedido';
    } finally {
      this.saving = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Pedidos de reparto</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createOrder(e)}>
          <ion-input
            placeholder="Cliente"
            value={this.newName}
            onIonInput={(e: any) => (this.newName = e.target.value)}
          />
          <ion-input
            placeholder="Teléfono"
            value={this.newPhone}
            onIonInput={(e: any) => (this.newPhone = e.target.value)}
          />
          <ion-select
            value={this.newType}
            onIonChange={(e: any) => (this.newType = e.target.value)}
          >
            <ion-select-option value="delivery">Reparto</ion-select-option>
            <ion-select-option value="takeaway">Recogida</ion-select-option>
          </ion-select>
          <ion-input
            placeholder="Dirección (reparto)"
            value={this.newAddress}
            onIonInput={(e: any) => (this.newAddress = e.target.value)}
          />
          <ion-button type="submit" size="small" disabled={this.saving || !this.newName || !this.newPhone}>
            {this.saving ? 'Guardando…' : 'Nuevo pedido'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.orders as unknown as Record<string, unknown>[]}
          searchKeys={['number', 'customer_name', 'customer_phone']}
          searchPlaceholder="Buscar nº, cliente o teléfono…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin pedidos.'}
        />
      </div>
    );
  }
}
