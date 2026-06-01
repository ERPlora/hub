import { Component, State, h } from '@stencil/core';

// WC del módulo `invoice` (Stencil). Mini-app: listado de facturas (F1/F2/R1…) con
// estado y tipo. La emisión va por el runtime (handler WASM); este WC es lectura +
// acciones ligeras. 90% lógica en Rust; reactivo a invoice.created/rectified.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}
interface Invoice {
  id: string; invoice_type: string; number: string; issue_date: string;
  customer_name: string; total_amount: number; status: string; source_type: string;
}
function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}
const TYPE_LABEL: Record<string, string> = {
  F1: 'Factura', F2: 'Ticket', F3: 'Factura', R1: 'Rectificativa', R2: 'Rectificativa',
  R3: 'Rectificativa', R4: 'Rectificativa', R5: 'Rectificativa',
};

@Component({
  tag: 'erp-invoice-list',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ion-text-color,#1c1b18); }
    h2 { margin:0 0 .75rem; font-size:1.15rem; }
    table { width:100%; border-collapse:collapse; font-size:.9rem; }
    th { text-align:left; color:#8b897f; font-weight:600; padding:.5rem .6rem; border-bottom:1px solid #e7e2d6; }
    td { padding:.55rem .6rem; border-bottom:1px solid #f1ede4; }
    .muted { color:#8b897f; font-size:.85rem; }
    .err { color:#d9480f; }
    .neg { color:#d9480f; }
    .st { font-size:.72rem; padding:.1rem .5rem; border-radius:999px; }
    .st-issued { background:#e4f1fb; color:#1496d6; }
    .st-paid { background:#e6f7ed; color:#1a7f4b; }
    .st-cancelled { background:#fdeceb; color:#d9480f; }
    .ty { font-size:.72rem; padding:.1rem .5rem; border-radius:6px; background:#f1ede4; color:#6b6862; }
  `,
})
export class ErpInvoiceList {
  @State() invoices: Invoice[] = [];
  @State() loading = true;
  @State() error = '';
  private unsub?: () => void;

  async componentWillLoad() {
    await this.refresh();
    try {
      const a = erplora().on('invoice.created', () => this.refresh());
      const b = erplora().on('invoice.rectified', () => this.refresh());
      this.unsub = () => { a(); b(); };
    } catch { /* preview */ }
  }
  disconnectedCallback() { this.unsub?.(); }

  private async refresh() {
    this.loading = true; this.error = '';
    try { this.invoices = (await erplora().query<Invoice[]>('invoice.list')) ?? []; }
    catch (e) { this.error = e instanceof Error ? e.message : 'Error cargando facturas'; }
    finally { this.loading = false; }
  }

  render() {
    return (
      <div>
        <h2>Facturas</h2>
        {this.error && <p class="err">{this.error}</p>}
        {this.loading ? (
          <p class="muted">Cargando…</p>
        ) : this.invoices.length === 0 ? (
          <p class="muted">Aún no hay facturas.</p>
        ) : (
          <table>
            <thead><tr><th>Número</th><th>Tipo</th><th>Cliente</th><th>Estado</th><th>Total</th></tr></thead>
            <tbody>
              {this.invoices.map((inv) => (
                <tr key={inv.id}>
                  <td>{inv.number}</td>
                  <td><span class="ty">{TYPE_LABEL[inv.invoice_type] ?? inv.invoice_type}</span></td>
                  <td>{inv.customer_name || '—'}</td>
                  <td><span class={`st st-${inv.status}`}>{inv.status}</span></td>
                  <td class={Number(inv.total_amount) < 0 ? 'neg' : ''}>{Number(inv.total_amount || 0).toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    );
  }
}
