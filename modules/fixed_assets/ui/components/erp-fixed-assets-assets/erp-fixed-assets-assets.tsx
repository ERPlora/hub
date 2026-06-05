import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `fixed_assets` (Stencil). Mini-app: lista de activos fijos
// con su valor contable + alta rápida. Es la pieza `ui.entry` que el shell carga en
// runtime (modules/fixed_assets/dist/fixed_assets.esm.js).
//
// La lógica fiscal/contable (autonumeración, amortización, baja) vive en Rust/WASM:
// este componente NO toca la BD; llama al SDK (erplora.query/command/on).

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface FixedAsset {
  id: string;
  asset_number: string;
  code: string;
  name: string;
  asset_category: string;
  depreciation_method: string;
  acquisition_cost: string;
  accumulated_depreciation: string;
  current_book_value: string;
  status: string;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-fixed-assets-assets',
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
export class ErpFixedAssetsAssets {
  @State() assets: FixedAsset[] = [];
  @State() loading = true;
  @State() error = '';
  @State() statusFilter = '';
  @State() newCode = '';
  @State() newName = '';
  @State() newCost = '';
  @State() newLife = '';
  @State() newMethod = 'linear';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'asset_number', header: 'Nº' },
    { key: 'code', header: 'Código' },
    { key: 'name', header: 'Nombre' },
    { key: 'asset_category', header: 'Categoría' },
    { key: 'depreciation_method', header: 'Método' },
    { key: 'acquisition_cost', header: 'Coste', align: 'right', format: (r) => Number(r.acquisition_cost).toFixed(2) },
    { key: 'current_book_value', header: 'Valor contable', align: 'right', format: (r) => Number(r.current_book_value).toFixed(2) },
    { key: 'status', header: 'Estado' },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('fixed_assets.asset.registered', () => this.refresh());
      const off2 = erplora().on('fixed_assets.asset.updated', () => this.refresh());
      const off3 = erplora().on('fixed_assets.asset.disposed', () => this.refresh());
      const off4 = erplora().on('fixed_assets.depreciation.posted', () => this.refresh());
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

  private async refresh() {
    this.loading = true;
    this.error = '';
    try {
      const assets = await erplora().query<FixedAsset[]>('fixed_assets.assets.list', {
        status: this.statusFilter,
        category: '',
        limit: 100,
      });
      this.assets = assets ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando activos';
    } finally {
      this.loading = false;
    }
  }

  private async createAsset(ev: Event) {
    ev.preventDefault();
    if (!this.newCode.trim() || !this.newName.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('fixed_assets.assets.register', {
        code: this.newCode.trim(),
        name: this.newName.trim(),
        acquisition_cost: Number(this.newCost) || 0,
        useful_life_years: Number(this.newLife) || 0,
        depreciation_method: this.newMethod,
        residual_value: 0,
        asset_category: '',
        description: '',
      });
      this.newCode = '';
      this.newName = '';
      this.newCost = '';
      this.newLife = '';
      this.newMethod = 'linear';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo registrar el activo';
    } finally {
      this.saving = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Activos fijos</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createAsset(e)}>
          <ion-input
            placeholder="Código"
            value={this.newCode}
            onIonInput={(e: any) => (this.newCode = e.target.value)}
          />
          <ion-input
            placeholder="Nombre"
            value={this.newName}
            onIonInput={(e: any) => (this.newName = e.target.value)}
          />
          <ion-input
            type="number"
            step="0.01"
            placeholder="Coste"
            value={this.newCost}
            onIonInput={(e: any) => (this.newCost = e.target.value)}
          />
          <ion-input
            type="number"
            step="1"
            placeholder="Vida (años)"
            value={this.newLife}
            onIonInput={(e: any) => (this.newLife = e.target.value)}
          />
          <ion-select
            placeholder="Método…"
            value={this.newMethod}
            onIonChange={(e: any) => (this.newMethod = e.target.value)}
          >
            <ion-select-option value="linear">Lineal</ion-select-option>
            <ion-select-option value="declining">Decreciente</ion-select-option>
            <ion-select-option value="units_of_production">Unidades de producción</ion-select-option>
          </ion-select>
          <ion-button type="submit" size="small" disabled={this.saving || !this.newCode || !this.newName}>
            {this.saving ? 'Guardando…' : 'Registrar'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.assets as unknown as Record<string, unknown>[]}
          searchKeys={['asset_number', 'code', 'name', 'asset_category']}
          searchPlaceholder="Buscar activo…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin activos fijos.'}
        />
      </div>
    );
  }
}
