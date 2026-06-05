import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `pipeline` (Stencil). Mini-app: lista de embudos
// (pipelines) y, al seleccionar uno, sus deals abiertos + alta rápida de deal.
// Es la pieza `ui.entry` que el shell carga en runtime
// (modules/pipeline/dist/pipeline.esm.js).
//
// La lógica de cálculo/transición vive en Rust/WASM: este componente NO toca la
// BD; llama al SDK (erplora.query/command/on). El listado usa el DataTable
// compartido + Ionic.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface Pipeline {
  id: string;
  name: string;
  description: string;
  is_default: number;
  is_active: number;
  color: string;
  order: number;
}

interface Stage {
  id: string;
  pipeline_id: string;
  code: string;
  name: string;
  order: number;
  is_won: number;
  is_lost: number;
}

interface Deal {
  id: string;
  pipeline_id: string;
  stage_id: string;
  deal_name: string;
  deal_value: string;
  customer_name: string;
  status: string;
  expected_close_date: string | null;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-pipeline-boards',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .form { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; }
    .form ion-input, .form ion-select { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:8rem; }
    .err { color:#d9480f; font-weight:600; }
    .pick { margin-bottom:.75rem; }
  `,
})
export class ErpPipelineBoards {
  @State() pipelines: Pipeline[] = [];
  @State() stages: Stage[] = [];
  @State() deals: Deal[] = [];
  @State() selectedPipeline = '';
  @State() loading = true;
  @State() error = '';
  @State() newName = '';
  @State() newStage = '';
  @State() newValue = '';
  @State() newCustomer = '';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'deal_name', header: 'Deal' },
    { key: 'customer_name', header: 'Cliente' },
    { key: 'stage_id', header: 'Etapa', format: (r) => this.stageName(r.stage_id as string) },
    { key: 'status', header: 'Estado' },
    { key: 'deal_value', header: 'Valor', align: 'right', format: (r) => Number(r.deal_value).toFixed(2) },
  ];

  async componentWillLoad() {
    await this.loadPipelines();
    try {
      const off1 = erplora().on('pipeline.deal.created', () => this.refreshDeals());
      const off2 = erplora().on('pipeline.deal.moved', () => this.refreshDeals());
      const off3 = erplora().on('pipeline.deal.lost', () => this.refreshDeals());
      const off4 = erplora().on('pipeline.pipeline.created', () => this.loadPipelines());
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

  private async loadPipelines() {
    this.loading = true;
    this.error = '';
    try {
      const pipelines = await erplora().query<Pipeline[]>('pipeline.pipelines.list', { active_only: 1 });
      this.pipelines = pipelines ?? [];
      if (!this.selectedPipeline && this.pipelines.length) {
        this.selectedPipeline = this.pipelines[0].id;
      }
      if (this.selectedPipeline) {
        await this.refreshStagesAndDeals();
      }
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando embudos';
    } finally {
      this.loading = false;
    }
  }

  private async refreshStagesAndDeals() {
    if (!this.selectedPipeline) return;
    const [stages, deals] = await Promise.all([
      erplora().query<Stage[]>('pipeline.stages.list', { pipeline_id: this.selectedPipeline }),
      erplora().query<Deal[]>('pipeline.deals.list', {
        pipeline_id: this.selectedPipeline,
        stage_id: '',
        status: 'open',
        limit: 100,
      }),
    ]);
    this.stages = stages ?? [];
    this.deals = deals ?? [];
    if (!this.newStage && this.stages.length) this.newStage = this.stages[0].id;
  }

  private async refreshDeals() {
    if (!this.selectedPipeline) return;
    try {
      const deals = await erplora().query<Deal[]>('pipeline.deals.list', {
        pipeline_id: this.selectedPipeline,
        stage_id: '',
        status: 'open',
        limit: 100,
      });
      this.deals = deals ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando deals';
    }
  }

  private async onSelectPipeline(id: string) {
    this.selectedPipeline = id;
    this.newStage = '';
    this.error = '';
    try {
      await this.refreshStagesAndDeals();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando embudo';
    }
  }

  private async createDeal(ev: Event) {
    ev.preventDefault();
    if (!this.newName.trim() || !this.selectedPipeline || !this.newStage) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('pipeline.deals.create', {
        pipeline_id: this.selectedPipeline,
        stage_id: this.newStage,
        deal_name: this.newName.trim(),
        deal_value: this.newValue.trim() || '0.00',
        customer_name: this.newCustomer.trim(),
        expected_close_date: null,
      });
      this.newName = '';
      this.newValue = '';
      this.newCustomer = '';
      await this.refreshDeals();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear el deal';
    } finally {
      this.saving = false;
    }
  }

  private stageName(id: string): string {
    return this.stages.find((s) => s.id === id)?.name ?? '—';
  }

  render() {
    return (
      <div>
        <header>
          <h2>Pipeline</h2>
        </header>

        <ion-select
          class="pick"
          placeholder="Embudo…"
          value={this.selectedPipeline}
          onIonChange={(e: any) => this.onSelectPipeline(e.target.value)}
        >
          {this.pipelines.map((p) => (
            <ion-select-option value={p.id} key={p.id}>
              {p.name}
            </ion-select-option>
          ))}
        </ion-select>

        <form class="form" onSubmit={(e) => this.createDeal(e)}>
          <ion-input
            placeholder="Nombre del deal"
            value={this.newName}
            onIonInput={(e: any) => (this.newName = e.target.value)}
          />
          <ion-input
            placeholder="Cliente"
            value={this.newCustomer}
            onIonInput={(e: any) => (this.newCustomer = e.target.value)}
          />
          <ion-input
            type="number"
            step="0.01"
            placeholder="Valor"
            value={this.newValue}
            onIonInput={(e: any) => (this.newValue = e.target.value)}
          />
          <ion-select
            placeholder="Etapa…"
            value={this.newStage}
            onIonChange={(e: any) => (this.newStage = e.target.value)}
          >
            {this.stages.map((s) => (
              <ion-select-option value={s.id} key={s.id}>
                {s.name}
              </ion-select-option>
            ))}
          </ion-select>
          <ion-button
            type="submit"
            size="small"
            disabled={this.saving || !this.newName || !this.selectedPipeline || !this.newStage}
          >
            {this.saving ? 'Guardando…' : 'Añadir deal'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.deals as unknown as Record<string, unknown>[]}
          searchKeys={['deal_name', 'customer_name']}
          searchPlaceholder="Buscar deal o cliente…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin deals abiertos.'}
        />
      </div>
    );
  }
}
