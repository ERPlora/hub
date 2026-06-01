import { Component, State, h } from '@stencil/core';

// WC del módulo `cash_register` (Stencil). Mini-app: sesiones de caja con su estado
// y reconciliación (esperado/contado/diferencia). 90% lógica en Rust; reactivo a
// los eventos de apertura/cierre de sesión.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}
interface Session {
  id: string; session_number: string; status: string;
  opening_balance: number; closing_balance: number | null;
  expected_balance: number | null; difference: number | null;
}
function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-cashregister-dashboard',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ion-text-color,#1c1b18); }
    h2 { margin:0 0 .75rem; font-size:1.15rem; }
    table { width:100%; border-collapse:collapse; font-size:.9rem; }
    th { text-align:left; color:#8b897f; font-weight:600; padding:.5rem .6rem; border-bottom:1px solid #e7e2d6; }
    td { padding:.55rem .6rem; border-bottom:1px solid #f1ede4; }
    .muted { color:#8b897f; font-size:.85rem; }
    .err { color:#d9480f; }
    .st { font-size:.72rem; padding:.1rem .5rem; border-radius:999px; }
    .st-open { background:#e6f7ed; color:#1a7f4b; }
    .st-closed { background:#f1ede4; color:#6b6862; }
    .diff-ok { color:#1a7f4b; }
    .diff-bad { color:#d9480f; font-weight:600; }
  `,
})
export class ErpCashRegisterDashboard {
  @State() sessions: Session[] = [];
  @State() loading = true;
  @State() error = '';
  private unsub?: () => void;

  async componentWillLoad() {
    await this.refresh();
    try {
      const a = erplora().on('cash_register.session_opened', () => this.refresh());
      const b = erplora().on('cash_register.session_closed', () => this.refresh());
      this.unsub = () => { a(); b(); };
    } catch { /* preview */ }
  }
  disconnectedCallback() { this.unsub?.(); }

  private async refresh() {
    this.loading = true; this.error = '';
    try { this.sessions = (await erplora().query<Session[]>('cash_register.sessions.list')) ?? []; }
    catch (e) { this.error = e instanceof Error ? e.message : 'Error cargando sesiones'; }
    finally { this.loading = false; }
  }

  private fmt(n: number | null): string { return n == null ? '—' : Number(n).toFixed(2); }

  render() {
    return (
      <div>
        <h2>Caja</h2>
        {this.error && <p class="err">{this.error}</p>}
        {this.loading ? (
          <p class="muted">Cargando…</p>
        ) : this.sessions.length === 0 ? (
          <p class="muted">Sin sesiones de caja.</p>
        ) : (
          <table>
            <thead><tr><th>Sesión</th><th>Estado</th><th>Apertura</th><th>Esperado</th><th>Contado</th><th>Diferencia</th></tr></thead>
            <tbody>
              {this.sessions.map((s) => (
                <tr key={s.id}>
                  <td>{s.session_number}</td>
                  <td><span class={`st st-${s.status}`}>{s.status}</span></td>
                  <td>{this.fmt(s.opening_balance)}</td>
                  <td>{this.fmt(s.expected_balance)}</td>
                  <td>{this.fmt(s.closing_balance)}</td>
                  <td class={s.difference == null ? '' : Math.abs(Number(s.difference)) < 0.01 ? 'diff-ok' : 'diff-bad'}>
                    {this.fmt(s.difference)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    );
  }
}
