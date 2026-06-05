import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `marketplaces` (Stencil). Mini-app: listado de ejecuciones de
// sync (SyncRun) entre todas las conexiones + lanzar un sync nuevo (command sync.start).
//
// El componente NUNCA toca la BD: llama al SDK (erplora.query/command/on). El cierre del
// sync (complete) y el import de pedidos son handlers WASM — ver WASM-TODO.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface SyncRun {
  id: string;
  connection_id: string;
  sync_type: string;
  started_at: string | null;
  completed_at: string | null;
  status: string;
  items_synced: number;
  items_failed: number;
}

interface MarketplaceConnection {
  id: string;
  code: string;
}

const SYNC_TYPES = ['products', 'orders', 'inventory', 'prices'];

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-marketplaces-syncs',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .form { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; }
    .form ion-select { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:9rem; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpMarketplacesSyncs {
  @State() syncs: SyncRun[] = [];
  @State() connections: MarketplaceConnection[] = [];
  @State() loading = true;
  @State() error = '';
  @State() newConnection = '';
  @State() newSyncType = 'products';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'connection_id', header: 'Conexión', format: (r) => this.connName(r.connection_id as string) },
    { key: 'sync_type', header: 'Tipo' },
    { key: 'status', header: 'Estado' },
    { key: 'started_at', header: 'Inicio', format: (r) => (r.started_at as string) || '—' },
    { key: 'items_synced', header: 'OK', align: 'right' },
    { key: 'items_failed', header: 'Fallos', align: 'right' },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('marketplaces.sync.started', () => this.refresh());
      const off2 = erplora().on('marketplaces.sync.completed', () => this.refresh());
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
      const [runs, conns] = await Promise.all([
        erplora().query<SyncRun[]>('marketplaces.syncs.list', {
          connection_id: '',
          status: '',
          sync_type: '',
          limit: 100,
        }),
        erplora().query<MarketplaceConnection[]>('marketplaces.connections.list', {
          platform: '',
          active_only: 1,
        }),
      ]);
      this.syncs = runs ?? [];
      this.connections = conns ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando syncs';
    } finally {
      this.loading = false;
    }
  }

  private async startSync(ev: Event) {
    ev.preventDefault();
    if (!this.newConnection) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('marketplaces.syncs.start', {
        connection_id: this.newConnection,
        sync_type: this.newSyncType,
      });
      this.newConnection = '';
      this.newSyncType = 'products';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo lanzar el sync';
    } finally {
      this.saving = false;
    }
  }

  private connName(id: string): string {
    return this.connections.find((c) => c.id === id)?.code ?? '—';
  }

  render() {
    return (
      <div>
        <header>
          <h2>Ejecuciones de sync</h2>
        </header>

        <form class="form" onSubmit={(e) => this.startSync(e)}>
          <ion-select
            placeholder="Conexión…"
            value={this.newConnection}
            onIonChange={(e: any) => (this.newConnection = e.target.value)}
          >
            {this.connections.map((c) => (
              <ion-select-option value={c.id} key={c.id}>
                {c.code}
              </ion-select-option>
            ))}
          </ion-select>
          <ion-select
            placeholder="Tipo…"
            value={this.newSyncType}
            onIonChange={(e: any) => (this.newSyncType = e.target.value)}
          >
            {SYNC_TYPES.map((t) => (
              <ion-select-option value={t} key={t}>
                {t}
              </ion-select-option>
            ))}
          </ion-select>
          <ion-button type="submit" size="small" disabled={this.saving || !this.newConnection}>
            {this.saving ? 'Lanzando…' : 'Lanzar sync'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.syncs as unknown as Record<string, unknown>[]}
          searchKeys={['sync_type', 'status']}
          searchPlaceholder="Buscar tipo o estado…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin ejecuciones de sync.'}
        />
      </div>
    );
  }
}
