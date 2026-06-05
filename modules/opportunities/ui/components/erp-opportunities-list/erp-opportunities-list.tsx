import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `opportunities` (Stencil). Mini-app: pipeline CRM de
// oportunidades de venta por etapas + alta rápida. Es la pieza `ui.entry` que el
// shell carga en runtime (modules/opportunities/dist/opportunities.esm.js).
//
// La lógica de negocio (numeración atómica OPP-YYYYMMDD-NNNN, probabilidad por
// etapa, valor ponderado, cierre won/lost) vive en Rust/WASM: este componente NO
// toca la BD; llama al SDK (erplora.query/command/on). El listado usa el DataTable
// compartido + formulario Ionic.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface Opportunity {
  id: string;
  opp_number: string;
  customer_name: string;
  customer_email: string;
  value: string;
  probability: number;
  expected_close_date: string | null;
  stage: string;
  close_reason: string;
  assigned_to_ref: string | null;
  notes: string;
  created_at: string | null;
}

const STAGES = ['prospecting', 'qualification', 'proposal', 'negotiation', 'won', 'lost'];

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-opportunities-list',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .form { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; }
    .form ion-input, .form ion-select { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:8rem; }
    .filters { display:flex; gap:.5rem; align-items:center; margin-bottom:.5rem; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpOpportunitiesList {
  @State() opportunities: Opportunity[] = [];
  @State() loading = true;
  @State() error = '';
  @State() stageFilter = '';
  @State() saving = false;
  @State() newCustomer = '';
  @State() newEmail = '';
  @State() newValue = '';
  @State() newStage = 'prospecting';

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'opp_number', header: 'Nº' },
    { key: 'customer_name', header: 'Cliente' },
    { key: 'stage', header: 'Etapa' },
    { key: 'value', header: 'Valor', align: 'right', format: (r) => Number(r.value).toFixed(2) },
    { key: 'probability', header: '%', align: 'right', format: (r) => `${r.probability}%` },
    {
      key: 'weighted',
      header: 'Ponderado',
      align: 'right',
      format: (r) => (Number(r.value) * Number(r.probability) / 100).toFixed(2),
    },
    { key: 'expected_close_date', header: 'Cierre est.', format: (r) => (r.expected_close_date as string) ?? '—' },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const offs = [
        erplora().on('opportunities.opportunity.created', () => this.refresh()),
        erplora().on('opportunities.opportunity.stage_changed', () => this.refresh()),
        erplora().on('opportunities.opportunity.updated', () => this.refresh()),
        erplora().on('opportunities.opportunity.won', () => this.refresh()),
        erplora().on('opportunities.opportunity.lost', () => this.refresh()),
      ];
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
      const opps = await erplora().query<Opportunity[]>('opportunities.opportunities.list', {
        stage: this.stageFilter,
        assigned_to: '',
        limit: 50,
      });
      this.opportunities = opps ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando oportunidades';
    } finally {
      this.loading = false;
    }
  }

  private async createOpportunity(ev: Event) {
    ev.preventDefault();
    if (!this.newCustomer.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('opportunities.opportunities.create', {
        customer_name: this.newCustomer.trim(),
        customer_email: this.newEmail.trim(),
        value: this.newValue.trim() || '0.00',
        stage: this.newStage,
        expected_close_date: null,
        notes: '',
      });
      this.newCustomer = '';
      this.newEmail = '';
      this.newValue = '';
      this.newStage = 'prospecting';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear la oportunidad';
    } finally {
      this.saving = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Pipeline de oportunidades</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createOpportunity(e)}>
          <ion-input
            placeholder="Cliente"
            value={this.newCustomer}
            onIonInput={(e: any) => (this.newCustomer = e.target.value)}
          />
          <ion-input
            type="email"
            placeholder="Email (opcional)"
            value={this.newEmail}
            onIonInput={(e: any) => (this.newEmail = e.target.value)}
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
            {STAGES.filter((s) => s !== 'won' && s !== 'lost').map((s) => (
              <ion-select-option value={s} key={s}>
                {s}
              </ion-select-option>
            ))}
          </ion-select>
          <ion-button type="submit" size="small" disabled={this.saving || !this.newCustomer}>
            {this.saving ? 'Guardando…' : 'Añadir'}
          </ion-button>
        </form>

        <div class="filters">
          <ion-select
            placeholder="Todas las etapas"
            value={this.stageFilter}
            onIonChange={(e: any) => {
              this.stageFilter = e.target.value;
              this.refresh();
            }}
          >
            <ion-select-option value="">Todas las etapas</ion-select-option>
            {STAGES.map((s) => (
              <ion-select-option value={s} key={s}>
                {s}
              </ion-select-option>
            ))}
          </ion-select>
        </div>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.opportunities as unknown as Record<string, unknown>[]}
          searchKeys={['opp_number', 'customer_name', 'stage']}
          searchPlaceholder="Buscar nº, cliente o etapa…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin oportunidades.'}
        />
      </div>
    );
  }
}
