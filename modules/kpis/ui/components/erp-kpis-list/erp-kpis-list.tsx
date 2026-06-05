import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `kpis` (Stencil). Mini-app: lista de definiciones de KPI
// + alta rápida. Es una de las piezas `ui.entry` que el shell carga en runtime
// (modules/kpis/dist/kpis.esm.js).
//
// La lógica de clasificación/umbral/agregados vive en Rust→WASM: este componente
// NO toca la BD; llama al SDK (erplora.query/command/on). El listado usa el
// DataTable compartido + Ionic.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface Kpi {
  id: string;
  code: string;
  name: string;
  unit: string;
  kpi_type: string;
  aggregation: string;
  category: string;
  target_value: string | null;
  target_direction: string;
  is_active: number;
}

const UNITS = ['currency', 'percent', 'count', 'duration', 'ratio', 'score', 'other'];
const KPI_TYPES = ['numerical', 'percentage', 'count', 'ratio'];

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-kpis-list',
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
export class ErpKpisList {
  @State() kpis: Kpi[] = [];
  @State() loading = true;
  @State() error = '';
  @State() saving = false;

  @State() newCode = '';
  @State() newName = '';
  @State() newUnit = 'count';
  @State() newType = 'numerical';
  @State() newTarget = '';

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'code', header: 'Código' },
    { key: 'name', header: 'Nombre' },
    { key: 'unit', header: 'Unidad' },
    { key: 'category', header: 'Categoría', format: (r) => (r.category as string) || '—' },
    {
      key: 'target_value',
      header: 'Objetivo',
      align: 'right',
      format: (r) => (r.target_value != null ? Number(r.target_value).toFixed(2) : '—'),
    },
    { key: 'target_direction', header: 'Dirección' },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('kpis.kpi.created', () => this.refresh());
      const off2 = erplora().on('kpis.kpi.updated', () => this.refresh());
      const off3 = erplora().on('kpis.kpi.deactivated', () => this.refresh());
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
      const kpis = await erplora().query<Kpi[]>('kpis.kpis.list', {
        category: '',
        is_active: 1,
      });
      this.kpis = kpis ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando KPIs';
    } finally {
      this.loading = false;
    }
  }

  private async createKpi(ev: Event) {
    ev.preventDefault();
    if (!this.newCode.trim() || !this.newName.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('kpis.kpis.create', {
        code: this.newCode.trim(),
        name: this.newName.trim(),
        description: '',
        unit: this.newUnit,
        kpi_type: this.newType,
        aggregation: 'last',
        category: '',
        target_value: this.newTarget.trim() === '' ? null : Number(this.newTarget),
        target_direction: 'higher_is_better',
        critical_threshold: null,
        warning_threshold: null,
        owner_ref: null,
      });
      this.newCode = '';
      this.newName = '';
      this.newTarget = '';
      this.newUnit = 'count';
      this.newType = 'numerical';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear el KPI';
    } finally {
      this.saving = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>KPIs</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createKpi(e)}>
          <ion-input
            placeholder="Código (revenue)"
            value={this.newCode}
            onIonInput={(e: any) => (this.newCode = e.target.value)}
          />
          <ion-input
            placeholder="Nombre"
            value={this.newName}
            onIonInput={(e: any) => (this.newName = e.target.value)}
          />
          <ion-select
            placeholder="Unidad…"
            value={this.newUnit}
            onIonChange={(e: any) => (this.newUnit = e.target.value)}
          >
            {UNITS.map((u) => (
              <ion-select-option value={u} key={u}>
                {u}
              </ion-select-option>
            ))}
          </ion-select>
          <ion-select
            placeholder="Tipo…"
            value={this.newType}
            onIonChange={(e: any) => (this.newType = e.target.value)}
          >
            {KPI_TYPES.map((t) => (
              <ion-select-option value={t} key={t}>
                {t}
              </ion-select-option>
            ))}
          </ion-select>
          <ion-input
            type="number"
            step="0.0001"
            placeholder="Objetivo"
            value={this.newTarget}
            onIonInput={(e: any) => (this.newTarget = e.target.value)}
          />
          <ion-button type="submit" size="small" disabled={this.saving || !this.newCode || !this.newName}>
            {this.saving ? 'Guardando…' : 'Añadir'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.kpis as unknown as Record<string, unknown>[]}
          searchKeys={['code', 'name', 'category']}
          searchPlaceholder="Buscar KPI…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin KPIs definidos.'}
        />
      </div>
    );
  }
}
