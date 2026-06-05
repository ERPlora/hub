import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild lo
// empaquete dentro del bundle del módulo. El shell provee los `ion-*`. (4 niveles, SIEMPRE.)
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn, DataTableAction } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `kitchen_orders` (Stencil): vista de comandas activas.
// Lista las comandas (rates → orders) y permite alta rápida + transiciones de estado.
// NO toca la BD: todo va por el SDK (erplora.query/command/on). La lógica de creación
// y transición vive en el handler WASM (ver WASM-TODO.md); aquí solo se invoca.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface Order {
  id: string;
  order_number: string;
  status: string;
  order_type: string;
  priority: string;
  total: string;
  notes: string;
  created_at: string;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-kitchen-orders-active',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .form { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; }
    .form ion-input, .form ion-select { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:8rem; }
    .err { color:#d9480f; font-weight:600; }
    .actions { display:flex; gap:.35rem; }
  `,
})
export class ErpKitchenOrdersActive {
  @State() orders: Order[] = [];
  @State() loading = true;
  @State() error = '';
  @State() statusFilter = '';
  @State() newType = 'dine_in';
  @State() newNotes = '';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'order_number', header: 'Comanda' },
    { key: 'order_type', header: 'Tipo' },
    { key: 'priority', header: 'Prioridad' },
    { key: 'status', header: 'Estado' },
    { key: 'total', header: 'Total', align: 'right', format: (r) => Number(r.total).toFixed(2) },
  ];

  private rowActions: DataTableAction[] = [
    { id: 'fire', label: 'Lanzar' },
    { id: 'mark_ready', label: 'Lista' },
    { id: 'cancel', label: 'Cancelar', color: 'danger' },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const offs = [
        erplora().on('kitchen_orders.order.created', () => this.refresh()),
        erplora().on('kitchen_orders.order.updated', () => this.refresh()),
        erplora().on('kitchen_orders.order.fired', () => this.refresh()),
        erplora().on('kitchen_orders.order.ready', () => this.refresh()),
        erplora().on('kitchen_orders.order.served', () => this.refresh()),
        erplora().on('kitchen_orders.order.cancelled', () => this.refresh()),
        erplora().on('kitchen_orders.order.deleted', () => this.refresh()),
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
      const orders = await erplora().query<Order[]>('kitchen_orders.orders.list', {
        status: this.statusFilter,
        order_type: '',
        priority: '',
        table_id: '',
        limit: 50,
      });
      this.orders = orders ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando comandas';
    } finally {
      this.loading = false;
    }
  }

  private async createOrder(ev: Event) {
    ev.preventDefault();
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('kitchen_orders.orders.create', {
        order_type: this.newType,
        priority: 'normal',
        notes: this.newNotes.trim(),
        items: [],
      });
      this.newNotes = '';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear la comanda';
    } finally {
      this.saving = false;
    }
  }

  private async onRowAction(ev: CustomEvent<{ actionId: string; row: Record<string, unknown> }>) {
    const { actionId, row } = ev.detail;
    this.error = '';
    try {
      await erplora().command('kitchen_orders.orders.set_status', {
        order_id: (row as unknown as Order).id,
        action_name: actionId,
      });
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo actualizar el estado';
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Comandas</h2>
          <ion-select
            placeholder="Estado…"
            value={this.statusFilter}
            onIonChange={(e: any) => {
              this.statusFilter = e.target.value;
              this.refresh();
            }}
          >
            <ion-select-option value="">Todas</ion-select-option>
            <ion-select-option value="pending">Pendiente</ion-select-option>
            <ion-select-option value="preparing">En preparación</ion-select-option>
            <ion-select-option value="ready">Lista</ion-select-option>
            <ion-select-option value="served">Servida</ion-select-option>
            <ion-select-option value="cancelled">Cancelada</ion-select-option>
          </ion-select>
        </header>

        <form class="form" onSubmit={(e) => this.createOrder(e)}>
          <ion-select
            placeholder="Tipo"
            value={this.newType}
            onIonChange={(e: any) => (this.newType = e.target.value)}
          >
            <ion-select-option value="dine_in">En sala</ion-select-option>
            <ion-select-option value="takeaway">Para llevar</ion-select-option>
            <ion-select-option value="delivery">A domicilio</ion-select-option>
          </ion-select>
          <ion-input
            placeholder="Notas"
            value={this.newNotes}
            onIonInput={(e: any) => (this.newNotes = e.target.value)}
          />
          <ion-button type="submit" size="small" disabled={this.saving}>
            {this.saving ? 'Creando…' : 'Nueva comanda'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.orders as unknown as Record<string, unknown>[]}
          searchKeys={['order_number', 'status', 'order_type']}
          searchPlaceholder="Buscar comanda o estado…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin comandas.'}
          actions={this.rowActions}
          onRowAction={(e: CustomEvent<{ actionId: string; row: Record<string, unknown> }>) => this.onRowAction(e)}
        />
      </div>
    );
  }
}
