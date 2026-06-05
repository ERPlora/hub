import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `stock_sync` (Stencil). Mini-app: cola de conflictos de
// stock (divergencias de cantidad entre canales) + acción de resolución por estrategia.
// La transición de estado y las guardas viven en el handler WASM (resolve_conflict);
// este componente NO toca la BD: llama al SDK (erplora.query/command/on).

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface Conflict {
  id: string;
  product_ref: string;
  source_channel_id: string;
  target_channel_id: string;
  source_quantity: string;
  target_quantity: string;
  detected_at: string | null;
  status: string;
  resolution_strategy: string;
  resolved_at: string | null;
}

interface Channel {
  id: string;
  code: string;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-stock-sync-conflicts',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .filters { display:flex; gap:.5rem; align-items:center; margin:.25rem 0 1rem; }
    .filters ion-select { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:9rem; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpStockSyncConflicts {
  @State() conflicts: Conflict[] = [];
  @State() channels: Channel[] = [];
  @State() loading = true;
  @State() error = '';
  @State() statusFilter = 'open';
  @State() busyId = '';

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'product_ref', header: 'Producto' },
    { key: 'source_channel_id', header: 'Origen', format: (r) => this.chCode(r.source_channel_id as string) },
    { key: 'target_channel_id', header: 'Destino', format: (r) => this.chCode(r.target_channel_id as string) },
    { key: 'source_quantity', header: 'Qty origen', align: 'right' },
    { key: 'target_quantity', header: 'Qty destino', align: 'right' },
    { key: 'status', header: 'Estado' },
    {
      key: 'id',
      header: 'Acción',
      format: (r) =>
        (r.status as string) === 'open'
          ? `resolver: usar origen / usar destino`
          : (r.resolution_strategy as string) || '—',
    },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('stock_sync.conflict.detected', () => this.refresh());
      const off2 = erplora().on('stock_sync.conflict.resolved', () => this.refresh());
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
      const [conflicts, channels] = await Promise.all([
        erplora().query<Conflict[]>('stock_sync.conflicts.list', {
          status: this.statusFilter,
          channel_id: '',
          limit: 100,
        }),
        erplora().query<Channel[]>('stock_sync.channels.list', { active_only: 0 }),
      ]);
      this.conflicts = conflicts ?? [];
      this.channels = channels ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando conflictos';
    } finally {
      this.loading = false;
    }
  }

  private async resolve(conflictId: string, strategy: string) {
    this.busyId = conflictId;
    this.error = '';
    try {
      await erplora().command('stock_sync.conflicts.resolve', {
        conflict_id: conflictId,
        strategy,
      });
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo resolver el conflicto';
    } finally {
      this.busyId = '';
    }
  }

  private chCode(id: string): string {
    return this.channels.find((c) => c.id === id)?.code ?? '—';
  }

  render() {
    return (
      <div>
        <header>
          <h2>Conflictos de stock</h2>
        </header>

        <div class="filters">
          <ion-select
            value={this.statusFilter}
            onIonChange={(e: any) => {
              this.statusFilter = e.target.value;
              this.refresh();
            }}
          >
            <ion-select-option value="open">Abiertos</ion-select-option>
            <ion-select-option value="resolved">Resueltos</ion-select-option>
            <ion-select-option value="ignored">Ignorados</ion-select-option>
          </ion-select>
        </div>

        {this.error && <p class="err">{this.error}</p>}

        {this.statusFilter === 'open' && (
          <div>
            {this.conflicts.map((c) => (
              <div key={c.id} style={{ display: 'flex', gap: '.5rem', alignItems: 'center', margin: '.25rem 0' }}>
                <span style={{ flex: '1' }}>
                  {c.product_ref}: {c.source_quantity} → {c.target_quantity}
                </span>
                <ion-button size="small" disabled={this.busyId === c.id} onClick={() => this.resolve(c.id, 'use_source')}>
                  Usar origen
                </ion-button>
                <ion-button
                  size="small"
                  fill="outline"
                  disabled={this.busyId === c.id}
                  onClick={() => this.resolve(c.id, 'use_target')}
                >
                  Usar destino
                </ion-button>
                <ion-button
                  size="small"
                  color="medium"
                  fill="clear"
                  disabled={this.busyId === c.id}
                  onClick={() => this.resolve(c.id, 'ignore')}
                >
                  Ignorar
                </ion-button>
              </div>
            ))}
          </div>
        )}

        <data-table
          columns={this.columns}
          rows={this.conflicts as unknown as Record<string, unknown>[]}
          searchKeys={['product_ref', 'status']}
          searchPlaceholder="Buscar producto o estado…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin conflictos.'}
        />
      </div>
    );
  }
}
