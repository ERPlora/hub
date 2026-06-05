import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild lo
// empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `subscriptions` (Stencil). Vista de planes: lista de planes
// de suscripción + alta rápida. Es una de las piezas `ui.entry` que el shell carga en
// runtime (modules/subscriptions/dist/subscriptions.esm.js).
//
// El componente NO toca la BD: llama al SDK (erplora.query/command/on). El listado usa
// el DataTable compartido + Ionic.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface Plan {
  id: string;
  code: string;
  name: string;
  description: string;
  billing_period: string;
  price: string;
  trial_days: number;
  is_active: number;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-subscriptions-plans',
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
export class ErpSubscriptionsPlans {
  @State() plans: Plan[] = [];
  @State() loading = true;
  @State() error = '';
  @State() saving = false;
  @State() newCode = '';
  @State() newName = '';
  @State() newPeriod = 'monthly';
  @State() newPrice = '';
  @State() newTrial = '';

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'code', header: 'Código' },
    { key: 'name', header: 'Nombre' },
    { key: 'billing_period', header: 'Periodo' },
    { key: 'price', header: 'Precio', align: 'right', format: (r) => Number(r.price).toFixed(2) },
    { key: 'trial_days', header: 'Trial (días)', align: 'right' },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off = erplora().on('subscriptions.plan.created', () => this.refresh());
      this.unsub = () => off();
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
      const plans = await erplora().query<Plan[]>('subscriptions.plans.list', { active_only: '1' });
      this.plans = plans ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando planes';
    } finally {
      this.loading = false;
    }
  }

  private async createPlan(ev: Event) {
    ev.preventDefault();
    if (!this.newCode.trim() || !this.newName.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('subscriptions.plans.create', {
        code: this.newCode.trim(),
        name: this.newName.trim(),
        description: '',
        billing_period: this.newPeriod,
        price: Number(this.newPrice) || 0,
        trial_days: Number(this.newTrial) || 0,
        features: '{}',
      });
      this.newCode = '';
      this.newName = '';
      this.newPeriod = 'monthly';
      this.newPrice = '';
      this.newTrial = '';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear el plan';
    } finally {
      this.saving = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Planes de suscripción</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createPlan(e)}>
          <ion-input
            placeholder="Código (basic)"
            value={this.newCode}
            onIonInput={(e: any) => (this.newCode = e.target.value)}
          />
          <ion-input
            placeholder="Nombre"
            value={this.newName}
            onIonInput={(e: any) => (this.newName = e.target.value)}
          />
          <ion-select
            placeholder="Periodo…"
            value={this.newPeriod}
            onIonChange={(e: any) => (this.newPeriod = e.target.value)}
          >
            <ion-select-option value="monthly">Mensual</ion-select-option>
            <ion-select-option value="quarterly">Trimestral</ion-select-option>
            <ion-select-option value="yearly">Anual</ion-select-option>
          </ion-select>
          <ion-input
            type="number"
            step="0.01"
            placeholder="Precio"
            value={this.newPrice}
            onIonInput={(e: any) => (this.newPrice = e.target.value)}
          />
          <ion-input
            type="number"
            step="1"
            placeholder="Trial (días)"
            value={this.newTrial}
            onIonInput={(e: any) => (this.newTrial = e.target.value)}
          />
          <ion-button type="submit" size="small" disabled={this.saving || !this.newCode || !this.newName}>
            {this.saving ? 'Guardando…' : 'Añadir'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.plans as unknown as Record<string, unknown>[]}
          searchKeys={['code', 'name']}
          searchPlaceholder="Buscar código o nombre…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin planes.'}
        />
      </div>
    );
  }
}
