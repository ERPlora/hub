import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`. (4 niveles)
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn, DataTableAction } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `uber_eats` (vista orders). Mini-app: lista de pedidos
// Uber Eats con filtro por estado + cambio de estado por fila vía erplora.command.
//
// El WC NUNCA toca la BD: todo va por el SDK (erplora.query/command/on). El listado usa
// el DataTable compartido + Ionic. Rust valida permiso, hub_id y las guardas de ciclo de vida.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface UEOrder {
  id: string;
  store_id: string;
  uber_order_id: string;
  order_number: string;
  customer_name: string;
  total_amount: string;
  currency: string;
  status: string;
  created_at_uber: string | null;
}

const ORDER_STATUSES = ['created', 'accepted', 'preparing', 'ready', 'delivered', 'cancelled'];

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-uber-eats-orders',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .filters { display:flex; gap:.5rem; align-items:end; margin:.5rem 0 1rem; }
    .filters ion-select { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:10rem; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpUberEatsOrders {
  @State() orders: UEOrder[] = [];
  @State() loading = true;
  @State() error = '';
  @State() statusFilter = '';
  @State() advancing = '';

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'order_number', header: 'Nº' },
    { key: 'customer_name', header: 'Cliente' },
    { key: 'status', header: 'Estado' },
    {
      key: 'total_amount',
      header: 'Total',
      align: 'right',
      format: (r) => `${Number(r.total_amount).toFixed(2)} ${r.currency ?? ''}`,
    },
  ];

  private actions: DataTableAction[] = [{ id: 'advance', label: 'Avanzar', color: 'primary' }];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('uber_eats.order.imported', () => this.refresh());
      const off2 = erplora().on('uber_eats.order.status_changed', () => this.refresh());
      const off3 = erplora().on('uber_eats.order.cancelled', () => this.refresh());
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

  private nextStatus(current: string): string | null {
    const idx = ORDER_STATUSES.indexOf(current);
    if (idx < 0 || current === 'cancelled' || current === 'delivered') return null;
    // 'ready' avanza a 'delivered'; el resto al siguiente del flujo lineal.
    return ORDER_STATUSES[idx + 1] ?? null;
  }

  private async refresh() {
    this.loading = true;
    this.error = '';
    try {
      const orders = await erplora().query<UEOrder[]>('uber_eats.orders.list', {
        store_id: '',
        status: this.statusFilter,
      });
      this.orders = orders ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando pedidos';
    } finally {
      this.loading = false;
    }
  }

  private async onFilterChange(value: string) {
    this.statusFilter = value;
    await this.refresh();
  }

  private async onRowAction(ev: CustomEvent<{ actionId: string; row: Record<string, unknown> }>) {
    if (ev.detail?.actionId === 'advance') {
      await this.advance(ev.detail.row as unknown as UEOrder);
    }
  }

  private async advance(order: UEOrder) {
    const next = this.nextStatus(order.status);
    if (!next) return;
    this.advancing = order.id;
    this.error = '';
    try {
      await erplora().command('uber_eats.orders.update_status', {
        order_id: order.id,
        new_status: next,
      });
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo cambiar el estado';
    } finally {
      this.advancing = '';
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Pedidos Uber Eats</h2>
        </header>

        <div class="filters">
          <ion-select
            placeholder="Todos los estados"
            value={this.statusFilter}
            onIonChange={(e: any) => this.onFilterChange(e.target.value)}
          >
            <ion-select-option value="">Todos</ion-select-option>
            {ORDER_STATUSES.map((s) => (
              <ion-select-option value={s} key={s}>
                {s}
              </ion-select-option>
            ))}
          </ion-select>
        </div>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.orders as unknown as Record<string, unknown>[]}
          searchKeys={['order_number', 'customer_name', 'uber_order_id']}
          searchPlaceholder="Buscar pedido o cliente…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin pedidos.'}
          actions={this.actions}
          onRowAction={(e: CustomEvent) => this.onRowAction(e)}
        />
      </div>
    );
  }
}
