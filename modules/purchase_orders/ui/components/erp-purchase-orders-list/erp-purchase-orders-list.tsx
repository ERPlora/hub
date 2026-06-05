import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn, DataTableAction } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `purchase_orders` (Stencil). Mini-app: lista de
// pedidos de compra + alta rápida (proveedor + una línea) + transiciones de
// estado (confirmar / recibir / cancelar) vía botones de fila.
//
// 90% de la lógica vive en Rust/WASM: este componente NO toca la BD; llama al
// SDK (erplora.query/command/on). El alta usa el handler WASM `create_order`
// (batch de líneas); las transiciones usan comandos SQL transaccionales.
// El listado usa el DataTable compartido + elementos Ionic.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface PurchaseOrder {
  id: string;
  order_number: string;
  status: string;
  supplier_id: string;
  supplier_name: string;
  total_amount: number;
  order_date: string;
  expected_date: string | null;
  created_at: string;
}

interface Supplier {
  id: string;
  name: string;
  tax_id: string;
  email: string;
  phone: string;
  is_active: number;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

const STATUS_LABELS: Record<string, string> = {
  draft: 'Borrador',
  confirmed: 'Confirmado',
  received: 'Recibido',
  cancelled: 'Cancelado',
};

@Component({
  tag: 'erp-purchase-orders-list',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ion-text-color, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .form { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; }
    .form ion-input, .form ion-select { --background:var(--surface-2,#f7f4ec); border:1px solid var(--ion-border-color,#e0ddd4); border-radius:8px; min-width:8rem; }
    .filters { display:flex; gap:.5rem; align-items:center; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpPurchaseOrdersList {
  @State() orders: PurchaseOrder[] = [];
  @State() suppliers: Supplier[] = [];
  @State() loading = true;
  @State() error = '';
  @State() statusFilter = '';
  // Formulario de alta (proveedor + una línea mínima).
  @State() newSupplier = '';
  @State() newProduct = '';
  @State() newQty = '';
  @State() newPrice = '';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'order_number', header: 'Nº pedido' },
    { key: 'supplier_name', header: 'Proveedor' },
    { key: 'status', header: 'Estado', format: (r) => STATUS_LABELS[r.status as string] ?? String(r.status) },
    { key: 'order_date', header: 'Fecha' },
    { key: 'total_amount', header: 'Total', align: 'right', format: (r) => Number(r.total_amount).toFixed(2) },
  ];

  private actions: DataTableAction[] = [
    { id: 'confirm', label: 'Confirmar', icon: 'checkmark-circle-outline', color: 'primary' },
    { id: 'receive', label: 'Recibir', icon: 'cube-outline', color: 'success' },
    { id: 'cancel', label: 'Cancelar', icon: 'close-circle-outline', color: 'danger' },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('purchase_orders.order.created', () => this.refresh());
      const off2 = erplora().on('purchase_orders.order.confirmed', () => this.refresh());
      const off3 = erplora().on('purchase_orders.order.received', () => this.refresh());
      const off4 = erplora().on('purchase_orders.order.cancelled', () => this.refresh());
      const off5 = erplora().on('purchase_orders.supplier.created', () => this.refresh());
      this.unsub = () => {
        off1();
        off2();
        off3();
        off4();
        off5();
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
      const [orders, suppliers] = await Promise.all([
        erplora().query<PurchaseOrder[]>('purchase_orders.orders.list', {
          status: this.statusFilter,
          supplier_id: '',
          limit: 50,
        }),
        erplora().query<Supplier[]>('purchase_orders.suppliers.list', { active_only: 1, search: '' }),
      ]);
      this.orders = orders ?? [];
      this.suppliers = suppliers ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando pedidos';
    } finally {
      this.loading = false;
    }
  }

  private async createOrder(ev: Event) {
    ev.preventDefault();
    if (!this.newSupplier || !this.newProduct.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('purchase_orders.orders.create', {
        supplier_id: this.newSupplier,
        order_date: new Date().toISOString().slice(0, 10),
        expected_date: null,
        notes: '',
        lines: [
          {
            product_name: this.newProduct.trim(),
            quantity: Number(this.newQty) || 1,
            unit_price: Number(this.newPrice) || 0,
          },
        ],
      });
      this.newSupplier = '';
      this.newProduct = '';
      this.newQty = '';
      this.newPrice = '';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear el pedido';
    } finally {
      this.saving = false;
    }
  }

  private async onRowAction(ev: CustomEvent<{ actionId: string; row: Record<string, unknown> }>) {
    const { actionId, row } = ev.detail;
    const orderId = row.id as string;
    this.error = '';
    try {
      if (actionId === 'confirm') {
        await erplora().command('purchase_orders.orders.confirm', { order_id: orderId });
      } else if (actionId === 'receive') {
        await erplora().command('purchase_orders.orders.receive', { order_id: orderId });
      } else if (actionId === 'cancel') {
        await erplora().command('purchase_orders.orders.cancel', { order_id: orderId, reason: '' });
      }
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo actualizar el pedido';
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Pedidos de compra</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createOrder(e)}>
          <ion-select
            placeholder="Proveedor…"
            value={this.newSupplier}
            onIonChange={(e: any) => (this.newSupplier = e.target.value)}
          >
            {this.suppliers.map((s) => (
              <ion-select-option value={s.id} key={s.id}>
                {s.name}
              </ion-select-option>
            ))}
          </ion-select>
          <ion-input
            placeholder="Producto"
            value={this.newProduct}
            onIonInput={(e: any) => (this.newProduct = e.target.value)}
          />
          <ion-input
            type="number"
            step="0.001"
            placeholder="Cantidad"
            value={this.newQty}
            onIonInput={(e: any) => (this.newQty = e.target.value)}
          />
          <ion-input
            type="number"
            step="0.01"
            placeholder="Precio ud."
            value={this.newPrice}
            onIonInput={(e: any) => (this.newPrice = e.target.value)}
          />
          <ion-button type="submit" size="small" disabled={this.saving || !this.newSupplier || !this.newProduct}>
            {this.saving ? 'Guardando…' : 'Nuevo pedido'}
          </ion-button>
        </form>

        <div class="filters">
          <ion-select
            placeholder="Todos los estados"
            value={this.statusFilter}
            onIonChange={(e: any) => {
              this.statusFilter = e.target.value;
              this.refresh();
            }}
          >
            <ion-select-option value="">Todos</ion-select-option>
            <ion-select-option value="draft">Borrador</ion-select-option>
            <ion-select-option value="confirmed">Confirmado</ion-select-option>
            <ion-select-option value="received">Recibido</ion-select-option>
            <ion-select-option value="cancelled">Cancelado</ion-select-option>
          </ion-select>
        </div>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.orders as unknown as Record<string, unknown>[]}
          actions={this.actions}
          searchKeys={['order_number', 'supplier_name']}
          searchPlaceholder="Buscar nº o proveedor…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin pedidos.'}
          onRowAction={(e: CustomEvent<{ actionId: string; row: Record<string, unknown> }>) => this.onRowAction(e)}
        />
      </div>
    );
  }
}
