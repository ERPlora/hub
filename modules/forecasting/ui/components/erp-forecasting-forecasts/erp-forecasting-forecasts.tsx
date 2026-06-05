import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `forecasting` (Stencil). Vista "forecasts": lista de
// ejecuciones de pronóstico recientes + acción "ejecutar" (run) sobre un modelo.
// Es una de las piezas `ui.entry` que el shell carga en runtime.
//
// El cálculo del pronóstico vive en Rust/WASM (handler.run_forecast): este componente
// NO toca la BD; solo dispara el command y lista vía query.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface ForecastModel {
  id: string;
  code: string;
  name: string;
}

interface Forecast {
  id: string;
  model_id: string;
  forecast_number: string;
  forecast_horizon_periods: number;
  period_unit: string;
  status: string;
  accuracy_score: string | null;
  created_at: string;
}

const PERIOD_UNITS = ['day', 'week', 'month', 'quarter'];

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-forecasting-forecasts',
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
export class ErpForecastingForecasts {
  @State() forecasts: Forecast[] = [];
  @State() models: ForecastModel[] = [];
  @State() loading = true;
  @State() error = '';
  @State() runModel = '';
  @State() runHorizon = '12';
  @State() runUnit = 'month';
  @State() running = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'forecast_number', header: 'Nº' },
    { key: 'model_id', header: 'Modelo', format: (r) => this.modelName(r.model_id as string) },
    { key: 'period_unit', header: 'Periodo' },
    { key: 'forecast_horizon_periods', header: 'Horizonte', align: 'right' },
    { key: 'status', header: 'Estado' },
    {
      key: 'accuracy_score',
      header: 'Precisión',
      align: 'right',
      format: (r) => (r.accuracy_score != null ? Number(r.accuracy_score).toFixed(4) : '—'),
    },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('forecasting.forecast.completed', () => this.refresh());
      const off2 = erplora().on('forecasting.forecast.accuracy_recorded', () => this.refresh());
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
      const [forecasts, models] = await Promise.all([
        erplora().query<Forecast[]>('forecasting.forecasts.list', {
          model_id: '',
          status: '',
          limit: 50,
        }),
        erplora().query<ForecastModel[]>('forecasting.models.list', {
          active_only: 1,
          target_metric: '',
        }),
      ]);
      this.forecasts = forecasts ?? [];
      this.models = models ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando pronósticos';
    } finally {
      this.loading = false;
    }
  }

  private async runForecast(ev: Event) {
    ev.preventDefault();
    if (!this.runModel) return;
    this.running = true;
    this.error = '';
    try {
      await erplora().command('forecasting.forecasts.run', {
        model_id: this.runModel,
        horizon_periods: Number(this.runHorizon) || 12,
        period_unit: this.runUnit,
        historical_data: [],
      });
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo ejecutar el pronóstico';
    } finally {
      this.running = false;
    }
  }

  private modelName(id: string): string {
    return this.models.find((m) => m.id === id)?.code ?? '—';
  }

  render() {
    return (
      <div>
        <header>
          <h2>Pronósticos</h2>
        </header>

        <form class="form" onSubmit={(e) => this.runForecast(e)}>
          <ion-select
            placeholder="Modelo…"
            value={this.runModel}
            onIonChange={(e: any) => (this.runModel = e.target.value)}
          >
            {this.models.map((m) => (
              <ion-select-option value={m.id} key={m.id}>
                {m.code}
              </ion-select-option>
            ))}
          </ion-select>
          <ion-input
            type="number"
            placeholder="Horizonte"
            value={this.runHorizon}
            onIonInput={(e: any) => (this.runHorizon = e.target.value)}
          />
          <ion-select
            placeholder="Periodo…"
            value={this.runUnit}
            onIonChange={(e: any) => (this.runUnit = e.target.value)}
          >
            {PERIOD_UNITS.map((u) => (
              <ion-select-option value={u} key={u}>
                {u}
              </ion-select-option>
            ))}
          </ion-select>
          <ion-button type="submit" size="small" disabled={this.running || !this.runModel}>
            {this.running ? 'Ejecutando…' : 'Ejecutar'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.forecasts as unknown as Record<string, unknown>[]}
          searchKeys={['forecast_number', 'status']}
          searchPlaceholder="Buscar pronóstico…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin pronósticos.'}
        />
      </div>
    );
  }
}
