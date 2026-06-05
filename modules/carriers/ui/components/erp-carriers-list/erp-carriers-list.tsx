import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `carriers` (Stencil). Vista "list": transportistas
// configurados del hub + alta rápida. Es parte de la pieza `ui.entry` que el
// shell carga en runtime (modules/carriers/dist/carriers.esm.js).
//
// El componente NO toca la BD: llama al SDK (erplora.query/command/on).

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface Carrier {
  id: string;
  code: string;
  name: string;
  provider: string;
  is_active: number;
  supports_pickup: number;
  supports_tracking: number;
}

const PROVIDERS = ['seur', 'mrw', 'gls', 'dhl', 'ups', 'correos', 'nacex', 'zeleris', 'custom'];

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-carriers-list',
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
export class ErpCarriersList {
  @State() carriers: Carrier[] = [];
  @State() loading = true;
  @State() error = '';
  @State() newCode = '';
  @State() newName = '';
  @State() newProvider = 'custom';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'code', header: 'Código' },
    { key: 'name', header: 'Nombre' },
    { key: 'provider', header: 'Proveedor' },
    { key: 'is_active', header: 'Activo', format: (r) => (Number(r.is_active) ? 'Sí' : 'No') },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('carriers.carrier.created', () => this.refresh());
      const off2 = erplora().on('carriers.carrier.deactivated', () => this.refresh());
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
      const rows = await erplora().query<Carrier[]>('carriers.carriers.list', {
        active_only: 0,
        provider: '',
      });
      this.carriers = rows ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando transportistas';
    } finally {
      this.loading = false;
    }
  }

  private async createCarrier(ev: Event) {
    ev.preventDefault();
    if (!this.newCode.trim() || !this.newName.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('carriers.carriers.create', {
        code: this.newCode.trim(),
        name: this.newName.trim(),
        provider: this.newProvider,
        service_types: [],
        supports_pickup: true,
        supports_tracking: true,
        max_weight_kg: null,
        max_dimensions: null,
        account_credentials_hash: '',
      });
      this.newCode = '';
      this.newName = '';
      this.newProvider = 'custom';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear el transportista';
    } finally {
      this.saving = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Transportistas</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createCarrier(e)}>
          <ion-input
            placeholder="Código (SEUR-ES)"
            value={this.newCode}
            onIonInput={(e: any) => (this.newCode = e.target.value)}
          />
          <ion-input
            placeholder="Nombre"
            value={this.newName}
            onIonInput={(e: any) => (this.newName = e.target.value)}
          />
          <ion-select
            placeholder="Proveedor…"
            value={this.newProvider}
            onIonChange={(e: any) => (this.newProvider = e.target.value)}
          >
            {PROVIDERS.map((p) => (
              <ion-select-option value={p} key={p}>
                {p}
              </ion-select-option>
            ))}
          </ion-select>
          <ion-button type="submit" size="small" disabled={this.saving || !this.newCode || !this.newName}>
            {this.saving ? 'Guardando…' : 'Añadir'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.carriers as unknown as Record<string, unknown>[]}
          searchKeys={['code', 'name', 'provider']}
          searchPlaceholder="Buscar código, nombre o proveedor…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin transportistas.'}
        />
      </div>
    );
  }
}
