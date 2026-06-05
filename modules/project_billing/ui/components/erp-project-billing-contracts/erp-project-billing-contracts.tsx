import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild lo empaquete
// dentro del bundle del módulo. El shell provee los `ion-*`. (4 niveles, SIEMPRE.)
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `project_billing` (Stencil). Vista de contratos de facturación por
// proyecto: lista (con DataTable compartido) + alta rápida vía erplora.command. Toda la lógica
// (autonumeración, generación de facturas) vive en Rust/WASM; este componente NUNCA toca la BD.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface BillingContract {
  id: string;
  contract_number: string;
  project_ref: string;
  customer_name: string;
  billing_type: string;
  total_amount: string;
  hourly_rate: string;
  currency: string;
  status: string;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-project-billing-contracts',
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
export class ErpProjectBillingContracts {
  @State() contracts: BillingContract[] = [];
  @State() loading = true;
  @State() error = '';
  @State() statusFilter = '';
  @State() newCustomer = '';
  @State() newProjectRef = '';
  @State() newBillingType = 'fixed_price';
  @State() newTotal = '';
  @State() newRate = '';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'contract_number', header: 'Nº contrato' },
    { key: 'customer_name', header: 'Cliente' },
    { key: 'project_ref', header: 'Proyecto' },
    { key: 'billing_type', header: 'Modo' },
    { key: 'total_amount', header: 'Total', align: 'right', format: (r) => Number(r.total_amount).toFixed(2) },
    { key: 'status', header: 'Estado' },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('project_billing.contract.created', () => this.refresh());
      const off2 = erplora().on('project_billing.contract.activated', () => this.refresh());
      const off3 = erplora().on('project_billing.contract.closed', () => this.refresh());
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

  private async refresh() {
    this.loading = true;
    this.error = '';
    try {
      this.contracts =
        (await erplora().query<BillingContract[]>('project_billing.contracts.list', {
          project_ref: '',
          status: this.statusFilter,
          billing_type: '',
          limit: 50,
        })) ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando contratos';
    } finally {
      this.loading = false;
    }
  }

  private async createContract(ev: Event) {
    ev.preventDefault();
    if (!this.newCustomer.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('project_billing.contracts.create', {
        project_ref: this.newProjectRef.trim(),
        customer_name: this.newCustomer.trim(),
        billing_type: this.newBillingType,
        total_amount: this.newTotal || '0',
        hourly_rate: this.newRate || '0',
        currency: 'EUR',
        start_date: null,
        end_date: null,
        notes: '',
      });
      this.newCustomer = '';
      this.newProjectRef = '';
      this.newTotal = '';
      this.newRate = '';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear el contrato';
    } finally {
      this.saving = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Contratos de facturación</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createContract(e)}>
          <ion-input
            placeholder="Cliente"
            value={this.newCustomer}
            onIonInput={(e: any) => (this.newCustomer = e.target.value)}
          />
          <ion-input
            placeholder="Ref. proyecto"
            value={this.newProjectRef}
            onIonInput={(e: any) => (this.newProjectRef = e.target.value)}
          />
          <ion-select
            value={this.newBillingType}
            onIonChange={(e: any) => (this.newBillingType = e.target.value)}
          >
            <ion-select-option value="fixed_price">Precio fijo</ion-select-option>
            <ion-select-option value="time_and_material">Tiempo y material</ion-select-option>
            <ion-select-option value="milestone">Por hitos</ion-select-option>
            <ion-select-option value="retainer">Iguala</ion-select-option>
          </ion-select>
          <ion-input
            type="number"
            step="0.01"
            placeholder="Total"
            value={this.newTotal}
            onIonInput={(e: any) => (this.newTotal = e.target.value)}
          />
          <ion-input
            type="number"
            step="0.0001"
            placeholder="Tarifa/hora"
            value={this.newRate}
            onIonInput={(e: any) => (this.newRate = e.target.value)}
          />
          <ion-button type="submit" size="small" disabled={this.saving || !this.newCustomer}>
            {this.saving ? 'Guardando…' : 'Crear'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.contracts as unknown as Record<string, unknown>[]}
          searchKeys={['contract_number', 'customer_name', 'project_ref']}
          searchPlaceholder="Buscar contrato, cliente o proyecto…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin contratos.'}
        />
      </div>
    );
  }
}
