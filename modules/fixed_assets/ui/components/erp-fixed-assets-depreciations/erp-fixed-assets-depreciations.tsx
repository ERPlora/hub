import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `fixed_assets` (Stencil). Mini-app: lista de entradas de
// amortización posteadas + lanzador del batch mensual. NO toca la BD; usa el SDK.
// El cálculo de amortización (lineal/decreciente) vive en Rust/WASM (ver WASM-TODO).

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface DepreciationEntry {
  id: string;
  asset_id: string;
  period_start: string;
  period_end: string;
  depreciation_amount: string;
  accumulated_after: string;
  book_value_after: string;
  posted: number;
  posted_at: string | null;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-fixed-assets-depreciations',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .form { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; }
    .form ion-input { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:8rem; }
    .err { color:#d9480f; font-weight:600; }
    .ok { color:#2b8a3e; font-weight:600; }
  `,
})
export class ErpFixedAssetsDepreciations {
  @State() entries: DepreciationEntry[] = [];
  @State() loading = true;
  @State() error = '';
  @State() notice = '';
  @State() month = '';
  @State() running = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'period_start', header: 'Desde' },
    { key: 'period_end', header: 'Hasta' },
    { key: 'depreciation_amount', header: 'Amortización', align: 'right', format: (r) => Number(r.depreciation_amount).toFixed(2) },
    { key: 'accumulated_after', header: 'Acumulada', align: 'right', format: (r) => Number(r.accumulated_after).toFixed(2) },
    { key: 'book_value_after', header: 'Valor contable', align: 'right', format: (r) => Number(r.book_value_after).toFixed(2) },
    { key: 'posted', header: 'Posteada', format: (r) => (Number(r.posted) ? 'Sí' : 'No') },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off = erplora().on('fixed_assets.depreciation.posted', () => this.refresh());
      this.unsub = off;
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
      const entries = await erplora().query<DepreciationEntry[]>('fixed_assets.depreciations.list', {
        asset_id: '',
        posted: -1,
      });
      this.entries = entries ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando amortizaciones';
    } finally {
      this.loading = false;
    }
  }

  private async runMonthly(ev: Event) {
    ev.preventDefault();
    if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(this.month.trim())) {
      this.error = 'Mes inválido (formato YYYY-MM).';
      return;
    }
    this.running = true;
    this.error = '';
    this.notice = '';
    try {
      const res = await erplora().command<{ entries_posted?: number; total_depreciation?: string }>(
        'fixed_assets.depreciations.run_monthly',
        { month: this.month.trim() },
      );
      this.notice = `Amortización posteada: ${res?.entries_posted ?? 0} entradas, total ${res?.total_depreciation ?? '0.00'}.`;
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo ejecutar la amortización mensual';
    } finally {
      this.running = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Amortizaciones</h2>
        </header>

        <form class="form" onSubmit={(e) => this.runMonthly(e)}>
          <ion-input
            placeholder="Mes (YYYY-MM)"
            value={this.month}
            onIonInput={(e: any) => (this.month = e.target.value)}
          />
          <ion-button type="submit" size="small" disabled={this.running || !this.month}>
            {this.running ? 'Procesando…' : 'Amortizar mes'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}
        {this.notice && <p class="ok">{this.notice}</p>}

        <data-table
          columns={this.columns}
          rows={this.entries as unknown as Record<string, unknown>[]}
          searchKeys={['period_start', 'period_end']}
          searchPlaceholder="Buscar periodo…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin entradas de amortización.'}
        />
      </div>
    );
  }
}
