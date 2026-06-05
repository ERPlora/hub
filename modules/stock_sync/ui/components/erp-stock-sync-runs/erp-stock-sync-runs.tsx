import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `stock_sync` (Stencil). Mini-app: lista de runs de
// sincronización + arranque de un nuevo run entre dos canales. Es una de las dos
// piezas que el shell carga vía ui.entry (modules/stock_sync/dist/stock_sync.esm.js).
//
// La lógica (numeración atómica del run, batch de items, bump de last_sync_at, etc.)
// vive en el handler WASM; este componente NO toca la BD: llama al SDK
// (erplora.query/command/on) y lista con el DataTable compartido.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface SyncRun {
  id: string;
  run_number: string;
  source_channel_id: string;
  target_channel_id: string;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  items_synced: number;
  conflicts_count: number;
  error_log: string;
}

interface Channel {
  id: string;
  code: string;
  name: string;
  channel_type: string;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-stock-sync-runs',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .form { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; }
    .form ion-select { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:10rem; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpStockSyncRuns {
  @State() runs: SyncRun[] = [];
  @State() channels: Channel[] = [];
  @State() loading = true;
  @State() error = '';
  @State() statusFilter = '';
  @State() newSource = '';
  @State() newTarget = '';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'run_number', header: 'Nº run' },
    { key: 'source_channel_id', header: 'Origen', format: (r) => this.chCode(r.source_channel_id as string) },
    { key: 'target_channel_id', header: 'Destino', format: (r) => this.chCode(r.target_channel_id as string) },
    { key: 'status', header: 'Estado' },
    { key: 'items_synced', header: 'Items', align: 'right' },
    { key: 'conflicts_count', header: 'Conflictos', align: 'right' },
    { key: 'started_at', header: 'Inicio', format: (r) => this.fmtDate(r.started_at as string | null) },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('stock_sync.run.started', () => this.refresh());
      const off2 = erplora().on('stock_sync.run.completed', () => this.refresh());
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
      const [runs, channels] = await Promise.all([
        erplora().query<SyncRun[]>('stock_sync.runs.list', {
          status: this.statusFilter,
          source_id: '',
          limit: 50,
        }),
        erplora().query<Channel[]>('stock_sync.channels.list', { active_only: 1 }),
      ]);
      this.runs = runs ?? [];
      this.channels = channels ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando runs';
    } finally {
      this.loading = false;
    }
  }

  private async startSync(ev: Event) {
    ev.preventDefault();
    if (!this.newSource || !this.newTarget || this.newSource === this.newTarget) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('stock_sync.runs.start', {
        source_channel_id: this.newSource,
        target_channel_id: this.newTarget,
        products: [],
      });
      this.newSource = '';
      this.newTarget = '';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo arrancar el run';
    } finally {
      this.saving = false;
    }
  }

  private chCode(id: string): string {
    return this.channels.find((c) => c.id === id)?.code ?? '—';
  }

  private fmtDate(iso: string | null): string {
    return iso ? iso.slice(0, 19).replace('T', ' ') : '—';
  }

  render() {
    return (
      <div>
        <header>
          <h2>Runs de sincronización</h2>
        </header>

        <form class="form" onSubmit={(e) => this.startSync(e)}>
          <ion-select
            placeholder="Canal origen…"
            value={this.newSource}
            onIonChange={(e: any) => (this.newSource = e.target.value)}
          >
            {this.channels.map((c) => (
              <ion-select-option value={c.id} key={c.id}>
                {c.code}
              </ion-select-option>
            ))}
          </ion-select>
          <ion-select
            placeholder="Canal destino…"
            value={this.newTarget}
            onIonChange={(e: any) => (this.newTarget = e.target.value)}
          >
            {this.channels.map((c) => (
              <ion-select-option value={c.id} key={c.id}>
                {c.code}
              </ion-select-option>
            ))}
          </ion-select>
          <ion-button
            type="submit"
            size="small"
            disabled={this.saving || !this.newSource || !this.newTarget || this.newSource === this.newTarget}
          >
            {this.saving ? 'Arrancando…' : 'Nuevo run'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.runs as unknown as Record<string, unknown>[]}
          searchKeys={['run_number', 'status']}
          searchPlaceholder="Buscar nº de run o estado…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin runs de sincronización.'}
        />
      </div>
    );
  }
}
