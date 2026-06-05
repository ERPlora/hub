import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `mrp` (Stencil). Mini-app: lista de runs MRP +
// disparar una corrida de planificación (netting). Es la pieza `ui.entry` que el
// shell carga en runtime (modules/mrp/dist/mrp.esm.js).
//
// El netting/agregación vive en Rust→WASM (command mrp.runs.create): este componente
// NO toca la BD; solo llama al SDK (erplora.query/command/on).

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface MrpRun {
  id: string;
  run_number: string;
  run_date: string;
  horizon_days: number;
  status: string;
  total_requirements: number;
  total_suggestions: number;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-mrp-runs',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .form { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; }
    .form ion-input, .form ion-select { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:8rem; }
    .err { color:#d9480f; font-weight:600; }
    .hint { color: var(--ink-muted, #7a756b); font-size:.85rem; margin:.25rem 0 .75rem; }
  `,
})
export class ErpMrpRuns {
  @State() runs: MrpRun[] = [];
  @State() loading = true;
  @State() error = '';
  @State() statusFilter = '';
  @State() newHorizon = '30';
  @State() running = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'run_number', header: 'Nº Run' },
    { key: 'run_date', header: 'Fecha' },
    { key: 'horizon_days', header: 'Horizonte (d)', align: 'right' },
    { key: 'status', header: 'Estado' },
    { key: 'total_requirements', header: 'Reqs', align: 'right' },
    { key: 'total_suggestions', header: 'Sugerencias', align: 'right' },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('mrp.run.completed', () => this.refresh());
      this.unsub = () => off1();
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
      const runs = await erplora().query<MrpRun[]>('mrp.runs.list', {
        status: this.statusFilter,
        limit: 50,
      });
      this.runs = runs ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando runs MRP';
    } finally {
      this.loading = false;
    }
  }

  private async createRun(ev: Event) {
    ev.preventDefault();
    this.running = true;
    this.error = '';
    try {
      // demand_inputs/on_hand/on_order/lead_times los aportan otros módulos vía el
      // orquestador; aquí lanzamos una corrida vacía (placeholder) con el horizonte.
      await erplora().command('mrp.runs.create', {
        horizon_days: Number(this.newHorizon) || 30,
        demand_inputs: [],
        on_hand: {},
        on_order: {},
        lead_times: {},
      });
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo ejecutar el MRP';
    } finally {
      this.running = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Runs MRP</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createRun(e)}>
          <ion-input
            type="number"
            min="1"
            placeholder="Horizonte (días)"
            value={this.newHorizon}
            onIonInput={(e: any) => (this.newHorizon = e.target.value)}
          />
          <ion-select
            placeholder="Filtrar estado…"
            value={this.statusFilter}
            onIonChange={(e: any) => {
              this.statusFilter = e.target.value;
              this.refresh();
            }}
          >
            <ion-select-option value="">Todos</ion-select-option>
            <ion-select-option value="running">Running</ion-select-option>
            <ion-select-option value="completed">Completed</ion-select-option>
            <ion-select-option value="failed">Failed</ion-select-option>
          </ion-select>
          <ion-button type="submit" size="small" disabled={this.running}>
            {this.running ? 'Ejecutando…' : 'Ejecutar MRP'}
          </ion-button>
        </form>
        <p class="hint">El cálculo de netting (demanda vs stock) lo ejecuta el runtime.</p>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.runs as unknown as Record<string, unknown>[]}
          searchKeys={['run_number', 'status']}
          searchPlaceholder="Buscar nº de run o estado…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin runs MRP.'}
        />
      </div>
    );
  }
}
