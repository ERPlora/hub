import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild lo
// empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn, DataTableAction } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `stripe` (Stencil). Vista de eventos de webhook: listado
// (con filtros por estado/tipo) + acción "marcar procesado" por fila. Es la segunda
// pieza de `ui.entry` que el shell carga en runtime (modules/stripe/dist/stripe.esm.js).
//
// La ingesta idempotente de eventos vive en WASM; este componente NO toca la BD: llama
// al SDK (erplora.query/command/on). El listado usa el DataTable compartido.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface StripeEvent {
  id: string;
  connection_id: string;
  event_id: string;
  event_type: string;
  occurred_at: string | null;
  processed_at: string | null;
  status: string;
  error_message: string;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-stripe-events',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .filters { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; }
    .filters ion-select { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:9rem; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpStripeEvents {
  @State() events: StripeEvent[] = [];
  @State() loading = true;
  @State() error = '';
  @State() statusFilter = '';

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'event_id', header: 'Event id' },
    { key: 'event_type', header: 'Tipo' },
    { key: 'status', header: 'Estado' },
    { key: 'occurred_at', header: 'Ocurrido', format: (r) => this.fmtDate(r.occurred_at as string | null) },
    { key: 'processed_at', header: 'Procesado', format: (r) => this.fmtDate(r.processed_at as string | null) },
  ];

  private actions: DataTableAction[] = [
    { id: 'mark_processed', label: 'Marcar procesado', icon: 'checkmark-done-outline', color: 'primary' },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('stripe.webhook.received', () => this.refresh());
      const off2 = erplora().on('stripe.webhook.processed', () => this.refresh());
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

  private fmtDate(v: string | null): string {
    if (!v) return '—';
    const d = new Date(v);
    return isNaN(d.getTime()) ? v : d.toLocaleString();
  }

  private async refresh() {
    this.loading = true;
    this.error = '';
    try {
      const events = await erplora().query<StripeEvent[]>('stripe.events.list', {
        connection_id: '',
        status: this.statusFilter,
        event_type: '',
        limit: 100,
      });
      this.events = events ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando eventos';
    } finally {
      this.loading = false;
    }
  }

  private async onStatusChange(value: string) {
    this.statusFilter = value;
    await this.refresh();
  }

  private async onRowAction(ev: CustomEvent<{ actionId: string; row: Record<string, unknown> }>) {
    const { actionId, row } = ev.detail;
    if (actionId !== 'mark_processed') return;
    if (row.status === 'processed') return;
    this.error = '';
    try {
      await erplora().command('stripe.webhooks.mark_processed', { event_id: row.event_id as string });
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo marcar el evento';
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Eventos de webhook</h2>
        </header>

        <div class="filters">
          <ion-select
            placeholder="Todos los estados"
            value={this.statusFilter}
            onIonChange={(e: any) => this.onStatusChange(e.target.value)}
          >
            <ion-select-option value="">Todos</ion-select-option>
            <ion-select-option value="received">Recibido</ion-select-option>
            <ion-select-option value="processing">Procesando</ion-select-option>
            <ion-select-option value="processed">Procesado</ion-select-option>
            <ion-select-option value="failed">Fallido</ion-select-option>
          </ion-select>
        </div>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.events as unknown as Record<string, unknown>[]}
          actions={this.actions}
          searchKeys={['event_id', 'event_type']}
          searchPlaceholder="Buscar id o tipo de evento…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin eventos de webhook.'}
          onRowAction={(e: CustomEvent) => this.onRowAction(e)}
        />
      </div>
    );
  }
}
