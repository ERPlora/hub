import { Component, State, h } from '@stencil/core';

// WC del módulo `customers` (Stencil). Mini-app: lista de clientes + búsqueda +
// alta rápida + lifecycle. ui.entry que el shell carga en runtime.
// 90% de la lógica en Rust: este componente llama al SDK (erplora.query/command);
// no toca BD ni valida permisos para seguridad (Rust revalida).

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}
interface Customer {
  id: string;
  name: string;
  email: string;
  phone: string;
  lifecycle_stage: string;
  total_spent: number;
  total_purchases: number;
}
function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

const STAGE_LABEL: Record<string, string> = {
  lead: 'Lead', prospect: 'Prospecto', first_purchase: '1ª compra', active: 'Activo',
  at_risk: 'En riesgo', dormant: 'Inactivo', churned: 'Perdido', vip: 'VIP',
};

@Component({
  tag: 'erp-customers-list',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ion-text-color,#1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    input { padding:.45rem .6rem; border:1px solid var(--ion-border-color,#e0ddd4); border-radius:8px; font-size:.9rem; }
    button { padding:.45rem .8rem; border:0; border-radius:8px; background:#1496d6; color:#fff; font-size:.85rem; cursor:pointer; }
    button:disabled { opacity:.5; cursor:not-allowed; }
    table { width:100%; border-collapse:collapse; font-size:.9rem; }
    th { text-align:left; color:#8b897f; font-weight:600; padding:.5rem .6rem; border-bottom:1px solid #e7e2d6; }
    td { padding:.55rem .6rem; border-bottom:1px solid #f1ede4; }
    .muted { color:#8b897f; font-size:.85rem; }
    .err { color:#d9480f; }
    .badge { font-size:.72rem; padding:.1rem .5rem; border-radius:999px; background:#e4f1fb; color:#1496d6; }
    .form { display:flex; gap:.4rem; flex-wrap:wrap; margin:.5rem 0 1rem; }
    .form input { flex:1; min-width:7rem; }
  `,
})
export class ErpCustomersList {
  @State() customers: Customer[] = [];
  @State() loading = true;
  @State() error = '';
  @State() search = '';
  @State() newName = '';
  @State() newEmail = '';
  @State() saving = false;
  private unsub?: () => void;

  async componentWillLoad() {
    await this.refresh();
    try {
      const a = erplora().on('customer.created', () => this.refresh());
      const b = erplora().on('customer.updated', () => this.refresh());
      this.unsub = () => { a(); b(); };
    } catch { /* preview sin SDK */ }
  }
  disconnectedCallback() { this.unsub?.(); }

  private async refresh() {
    this.loading = true; this.error = '';
    try {
      this.customers = (await erplora().query<Customer[]>('customers.list')) ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando clientes';
    } finally {
      this.loading = false;
    }
  }

  private async create(ev: Event) {
    ev.preventDefault();
    if (!this.newName.trim()) return;
    this.saving = true;
    try {
      await erplora().command('customers.create', {
        name: this.newName.trim(), email: this.newEmail.trim(), phone: '', tax_id: '',
        address: '', city: '', postal_code: '', country: '', avatar: '', notes: '',
        lifecycle_stage: 'lead', source: 'walk_in', company_name: '',
        birthday: null, anniversary: null, preferred_channel: 'none',
        marketing_consent: 0, consent_date: null,
      });
      this.newName = ''; this.newEmail = '';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear';
    } finally {
      this.saving = false;
    }
  }

  private get filtered(): Customer[] {
    const q = this.search.trim().toLowerCase();
    if (!q) return this.customers;
    return this.customers.filter((c) =>
      c.name.toLowerCase().includes(q) || (c.email || '').toLowerCase().includes(q));
  }

  render() {
    return (
      <div>
        <header>
          <h2>Clientes</h2>
          <input type="search" placeholder="Buscar nombre o email…" value={this.search}
            onInput={(e) => (this.search = (e.target as HTMLInputElement).value)} />
        </header>
        <form class="form" onSubmit={(e) => this.create(e)}>
          <input placeholder="Nombre" value={this.newName}
            onInput={(e) => (this.newName = (e.target as HTMLInputElement).value)} />
          <input placeholder="Email" type="email" value={this.newEmail}
            onInput={(e) => (this.newEmail = (e.target as HTMLInputElement).value)} />
          <button type="submit" disabled={this.saving || !this.newName}>
            {this.saving ? 'Guardando…' : 'Añadir'}
          </button>
        </form>
        {this.error && <p class="err">{this.error}</p>}
        {this.loading ? (
          <p class="muted">Cargando…</p>
        ) : this.filtered.length === 0 ? (
          <p class="muted">Sin clientes.</p>
        ) : (
          <table>
            <thead><tr><th>Nombre</th><th>Email</th><th>Teléfono</th><th>Etapa</th><th>Gastado</th></tr></thead>
            <tbody>
              {this.filtered.map((c) => (
                <tr key={c.id}>
                  <td>{c.name}</td>
                  <td>{c.email}</td>
                  <td>{c.phone}</td>
                  <td><span class="badge">{STAGE_LABEL[c.lifecycle_stage] ?? c.lifecycle_stage}</span></td>
                  <td>{Number(c.total_spent || 0).toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    );
  }
}
