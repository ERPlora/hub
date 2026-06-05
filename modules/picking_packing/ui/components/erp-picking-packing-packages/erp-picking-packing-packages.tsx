import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `picking_packing` — vista de Paquetes.
// Mini-app: lista los paquetes del hub + alta rápida (status=open). NO toca la BD:
// todo va por el SDK (erplora.query/command/on). El número de paquete (contador) y la
// máquina de estados (open→sealed→shipped→delivered) viven en WASM.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface Package {
  id: string;
  package_number: string;
  pick_list_ref: string;
  weight_kg: string;
  carrier: string;
  status: string;
  tracking_number: string;
  created_at: string;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-picking-packing-packages',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .form { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; }
    .form ion-input { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:8rem; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpPickingPackingPackages {
  @State() packages: Package[] = [];
  @State() loading = true;
  @State() error = '';
  @State() statusFilter = '';
  @State() newPickRef = '';
  @State() newWeight = '';
  @State() newCarrier = '';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'package_number', header: 'Nº paquete' },
    { key: 'pick_list_ref', header: 'Pick', format: (r) => (r.pick_list_ref as string) || '—' },
    { key: 'status', header: 'Estado' },
    { key: 'carrier', header: 'Transportista', format: (r) => (r.carrier as string) || '—' },
    { key: 'weight_kg', header: 'Peso (kg)', align: 'right', format: (r) => Number(r.weight_kg).toFixed(3) },
    { key: 'tracking_number', header: 'Tracking', format: (r) => (r.tracking_number as string) || '—' },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const offs = [
        erplora().on('picking_packing.package.created', () => this.refresh()),
        erplora().on('picking_packing.package.sealed', () => this.refresh()),
        erplora().on('picking_packing.package.shipped', () => this.refresh()),
        erplora().on('picking_packing.package.delivered', () => this.refresh()),
      ];
      this.unsub = () => offs.forEach((o) => o());
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
      const packages = await erplora().query<Package[]>('picking_packing.packages.list', {
        status: this.statusFilter,
        limit: 50,
      });
      this.packages = packages ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando paquetes';
    } finally {
      this.loading = false;
    }
  }

  private async createPackage(ev: Event) {
    ev.preventDefault();
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('picking_packing.packages.create', {
        pick_list_ref: this.newPickRef.trim(),
        weight_kg: Number(this.newWeight) || 0,
        carrier: this.newCarrier.trim(),
      });
      this.newPickRef = '';
      this.newWeight = '';
      this.newCarrier = '';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear el paquete';
    } finally {
      this.saving = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Paquetes</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createPackage(e)}>
          <ion-input
            placeholder="Pick (ref)"
            value={this.newPickRef}
            onIonInput={(e: any) => (this.newPickRef = e.target.value)}
          />
          <ion-input
            type="number"
            step="0.001"
            placeholder="Peso (kg)"
            value={this.newWeight}
            onIonInput={(e: any) => (this.newWeight = e.target.value)}
          />
          <ion-input
            placeholder="Transportista"
            value={this.newCarrier}
            onIonInput={(e: any) => (this.newCarrier = e.target.value)}
          />
          <ion-button type="submit" size="small" disabled={this.saving}>
            {this.saving ? 'Guardando…' : 'Crear paquete'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.packages as unknown as Record<string, unknown>[]}
          searchKeys={['package_number', 'pick_list_ref', 'carrier', 'tracking_number']}
          searchPlaceholder="Buscar nº, pick, transportista o tracking…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin paquetes.'}
        />
      </div>
    );
  }
}
