import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `cashflow_forecasting` (Stencil). Vista de proyecciones:
// lista de ejecuciones de proyección + lanzar una proyección (command WASM).
// Es parte de la pieza `ui.entry` que el shell carga en runtime.
//
// La lógica de cálculo vive en el handler WASM (run_projection): este componente
// NO toca la BD; solo llama al SDK (erplora.query/command/on) y muestra resultados.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface Projection {
  id: string;
  scenario_id: string;
  projection_number: string;
  period_start: string;
  period_end: string;
  period_unit: string;
  status: string;
}

interface Scenario {
  id: string;
  code: string;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-cashflow-forecasting-projections',
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
export class ErpCashflowForecastingProjections {
  @State() projections: Projection[] = [];
  @State() scenarios: Scenario[] = [];
  @State() loading = true;
  @State() error = '';
  @State() runScenario = '';
  @State() runStart = '';
  @State() runEnd = '';
  @State() runUnit = 'month';
  @State() running = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'projection_number', header: 'Nº proyección' },
    { key: 'scenario_id', header: 'Escenario', format: (r) => this.scenarioCode(r.scenario_id as string) },
    { key: 'period_start', header: 'Desde' },
    { key: 'period_end', header: 'Hasta' },
    { key: 'period_unit', header: 'Unidad' },
    { key: 'status', header: 'Estado' },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('cashflow_forecasting.projection.completed', () => this.refresh());
      const off2 = erplora().on('cashflow_forecasting.scenario.created', () => this.refresh());
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
      const [projs, scns] = await Promise.all([
        erplora().query<Projection[]>('cashflow_forecasting.projections.list', { scenario_id: '', limit: 50 }),
        erplora().query<Scenario[]>('cashflow_forecasting.scenarios.list', { active_only: '1' }),
      ]);
      this.projections = projs ?? [];
      this.scenarios = scns ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando proyecciones';
    } finally {
      this.loading = false;
    }
  }

  private async runProjection(ev: Event) {
    ev.preventDefault();
    if (!this.runScenario || !this.runStart || !this.runEnd) return;
    this.running = true;
    this.error = '';
    try {
      await erplora().command('cashflow_forecasting.projections.run', {
        scenario_id: this.runScenario,
        period_start: this.runStart,
        period_end: this.runEnd,
        period_unit: this.runUnit,
        inflows: [],
        outflows: [],
      });
      this.runStart = '';
      this.runEnd = '';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo lanzar la proyección';
    } finally {
      this.running = false;
    }
  }

  private scenarioCode(id: string): string {
    return this.scenarios.find((s) => s.id === id)?.code ?? '—';
  }

  render() {
    return (
      <div>
        <header>
          <h2>Proyecciones de cash-flow</h2>
        </header>

        <form class="form" onSubmit={(e) => this.runProjection(e)}>
          <ion-select
            placeholder="Escenario…"
            value={this.runScenario}
            onIonChange={(e: any) => (this.runScenario = e.target.value)}
          >
            {this.scenarios.map((s) => (
              <ion-select-option value={s.id} key={s.id}>
                {s.code}
              </ion-select-option>
            ))}
          </ion-select>
          <ion-input
            type="date"
            placeholder="Desde"
            value={this.runStart}
            onIonInput={(e: any) => (this.runStart = e.target.value)}
          />
          <ion-input
            type="date"
            placeholder="Hasta"
            value={this.runEnd}
            onIonInput={(e: any) => (this.runEnd = e.target.value)}
          />
          <ion-select
            placeholder="Unidad…"
            value={this.runUnit}
            onIonChange={(e: any) => (this.runUnit = e.target.value)}
          >
            <ion-select-option value="day">day</ion-select-option>
            <ion-select-option value="week">week</ion-select-option>
            <ion-select-option value="month">month</ion-select-option>
          </ion-select>
          <ion-button
            type="submit"
            size="small"
            disabled={this.running || !this.runScenario || !this.runStart || !this.runEnd}
          >
            {this.running ? 'Ejecutando…' : 'Lanzar proyección'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.projections as unknown as Record<string, unknown>[]}
          searchKeys={['projection_number', 'status']}
          searchPlaceholder="Buscar nº o estado…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin proyecciones.'}
        />
      </div>
    );
  }
}
