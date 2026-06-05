import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild lo
// empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn, DataTableAction } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `subscriptions` (Stencil). Vista de suscripciones: lista con
// filtro por estado + alta rápida (elige plan + cliente). El alta/activación/cancelación
// pasan por commands WASM (lógica de fechas en Rust). El componente NO toca la BD.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface Subscription {
  id: string;
  plan_id: string;
  customer_name: string;
  customer_email: string;
  status: string;
  start_date: string;
  current_period_end: string | null;
  trial_end: string | null;
}

interface Plan {
  id: string;
  code: string;
  name: string;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-subscriptions-list',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .form { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; }
    .filters { display:flex; gap:.5rem; align-items:end; margin:.25rem 0 .75rem; }
    .form ion-input, .form ion-select, .filters ion-select { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:8rem; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpSubscriptionsList {
  @State() subscriptions: Subscription[] = [];
  @State() plans: Plan[] = [];
  @State() loading = true;
  @State() error = '';
  @State() saving = false;
  @State() statusFilter = '';
  @State() newPlan = '';
  @State() newCustomer = '';
  @State() newEmail = '';

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'customer_name', header: 'Cliente' },
    { key: 'plan_id', header: 'Plan', format: (r) => this.planName(r.plan_id as string) },
    { key: 'status', header: 'Estado' },
    { key: 'start_date', header: 'Inicio' },
    { key: 'current_period_end', header: 'Fin periodo', format: (r) => (r.current_period_end as string) ?? '—' },
  ];

  private rowActions: DataTableAction[] = [{ id: 'cancel', label: 'Cancelar', color: 'danger' }];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('subscriptions.subscription.created', () => this.refresh());
      const off2 = erplora().on('subscriptions.subscription.activated', () => this.refresh());
      const off3 = erplora().on('subscriptions.subscription.cancelled', () => this.refresh());
      const off4 = erplora().on('subscriptions.cycle.generated', () => this.refresh());
      this.unsub = () => {
        off1();
        off2();
        off3();
        off4();
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
      const [subs, plans] = await Promise.all([
        erplora().query<Subscription[]>('subscriptions.subscriptions.list', {
          status: this.statusFilter,
          customer_name: '',
          limit: 50,
        }),
        erplora().query<Plan[]>('subscriptions.plans.list', { active_only: '1' }),
      ]);
      this.subscriptions = subs ?? [];
      this.plans = plans ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando suscripciones';
    } finally {
      this.loading = false;
    }
  }

  private async onStatusChange(value: string) {
    this.statusFilter = value;
    await this.refresh();
  }

  private async createSubscription(ev: Event) {
    ev.preventDefault();
    if (!this.newPlan || !this.newCustomer.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('subscriptions.subscriptions.create', {
        plan_id: this.newPlan,
        customer_name: this.newCustomer.trim(),
        customer_email: this.newEmail.trim(),
        customer_tax_id: '',
        start_date: null,
      });
      this.newPlan = '';
      this.newCustomer = '';
      this.newEmail = '';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear la suscripción';
    } finally {
      this.saving = false;
    }
  }

  private onRowAction(ev: CustomEvent<{ actionId: string; row: Record<string, unknown> }>) {
    if (ev.detail.actionId === 'cancel') {
      this.cancelSubscription(ev.detail.row.id as string);
    }
  }

  private async cancelSubscription(id: string) {
    this.error = '';
    try {
      await erplora().command('subscriptions.subscriptions.cancel', {
        subscription_id: id,
        reason: '',
        immediate: false,
      });
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo cancelar';
    }
  }

  private planName(id: string): string {
    return this.plans.find((p) => p.id === id)?.code ?? '—';
  }

  render() {
    return (
      <div>
        <header>
          <h2>Suscripciones</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createSubscription(e)}>
          <ion-select
            placeholder="Plan…"
            value={this.newPlan}
            onIonChange={(e: any) => (this.newPlan = e.target.value)}
          >
            {this.plans.map((p) => (
              <ion-select-option value={p.id} key={p.id}>
                {p.code}
              </ion-select-option>
            ))}
          </ion-select>
          <ion-input
            placeholder="Cliente"
            value={this.newCustomer}
            onIonInput={(e: any) => (this.newCustomer = e.target.value)}
          />
          <ion-input
            type="email"
            placeholder="Email"
            value={this.newEmail}
            onIonInput={(e: any) => (this.newEmail = e.target.value)}
          />
          <ion-button type="submit" size="small" disabled={this.saving || !this.newPlan || !this.newCustomer}>
            {this.saving ? 'Guardando…' : 'Suscribir'}
          </ion-button>
        </form>

        <div class="filters">
          <ion-select
            placeholder="Estado…"
            value={this.statusFilter}
            onIonChange={(e: any) => this.onStatusChange(e.target.value)}
          >
            <ion-select-option value="">Todos</ion-select-option>
            <ion-select-option value="trialing">Trialing</ion-select-option>
            <ion-select-option value="active">Active</ion-select-option>
            <ion-select-option value="past_due">Past due</ion-select-option>
            <ion-select-option value="cancelled">Cancelled</ion-select-option>
            <ion-select-option value="expired">Expired</ion-select-option>
          </ion-select>
        </div>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.subscriptions as unknown as Record<string, unknown>[]}
          searchKeys={['customer_name', 'status']}
          searchPlaceholder="Buscar cliente o estado…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin suscripciones.'}
          actions={this.rowActions}
          onRowAction={(e: CustomEvent<{ actionId: string; row: Record<string, unknown> }>) => this.onRowAction(e)}
        />
      </div>
    );
  }
}
