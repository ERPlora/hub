import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `cashflow_forecasting` (Stencil). Vista de escenarios:
// lista de escenarios de cash-flow + alta rápida. Es parte de la pieza `ui.entry`
// que el shell carga en runtime (modules/cashflow_forecasting/dist/cashflow_forecasting.esm.js).
//
// La lógica vive en Rust/WASM: este componente NO toca la BD; llama al SDK
// (erplora.query/command/on). El listado usa el DataTable compartido + Ionic.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface Scenario {
  id: string;
  code: string;
  name: string;
  description: string;
  scenario_type: string;
  opening_balance: string;
  currency: string;
  is_active: number;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-cashflow-forecasting-scenarios',
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
export class ErpCashflowForecastingScenarios {
  @State() scenarios: Scenario[] = [];
  @State() loading = true;
  @State() error = '';
  @State() newCode = '';
  @State() newName = '';
  @State() newType = 'baseline';
  @State() newOpening = '';
  @State() newCurrency = 'EUR';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'code', header: 'Código' },
    { key: 'name', header: 'Nombre' },
    { key: 'scenario_type', header: 'Tipo' },
    { key: 'currency', header: 'Moneda' },
    { key: 'opening_balance', header: 'Saldo inicial', align: 'right', format: (r) => Number(r.opening_balance).toFixed(2) },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('cashflow_forecasting.scenario.created', () => this.refresh());
      const off2 = erplora().on('cashflow_forecasting.scenario.updated', () => this.refresh());
      const off3 = erplora().on('cashflow_forecasting.scenario.deactivated', () => this.refresh());
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
      const rows = await erplora().query<Scenario[]>('cashflow_forecasting.scenarios.list', { active_only: '1' });
      this.scenarios = rows ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando escenarios';
    } finally {
      this.loading = false;
    }
  }

  private async createScenario(ev: Event) {
    ev.preventDefault();
    if (!this.newCode.trim() || !this.newName.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('cashflow_forecasting.scenarios.create', {
        code: this.newCode.trim(),
        name: this.newName.trim(),
        description: '',
        scenario_type: this.newType,
        opening_balance: Number(this.newOpening) || 0,
        currency: this.newCurrency.trim().toUpperCase() || 'EUR',
        parameters: '{}',
      });
      this.newCode = '';
      this.newName = '';
      this.newType = 'baseline';
      this.newOpening = '';
      this.newCurrency = 'EUR';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear el escenario';
    } finally {
      this.saving = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Escenarios de cash-flow</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createScenario(e)}>
          <ion-input
            placeholder="Código (base-2026)"
            value={this.newCode}
            onIonInput={(e: any) => (this.newCode = e.target.value)}
          />
          <ion-input
            placeholder="Nombre"
            value={this.newName}
            onIonInput={(e: any) => (this.newName = e.target.value)}
          />
          <ion-select
            placeholder="Tipo…"
            value={this.newType}
            onIonChange={(e: any) => (this.newType = e.target.value)}
          >
            <ion-select-option value="baseline">baseline</ion-select-option>
            <ion-select-option value="optimistic">optimistic</ion-select-option>
            <ion-select-option value="pessimistic">pessimistic</ion-select-option>
            <ion-select-option value="custom">custom</ion-select-option>
          </ion-select>
          <ion-input
            type="number"
            step="0.0001"
            placeholder="Saldo inicial"
            value={this.newOpening}
            onIonInput={(e: any) => (this.newOpening = e.target.value)}
          />
          <ion-input
            placeholder="Moneda (EUR)"
            value={this.newCurrency}
            onIonInput={(e: any) => (this.newCurrency = e.target.value)}
          />
          <ion-button type="submit" size="small" disabled={this.saving || !this.newCode || !this.newName}>
            {this.saving ? 'Guardando…' : 'Añadir'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.scenarios as unknown as Record<string, unknown>[]}
          searchKeys={['code', 'name', 'scenario_type']}
          searchPlaceholder="Buscar código o nombre…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin escenarios.'}
        />
      </div>
    );
  }
}
