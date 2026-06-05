import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// WC del módulo `sales` (Stencil). Mini-app: historial de ventas + métricas (ticket
// medio, total). El TPV completo (grid de productos, carrito, pago) es una vista mayor
// que se añadirá; esta es la vista "list/history". ui.entry cargado en runtime.
// 90% lógica en Rust: llama al SDK (erplora.query); reactivo a sale.completed.
// El listado usa el DataTable compartido + Ionic.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}
interface Sale {
  id: string;
  sale_number: string;
  status: string;
  total: number;
  customer_name: string;
  payment_method_name: string;
  created_at: string;
}
interface Stats { count: number; total_revenue: number; avg_ticket: number; }
function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-sales-list',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ion-text-color,#1c1b18); }
    h2 { margin:0 0 .75rem; font-size:1.15rem; }
    .cards { display:flex; gap:.6rem; margin-bottom:1rem; flex-wrap:wrap; }
    .card { flex:1; min-width:8rem; padding:.7rem .9rem; border:1px solid var(--ion-border-color,#e0ddd4); border-radius:12px; }
    .card .k { color:#8b897f; font-size:.75rem; text-transform:uppercase; }
    .card .v { font-size:1.3rem; font-weight:700; }
    .err { color:#d9480f; }
    .st { font-size:.72rem; padding:.1rem .5rem; border-radius:999px; }
    .st-completed { background:#e6f7ed; color:#1a7f4b; }
    .st-voided { background:#fdeceb; color:#d9480f; }
  `,
})
export class ErpSalesList {
  @State() sales: Sale[] = [];
  @State() stats: Stats = { count: 0, total_revenue: 0, avg_ticket: 0 };
  @State() loading = true;
  @State() error = '';
  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'sale_number', header: 'Número' },
    { key: 'customer_name', header: 'Cliente', format: (r) => (r.customer_name as string) || '—' },
    { key: 'payment_method_name', header: 'Pago', format: (r) => (r.payment_method_name as string) || '—' },
    { key: 'status', header: 'Estado' },
    { key: 'total', header: 'Total', align: 'right', format: (r) => Number(r.total || 0).toFixed(2) },
  ];

  async componentWillLoad() {
    await this.refresh();
    try { this.unsub = erplora().on('sale.completed', () => this.refresh()); }
    catch { /* preview sin SDK */ }
  }
  disconnectedCallback() { this.unsub?.(); }

  private async refresh() {
    this.loading = true; this.error = '';
    try {
      const [sales, statsRows] = await Promise.all([
        erplora().query<Sale[]>('sales.list'),
        erplora().query<Stats[]>('sales.stats'),
      ]);
      this.sales = sales ?? [];
      this.stats = (statsRows && statsRows[0]) || { count: 0, total_revenue: 0, avg_ticket: 0 };
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando ventas';
    } finally {
      this.loading = false;
    }
  }

  render() {
    return (
      <div>
        <h2>Ventas</h2>
        <div class="cards">
          <div class="card"><div class="k">Tickets</div><div class="v">{this.stats.count}</div></div>
          <div class="card"><div class="k">Ingresos</div><div class="v">{Number(this.stats.total_revenue || 0).toFixed(2)}</div></div>
          <div class="card"><div class="k">Ticket medio</div><div class="v">{Number(this.stats.avg_ticket || 0).toFixed(2)}</div></div>
        </div>
        {this.error && <p class="err">{this.error}</p>}
        <data-table
          columns={this.columns}
          rows={this.sales as unknown as Record<string, unknown>[]}
          searchKeys={['sale_number', 'customer_name', 'payment_method_name']}
          searchPlaceholder="Buscar número o cliente…"
          emptyMessage={this.loading ? 'Cargando…' : 'Aún no hay ventas.'}
        />
      </div>
    );
  }
}
