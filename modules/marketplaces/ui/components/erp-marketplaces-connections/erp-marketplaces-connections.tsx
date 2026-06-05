import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `marketplaces` (Stencil). Mini-app: lista de conexiones a
// marketplaces externos + alta rápida. Es una de las piezas que el shell carga vía
// `ui.entry` (modules/marketplaces/dist/marketplaces.esm.js).
//
// El componente NUNCA toca la BD: llama al SDK (erplora.query/command/on). El alta de
// conexión va por command (Tier 0 SQL). El enmascarado de credenciales vive en WASM/runtime.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface MarketplaceConnection {
  id: string;
  code: string;
  platform: string;
  name: string;
  is_active: number;
  region: string;
  last_sync_at: string | null;
  last_sync_status: string;
}

const PLATFORMS = ['amazon', 'ebay', 'aliexpress', 'etsy', 'other'];

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-marketplaces-connections',
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
export class ErpMarketplacesConnections {
  @State() connections: MarketplaceConnection[] = [];
  @State() loading = true;
  @State() error = '';
  @State() newCode = '';
  @State() newName = '';
  @State() newPlatform = 'other';
  @State() newRegion = '';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'code', header: 'Código' },
    { key: 'name', header: 'Nombre' },
    { key: 'platform', header: 'Plataforma' },
    { key: 'region', header: 'Región' },
    { key: 'last_sync_status', header: 'Último sync', format: (r) => (r.last_sync_status as string) || '—' },
    { key: 'is_active', header: 'Activa', format: (r) => (r.is_active ? 'Sí' : 'No') },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('marketplaces.connection.created', () => this.refresh());
      const off2 = erplora().on('marketplaces.connection.deactivated', () => this.refresh());
      const off3 = erplora().on('marketplaces.sync.completed', () => this.refresh());
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
      const rows = await erplora().query<MarketplaceConnection[]>('marketplaces.connections.list', {
        platform: '',
        active_only: 0,
      });
      this.connections = rows ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando conexiones';
    } finally {
      this.loading = false;
    }
  }

  private async createConnection(ev: Event) {
    ev.preventDefault();
    if (!this.newCode.trim() || !this.newName.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('marketplaces.connections.create', {
        code: this.newCode.trim(),
        platform: this.newPlatform,
        name: this.newName.trim(),
        credentials: {},
        region: this.newRegion.trim(),
      });
      this.newCode = '';
      this.newName = '';
      this.newPlatform = 'other';
      this.newRegion = '';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear la conexión';
    } finally {
      this.saving = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Conexiones de marketplace</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createConnection(e)}>
          <ion-input
            placeholder="Código (mi-amazon)"
            value={this.newCode}
            onIonInput={(e: any) => (this.newCode = e.target.value)}
          />
          <ion-input
            placeholder="Nombre"
            value={this.newName}
            onIonInput={(e: any) => (this.newName = e.target.value)}
          />
          <ion-select
            placeholder="Plataforma…"
            value={this.newPlatform}
            onIonChange={(e: any) => (this.newPlatform = e.target.value)}
          >
            {PLATFORMS.map((p) => (
              <ion-select-option value={p} key={p}>
                {p}
              </ion-select-option>
            ))}
          </ion-select>
          <ion-input
            placeholder="Región (eu-west-1)"
            value={this.newRegion}
            onIonInput={(e: any) => (this.newRegion = e.target.value)}
          />
          <ion-button type="submit" size="small" disabled={this.saving || !this.newCode || !this.newName}>
            {this.saving ? 'Guardando…' : 'Añadir'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.connections as unknown as Record<string, unknown>[]}
          searchKeys={['code', 'name', 'platform']}
          searchPlaceholder="Buscar código, nombre o plataforma…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin conexiones de marketplace.'}
        />
      </div>
    );
  }
}
