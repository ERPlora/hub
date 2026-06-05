import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `mrp` (Stencil). Vista de requerimientos de material
// computados por los runs MRP + sugerencias de aprovisionamiento (aprobar/rechazar).
// NO toca la BD; llama al SDK (erplora.query/command/on).

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface MrpRequirement {
  id: string;
  run_id: string;
  product_ref: string;
  required_date: string | null;
  quantity_required: string;
  quantity_on_hand: string;
  quantity_on_order: string;
  net_requirement: string;
  source_type: string;
  source_ref: string;
}

interface MrpSuggestion {
  id: string;
  product_ref: string;
  suggested_type: string;
  quantity: string;
  suggested_date: string | null;
  lead_time_days: number;
  status: string;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-mrp-requirements',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .filters { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; }
    .filters ion-input { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:10rem; }
    h3 { font-size:1rem; margin:1.5rem 0 .5rem; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpMrpRequirements {
  @State() requirements: MrpRequirement[] = [];
  @State() suggestions: MrpSuggestion[] = [];
  @State() loading = true;
  @State() error = '';
  @State() productFilter = '';

  private unsub?: () => void;

  private reqColumns: DataTableColumn[] = [
    { key: 'product_ref', header: 'Producto' },
    { key: 'required_date', header: 'Fecha req.' },
    { key: 'quantity_required', header: 'Requerido', align: 'right' },
    { key: 'quantity_on_hand', header: 'En stock', align: 'right' },
    { key: 'quantity_on_order', header: 'Pedido', align: 'right' },
    { key: 'net_requirement', header: 'Neto', align: 'right' },
    { key: 'source_type', header: 'Origen' },
  ];

  private sugColumns: DataTableColumn[] = [
    { key: 'product_ref', header: 'Producto' },
    { key: 'suggested_type', header: 'Acción' },
    { key: 'quantity', header: 'Cantidad', align: 'right' },
    { key: 'suggested_date', header: 'Fecha sug.' },
    { key: 'lead_time_days', header: 'Lead (d)', align: 'right' },
    { key: 'status', header: 'Estado' },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('mrp.run.completed', () => this.refresh());
      const off2 = erplora().on('mrp.suggestion.approved', () => this.refresh());
      const off3 = erplora().on('mrp.suggestion.rejected', () => this.refresh());
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
      const [reqs, sugs] = await Promise.all([
        erplora().query<MrpRequirement[]>('mrp.requirements.list', {
          run_id: '',
          product_ref: this.productFilter,
          limit: 200,
        }),
        erplora().query<MrpSuggestion[]>('mrp.suggestions.list', {
          run_id: '',
          status: 'pending',
          suggested_type: '',
          limit: 200,
        }),
      ]);
      this.requirements = reqs ?? [];
      this.suggestions = sugs ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando requerimientos MRP';
    } finally {
      this.loading = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Requerimientos de material</h2>
        </header>

        <div class="filters">
          <ion-input
            placeholder="Filtrar por producto…"
            value={this.productFilter}
            onIonInput={(e: any) => (this.productFilter = e.target.value)}
            onIonChange={() => this.refresh()}
          />
          <ion-button size="small" onClick={() => this.refresh()}>
            Buscar
          </ion-button>
        </div>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.reqColumns}
          rows={this.requirements as unknown as Record<string, unknown>[]}
          searchKeys={['product_ref', 'source_type']}
          searchPlaceholder="Buscar producto u origen…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin requerimientos.'}
        />

        <h3>Sugerencias pendientes</h3>
        <data-table
          columns={this.sugColumns}
          rows={this.suggestions as unknown as Record<string, unknown>[]}
          searchKeys={['product_ref', 'suggested_type']}
          searchPlaceholder="Buscar producto o acción…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin sugerencias pendientes.'}
        />
      </div>
    );
  }
}
