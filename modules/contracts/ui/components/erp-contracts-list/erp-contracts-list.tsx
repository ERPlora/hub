import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn, DataTableAction } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `contracts` (Stencil). Mini-app: lista de contratos +
// filtro por estado + alta rápida + acciones de ciclo de vida (activar / terminar).
// Es la pieza `ui.entry` que el shell carga en runtime (modules/contracts/dist/contracts.esm.js).
//
// La lógica vive en Rust/WASM: este componente NO toca la BD; llama al SDK
// (erplora.query/command/on). El nº de contrato (COR-YYYYMMDD-NNNN) lo genera el
// handler WASM (ver WASM-TODO.md); la UI solo recoge inputs y muestra resultados.
// El cliente se obtiene de `globalThis.erplora` (lo monta el shell en el boot).

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface Contract {
  id: string;
  contract_number: string;
  customer_name: string;
  customer_email: string;
  customer_tax_id: string;
  contract_type: string;
  status: string;
  start_date: string | null;
  end_date: string | null;
  monthly_amount: string;
  total_amount: string;
  auto_renew: number;
  renewal_period_months: number;
}

const STATUS_LABELS: Record<string, string> = {
  draft: 'Borrador',
  active: 'Activo',
  suspended: 'Suspendido',
  terminated: 'Terminado',
  expired: 'Caducado',
};

const TYPE_LABELS: Record<string, string> = {
  service: 'Servicio',
  recurring: 'Recurrente',
  maintenance: 'Mantenimiento',
  other: 'Otro',
};

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-contracts-list',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ion-text-color, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .form { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; }
    .form ion-input, .form ion-select { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:8rem; flex:1; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpContractsList {
  @State() contracts: Contract[] = [];
  @State() loading = true;
  @State() error = '';
  @State() filterStatus = '';
  @State() newCustomer = '';
  @State() newType = 'service';
  @State() newMonthly = '';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'contract_number', header: 'Número' },
    { key: 'customer_name', header: 'Cliente' },
    { key: 'contract_type', header: 'Tipo', format: (r) => TYPE_LABELS[r.contract_type as string] ?? (r.contract_type as string) },
    { key: 'status', header: 'Estado', format: (r) => STATUS_LABELS[r.status as string] ?? (r.status as string) },
    { key: 'monthly_amount', header: 'Mensual', align: 'right', format: (r) => Number(r.monthly_amount).toFixed(2) },
    { key: 'total_amount', header: 'Total', align: 'right', format: (r) => Number(r.total_amount).toFixed(2) },
  ];

  // Acciones de fila de ciclo de vida. El DataTable las muestra en todas las filas;
  // el handler ignora las que no apliquen al estado actual (lo revalida Rust).
  private actions: DataTableAction[] = [
    { id: 'activate', label: 'Activar', color: 'success' },
    { id: 'terminate', label: 'Terminar', color: 'danger' },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const events = [
        'contracts.contract.created',
        'contracts.contract.activated',
        'contracts.contract.suspended',
        'contracts.contract.resumed',
        'contracts.contract.terminated',
        'contracts.contract.expired',
      ];
      const offs = events.map((e) => erplora().on(e, () => this.refresh()));
      this.unsub = () => offs.forEach((off) => off());
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
      const rows = await erplora().query<Contract[]>('contracts.contracts.list', {
        status: this.filterStatus,
        customer_name: '',
        limit: 50,
      });
      this.contracts = rows ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando contratos';
    } finally {
      this.loading = false;
    }
  }

  private async onFilterChange(value: string) {
    this.filterStatus = value;
    await this.refresh();
  }

  private async createContract(ev: Event) {
    ev.preventDefault();
    if (!this.newCustomer.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      // El handler WASM genera el nº de contrato (counter por hub+día) antes de persistir.
      await erplora().command('contracts.contracts.create', {
        customer_name: this.newCustomer.trim(),
        contract_type: this.newType,
        customer_email: '',
        customer_tax_id: '',
        start_date: null,
        end_date: null,
        monthly_amount: this.newMonthly || '0',
        total_amount: '0',
        auto_renew: false,
        renewal_period_months: 0,
        notes: '',
        terms: '',
      });
      this.newCustomer = '';
      this.newType = 'service';
      this.newMonthly = '';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear el contrato';
    } finally {
      this.saving = false;
    }
  }

  private async activate(id: string) {
    try {
      await erplora().command('contracts.contracts.activate', { contract_id: id });
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo activar';
    }
  }

  private async terminate(id: string) {
    try {
      await erplora().command('contracts.contracts.terminate', { contract_id: id, reason: '' });
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo terminar';
    }
  }

  private onRowAction = (ev: CustomEvent<{ actionId: string; row: Record<string, unknown> }>) => {
    const { actionId, row } = ev.detail;
    if (actionId === 'activate' && row.status === 'draft') {
      this.activate(row.id as string);
    } else if (actionId === 'terminate' && (row.status === 'active' || row.status === 'suspended')) {
      this.terminate(row.id as string);
    }
  };

  render() {
    return (
      <div>
        <header>
          <h2>Contratos</h2>
          <ion-select
            placeholder="Todos los estados"
            value={this.filterStatus}
            interface="popover"
            onIonChange={(e: any) => this.onFilterChange(e.target.value)}
          >
            <ion-select-option value="">Todos los estados</ion-select-option>
            <ion-select-option value="draft">Borrador</ion-select-option>
            <ion-select-option value="active">Activo</ion-select-option>
            <ion-select-option value="suspended">Suspendido</ion-select-option>
            <ion-select-option value="terminated">Terminado</ion-select-option>
            <ion-select-option value="expired">Caducado</ion-select-option>
          </ion-select>
        </header>

        <form class="form" onSubmit={(e) => this.createContract(e)}>
          <ion-input
            placeholder="Cliente"
            value={this.newCustomer}
            onIonInput={(e: any) => (this.newCustomer = e.target.value)}
          />
          <ion-select
            placeholder="Tipo…"
            value={this.newType}
            interface="popover"
            onIonChange={(e: any) => (this.newType = e.target.value)}
          >
            <ion-select-option value="service">Servicio</ion-select-option>
            <ion-select-option value="recurring">Recurrente</ion-select-option>
            <ion-select-option value="maintenance">Mantenimiento</ion-select-option>
            <ion-select-option value="other">Otro</ion-select-option>
          </ion-select>
          <ion-input
            type="number"
            step="0.01"
            placeholder="Importe mensual"
            value={this.newMonthly}
            onIonInput={(e: any) => (this.newMonthly = e.target.value)}
          />
          <ion-button type="submit" size="small" disabled={this.saving || !this.newCustomer}>
            {this.saving ? 'Guardando…' : 'Nuevo contrato'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.contracts as unknown as Record<string, unknown>[]}
          actions={this.actions}
          searchKeys={['contract_number', 'customer_name']}
          searchPlaceholder="Buscar número o cliente…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin contratos.'}
          onRowAction={this.onRowAction}
        />
      </div>
    );
  }
}
