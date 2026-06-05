import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn, DataTableAction } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `orders` (Stencil). Mini-app: pipeline de pedidos
// (multicanal: teléfono/WhatsApp/email/presencial) con filtro por estado y acciones
// de transición (confirmar / completar / cancelar). Es la pieza `ui.entry` que el
// shell carga en runtime (modules/orders/dist/orders.esm.js).
//
// 90% de la lógica vive en Rust/WASM: este componente NO toca la BD; llama al SDK
// (erplora.query/command/on). Un "pedido" es una fila de la tabla PROPIA del módulo
// orders (orders_order); toda escritura la valida y ejecuta el runtime.
// El cliente se obtiene de `globalThis.erplora` (lo monta el shell en el boot).
// El listado usa el DataTable compartido + Ionic.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface Order {
  id: string;
  order_number: string;
  status: string;
  channel: string;
  customer_name: string;
  customer_phone: string;
  total: number;
  priority: string;
  sale_id: string | null;
  created_at: string;
}

const STATUSES = ['', 'draft', 'pending', 'completed', 'voided'];

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-orders-pipeline',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ion-text-color, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; flex-wrap:wrap; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .filter ion-select { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:12rem; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpOrdersPipeline {
  @State() orders: Order[] = [];
  @State() loading = true;
  @State() error = '';
  @State() statusFilter = '';
  @State() busyId = '';

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'order_number', header: 'Nº' },
    { key: 'status', header: 'Estado' },
    { key: 'channel', header: 'Canal' },
    { key: 'customer_name', header: 'Cliente', format: (r) => (r.customer_name as string) || '—' },
    { key: 'total', header: 'Total', align: 'right', format: (r) => Number(r.total).toFixed(2) },
  ];

  // Acciones de fila (botones). El handler `onRowAction` valida la transición
  // según el estado del pedido antes de invocar el comando del runtime.
  private actions: DataTableAction[] = [
    { id: 'confirm', label: 'Confirmar', icon: 'checkmark-circle-outline', color: 'primary' },
    { id: 'complete', label: 'Completar', icon: 'checkmark-done-outline', color: 'success' },
    { id: 'cancel', label: 'Cancelar', icon: 'close-circle-outline', color: 'danger' },
  ];

  async componentWillLoad() {
    await this.refresh();
    // Reactividad: recargamos cuando el dominio anuncia cambios de pedido.
    try {
      const offs = [
        erplora().on('orders.order_created', () => this.refresh()),
        erplora().on('orders.order_confirmed', () => this.refresh()),
        erplora().on('orders.order_completed', () => this.refresh()),
        erplora().on('orders.order_cancelled', () => this.refresh()),
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
      const rows = await erplora().query<Order[]>('orders.orders.list', {
        status: this.statusFilter,
        channel: '',
        search: '',
      });
      this.orders = rows ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando pedidos';
    } finally {
      this.loading = false;
    }
  }

  // Mapeo acción de fila → comando del runtime + estado destino, con la guarda de
  // transición que antes vivía en el render condicional de cada botón.
  // Tier 0 (confirm/cancel): el comando UPDATE de orders_order bindea :order_id +
  // :new_status, así que aquí derivamos new_status del actionId. `complete` es un
  // handler WASM (lógica de cierre) y recibe el payload sin new_status precalculado.
  private commandFor(actionId: string, status: string): { command: string; newStatus: string | null } | null {
    if (actionId === 'confirm') return status === 'draft' ? { command: 'orders.confirm', newStatus: 'pending' } : null;
    if (actionId === 'complete')
      return status === 'draft' || status === 'pending' ? { command: 'orders.complete', newStatus: null } : null;
    if (actionId === 'cancel')
      return status !== 'completed' && status !== 'voided' ? { command: 'orders.cancel', newStatus: 'voided' } : null;
    return null;
  }

  private async onRowAction(ev: CustomEvent<{ actionId: string; row: Record<string, unknown> }>) {
    const o = ev.detail.row as unknown as Order;
    const mapped = this.commandFor(ev.detail.actionId, o.status);
    if (!mapped || this.busyId === o.id) return;
    this.busyId = o.id;
    this.error = '';
    try {
      // La UI envía order_id (referencia a orders_order) + new_status derivado del
      // actionId + reason. El runtime inyecta current_user_id/now. La nota de cambio
      // de estado y la transición compleja las resuelve el handler (ver WASM-TODO.md).
      const payload: Record<string, unknown> = { order_id: o.id, order_number: o.order_number, reason: '' };
      if (mapped.newStatus) payload.new_status = mapped.newStatus;
      await erplora().command(mapped.command, payload);
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo actualizar el pedido';
    } finally {
      this.busyId = '';
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Pedidos</h2>
          <div class="filter">
            <ion-select
              value={this.statusFilter}
              interface="popover"
              onIonChange={(e: any) => {
                this.statusFilter = e.target.value;
                this.refresh();
              }}
            >
              {STATUSES.map((s) => (
                <ion-select-option value={s} key={s || 'all'}>
                  {s === '' ? 'Todos los estados' : s}
                </ion-select-option>
              ))}
            </ion-select>
          </div>
        </header>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.orders as unknown as Record<string, unknown>[]}
          actions={this.actions}
          searchKeys={['order_number', 'customer_name', 'customer_phone']}
          searchPlaceholder="Buscar nº, cliente o teléfono…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin pedidos.'}
          onRowAction={(e: CustomEvent<{ actionId: string; row: Record<string, unknown> }>) => this.onRowAction(e)}
        />
      </div>
    );
  }
}
