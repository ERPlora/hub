import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn, DataTableAction } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `credit_risk` (Stencil). Mini-app: lista de perfiles de
// crédito por cliente (límite, exposición, crédito disponible, score, estado) + alta
// rápida y bloqueo/desbloqueo. Es una pieza `ui.entry` que el shell carga en runtime
// (modules/credit_risk/dist/credit_risk.esm.js).
//
// La lógica de cálculo (exposición, scoring, alertas) vive en Rust/WASM: este componente
// NO toca la BD; llama al SDK (erplora.query/command/on). El listado usa el DataTable
// compartido + Ionic.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface CustomerCredit {
  id: string;
  customer_ref: string;
  customer_name: string;
  credit_limit: string;
  payment_terms_days: number;
  current_exposure: string;
  available_credit: string;
  credit_score: number;
  status: string;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-credit-risk-customers',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .form { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; }
    .form ion-input { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:8rem; }
    .err { color:#d9480f; font-weight:600; }
    .status { text-transform:capitalize; }
  `,
})
export class ErpCreditRiskCustomers {
  @State() customers: CustomerCredit[] = [];
  @State() loading = true;
  @State() error = '';
  @State() statusFilter = '';
  @State() newRef = '';
  @State() newName = '';
  @State() newLimit = '';
  @State() newTerms = '';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'customer_name', header: 'Cliente' },
    { key: 'customer_ref', header: 'Ref' },
    { key: 'credit_limit', header: 'Límite', align: 'right', format: (r) => Number(r.credit_limit).toFixed(2) },
    { key: 'current_exposure', header: 'Exposición', align: 'right', format: (r) => Number(r.current_exposure).toFixed(2) },
    { key: 'available_credit', header: 'Disponible', align: 'right', format: (r) => Math.max(0, Number(r.available_credit)).toFixed(2) },
    { key: 'credit_score', header: 'Score', align: 'right' },
    { key: 'status', header: 'Estado' },
  ];

  private actions: DataTableAction[] = [{ id: 'toggle_block', label: 'Bloquear/Desbloquear', icon: 'lock-closed-outline' }];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('credit_risk.customer.registered', () => this.refresh());
      const off2 = erplora().on('credit_risk.customer.blocked', () => this.refresh());
      const off3 = erplora().on('credit_risk.customer.unblocked', () => this.refresh());
      const off4 = erplora().on('credit_risk.event.recorded', () => this.refresh());
      const off5 = erplora().on('credit_risk.limit.updated', () => this.refresh());
      const off6 = erplora().on('credit_risk.score.updated', () => this.refresh());
      this.unsub = () => {
        off1();
        off2();
        off3();
        off4();
        off5();
        off6();
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
      const rows = await erplora().query<CustomerCredit[]>('credit_risk.customers.list', {
        status: this.statusFilter,
      });
      this.customers = rows ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando perfiles de crédito';
    } finally {
      this.loading = false;
    }
  }

  private async registerCustomer(ev: Event) {
    ev.preventDefault();
    if (!this.newRef.trim() || !this.newName.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('credit_risk.customers.register', {
        customer_ref: this.newRef.trim(),
        customer_name: this.newName.trim(),
        credit_limit: Number(this.newLimit) || 0,
        payment_terms_days: Number(this.newTerms) || 30,
      });
      this.newRef = '';
      this.newName = '';
      this.newLimit = '';
      this.newTerms = '';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo registrar el cliente';
    } finally {
      this.saving = false;
    }
  }

  private async toggleBlock(c: CustomerCredit) {
    this.error = '';
    try {
      if (c.status === 'blocked') {
        await erplora().command('credit_risk.customers.unblock', { customer_credit_id: c.id });
      } else {
        const reason = 'Bloqueado desde el panel de crédito';
        await erplora().command('credit_risk.customers.block', {
          customer_credit_id: c.id,
          reason,
        });
      }
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo cambiar el estado';
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Perfiles de crédito</h2>
          <ion-select
            placeholder="Estado…"
            value={this.statusFilter}
            onIonChange={(e: any) => {
              this.statusFilter = e.target.value;
              this.refresh();
            }}
          >
            <ion-select-option value="">Todos</ion-select-option>
            <ion-select-option value="active">Activo</ion-select-option>
            <ion-select-option value="on_hold">En espera</ion-select-option>
            <ion-select-option value="blocked">Bloqueado</ion-select-option>
          </ion-select>
        </header>

        <form class="form" onSubmit={(e) => this.registerCustomer(e)}>
          <ion-input
            placeholder="Ref cliente"
            value={this.newRef}
            onIonInput={(e: any) => (this.newRef = e.target.value)}
          />
          <ion-input
            placeholder="Nombre"
            value={this.newName}
            onIonInput={(e: any) => (this.newName = e.target.value)}
          />
          <ion-input
            type="number"
            step="0.01"
            placeholder="Límite"
            value={this.newLimit}
            onIonInput={(e: any) => (this.newLimit = e.target.value)}
          />
          <ion-input
            type="number"
            placeholder="Días pago (30)"
            value={this.newTerms}
            onIonInput={(e: any) => (this.newTerms = e.target.value)}
          />
          <ion-button type="submit" size="small" disabled={this.saving || !this.newRef || !this.newName}>
            {this.saving ? 'Guardando…' : 'Registrar'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.customers as unknown as Record<string, unknown>[]}
          searchKeys={['customer_name', 'customer_ref']}
          searchPlaceholder="Buscar cliente o ref…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin perfiles de crédito.'}
          actions={this.actions}
          onRowAction={(e: CustomEvent<{ actionId: string; row: Record<string, unknown> }>) =>
            this.toggleBlock(e.detail.row as unknown as CustomerCredit)
          }
        />
      </div>
    );
  }
}
