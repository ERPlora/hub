import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// WC del módulo `customers` (Stencil). Mini-app: lista de clientes + búsqueda +
// alta rápida + lifecycle. ui.entry que el shell carga en runtime.
// 90% de la lógica en Rust: este componente llama al SDK (erplora.query/command);
// no toca BD ni valida permisos para seguridad (Rust revalida). El listado usa el
// DataTable compartido + Ionic.

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
    .form { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; }
    .form ion-input { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; flex:1; min-width:8rem; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpCustomersList {
  @State() customers: Customer[] = [];
  @State() loading = true;
  @State() error = '';
  @State() newName = '';
  @State() newEmail = '';
  @State() saving = false;
  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'name', header: 'Nombre' },
    { key: 'email', header: 'Email' },
    { key: 'phone', header: 'Teléfono' },
    { key: 'lifecycle_stage', header: 'Etapa', format: (r) => STAGE_LABEL[r.lifecycle_stage as string] ?? (r.lifecycle_stage as string) },
    { key: 'total_spent', header: 'Gastado', align: 'right', format: (r) => Number(r.total_spent || 0).toFixed(2) },
  ];

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

  render() {
    return (
      <div>
        <header>
          <h2>Clientes</h2>
        </header>
        <form class="form" onSubmit={(e) => this.create(e)}>
          <ion-input
            placeholder="Nombre"
            value={this.newName}
            onIonInput={(e: any) => (this.newName = e.target.value)}
          />
          <ion-input
            type="email"
            placeholder="Email"
            value={this.newEmail}
            onIonInput={(e: any) => (this.newEmail = e.target.value)}
          />
          <ion-button type="submit" size="small" disabled={this.saving || !this.newName}>
            {this.saving ? 'Guardando…' : 'Añadir'}
          </ion-button>
        </form>
        {this.error && <p class="err">{this.error}</p>}
        <data-table
          columns={this.columns}
          rows={this.customers as unknown as Record<string, unknown>[]}
          searchKeys={['name', 'email']}
          searchPlaceholder="Buscar nombre o email…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin clientes.'}
        />
      </div>
    );
  }
}
