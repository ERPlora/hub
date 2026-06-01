import { Component, State, h } from '@stencil/core';

// WC del módulo `sales` (Stencil). Mini-app: historial de ventas + métricas (ticket
// medio, total). El TPV completo (grid de productos, carrito, pago) es una vista mayor
// que se añadirá; esta es la vista "list/history". ui.entry cargado en runtime.
// 90% lógica en Rust: llama al SDK (erplora.query); reactivo a sale.completed.

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
    table { width:100%; border-collapse:collapse; font-size:.9rem; }
    th { text-align:left; color:#8b897f; font-weight:600; padding:.5rem .6rem; border-bottom:1px solid #e7e2d6; }
    td { padding:.55rem .6rem; border-bottom:1px solid #f1ede4; }
    .muted { color:#8b897f; font-size:.85rem; }
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
        {this.loading ? (
          <p class="muted">Cargando…</p>
        ) : this.sales.length === 0 ? (
          <p class="muted">Aún no hay ventas.</p>
        ) : (
          <table>
            <thead><tr><th>Número</th><th>Cliente</th><th>Pago</th><th>Estado</th><th>Total</th></tr></thead>
            <tbody>
              {this.sales.map((s) => (
                <tr key={s.id}>
                  <td>{s.sale_number}</td>
                  <td>{s.customer_name || '—'}</td>
                  <td>{s.payment_method_name || '—'}</td>
                  <td><span class={`st st-${s.status}`}>{s.status}</span></td>
                  <td>{Number(s.total || 0).toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    );
  }
}
