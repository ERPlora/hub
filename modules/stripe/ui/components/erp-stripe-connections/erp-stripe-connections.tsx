import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild lo
// empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn, DataTableAction } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `stripe` (Stencil). Vista de conexiones Stripe: listado
// + alta rápida + baja lógica por fila. Es la pieza `ui.entry` que el shell carga en
// runtime (modules/stripe/dist/stripe.esm.js).
//
// La lógica idempotente (cargos/refunds/eventos) vive en WASM; este componente NO toca
// la BD: llama al SDK (erplora.query/command/on). El listado usa el DataTable compartido.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface StripeConnection {
  id: string;
  name: string;
  account_id: string;
  publishable_key: string;
  is_active: number;
  is_test_mode: number;
  country: string;
  default_currency: string;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-stripe-connections',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .form { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; }
    .form ion-input, .form ion-select { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:8rem; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpStripeConnections {
  @State() connections: StripeConnection[] = [];
  @State() loading = true;
  @State() error = '';
  @State() newName = '';
  @State() newAccountId = '';
  @State() newCountry = 'ES';
  @State() newCurrency = 'EUR';
  @State() newTestMode = true;
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'name', header: 'Nombre' },
    { key: 'account_id', header: 'Cuenta' },
    { key: 'country', header: 'País' },
    { key: 'default_currency', header: 'Moneda' },
    { key: 'is_test_mode', header: 'Modo', format: (r) => (Number(r.is_test_mode) ? 'Test' : 'Live') },
    { key: 'is_active', header: 'Estado', format: (r) => (Number(r.is_active) ? 'Activa' : 'Inactiva') },
  ];

  private actions: DataTableAction[] = [
    { id: 'deactivate', label: 'Desactivar', icon: 'close-circle-outline', color: 'danger' },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('stripe.connection.created', () => this.refresh());
      const off2 = erplora().on('stripe.connection.deactivated', () => this.refresh());
      this.unsub = () => {
        off1();
        off2();
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
      const conns = await erplora().query<StripeConnection[]>('stripe.connections.list', { active_only: 0 });
      this.connections = conns ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando conexiones';
    } finally {
      this.loading = false;
    }
  }

  private async createConnection(ev: Event) {
    ev.preventDefault();
    if (!this.newName.trim() || !this.newAccountId.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('stripe.connections.create', {
        name: this.newName.trim(),
        account_id: this.newAccountId.trim(),
        publishable_key: '',
        country: this.newCountry.trim().toUpperCase() || 'ES',
        default_currency: this.newCurrency.trim().toUpperCase() || 'EUR',
        is_test_mode: this.newTestMode,
      });
      this.newName = '';
      this.newAccountId = '';
      this.newCountry = 'ES';
      this.newCurrency = 'EUR';
      this.newTestMode = true;
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear la conexión';
    } finally {
      this.saving = false;
    }
  }

  private async onRowAction(ev: CustomEvent<{ actionId: string; row: Record<string, unknown> }>) {
    const { actionId, row } = ev.detail;
    if (actionId !== 'deactivate') return;
    if (!Number(row.is_active)) return;
    this.error = '';
    try {
      await erplora().command('stripe.connections.deactivate', { id: row.id as string });
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo desactivar la conexión';
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Conexiones Stripe</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createConnection(e)}>
          <ion-input
            placeholder="Nombre"
            value={this.newName}
            onIonInput={(e: any) => (this.newName = e.target.value)}
          />
          <ion-input
            placeholder="Account id (acct_…)"
            value={this.newAccountId}
            onIonInput={(e: any) => (this.newAccountId = e.target.value)}
          />
          <ion-input
            placeholder="País (ES)"
            value={this.newCountry}
            onIonInput={(e: any) => (this.newCountry = e.target.value)}
          />
          <ion-input
            placeholder="Moneda (EUR)"
            value={this.newCurrency}
            onIonInput={(e: any) => (this.newCurrency = e.target.value)}
          />
          <ion-select
            placeholder="Modo…"
            value={this.newTestMode ? 'test' : 'live'}
            onIonChange={(e: any) => (this.newTestMode = e.target.value === 'test')}
          >
            <ion-select-option value="test">Test</ion-select-option>
            <ion-select-option value="live">Live</ion-select-option>
          </ion-select>
          <ion-button type="submit" size="small" disabled={this.saving || !this.newName || !this.newAccountId}>
            {this.saving ? 'Guardando…' : 'Añadir'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.connections as unknown as Record<string, unknown>[]}
          actions={this.actions}
          searchKeys={['name', 'account_id', 'country']}
          searchPlaceholder="Buscar nombre o cuenta…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin conexiones Stripe.'}
          onRowAction={(e: CustomEvent) => this.onRowAction(e)}
        />
      </div>
    );
  }
}
