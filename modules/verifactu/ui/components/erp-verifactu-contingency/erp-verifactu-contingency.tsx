import { Component, State, h } from '@stencil/core';
// DataTable compartido (efecto secundario: auto-registro + bundling).
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `verifactu`: cola de contingencia (registros pendientes
// de transmisión cuando la AEAT no está disponible). Lista + acciones de reintento
// y cancelación vía erplora.command. El WC NO toca la BD.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface ContingencyEntry {
  id: string;
  record_id: string;
  priority: number;
  queued_at: string;
  attempts: number;
  last_error: string;
  next_attempt_at: string | null;
  status: string;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-verifactu-contingency',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .err { color:#d9480f; font-weight:600; }
    .actions { display:flex; gap:.35rem; }
  `,
})
export class ErpVerifactuContingency {
  @State() entries: ContingencyEntry[] = [];
  @State() loading = true;
  @State() error = '';
  @State() busy = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'record_id', header: 'Registro' },
    { key: 'priority', header: 'Prioridad', align: 'right' },
    { key: 'attempts', header: 'Intentos', align: 'right' },
    { key: 'status', header: 'Estado' },
    { key: 'next_attempt_at', header: 'Próximo intento', format: (r) => (r.next_attempt_at as string) ?? '—' },
    { key: 'last_error', header: 'Último error', format: (r) => ((r.last_error as string) || '').slice(0, 80) },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('verifactu.contingency.retried', () => this.refresh());
      const off2 = erplora().on('verifactu.contingency.cancelled', () => this.refresh());
      const off3 = erplora().on('verifactu.contingency.processed', () => this.refresh());
      this.unsub = () => {
        off1();
        off2();
        off3();
      };
    } catch {
      /* sin SDK (preview) */
    }
  }

  disconnectedCallback() {
    this.unsub?.();
  }

  private async refresh() {
    this.loading = true;
    this.error = '';
    try {
      const rows = await erplora().query<ContingencyEntry[]>('verifactu.contingency.list', {
        status: '',
        limit: 50,
      });
      this.entries = rows ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando la cola de contingencia';
    } finally {
      this.loading = false;
    }
  }

  private async processQueue() {
    this.busy = true;
    this.error = '';
    try {
      await erplora().command('verifactu.contingency.process', { limit: 100 });
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo procesar la cola';
    } finally {
      this.busy = false;
    }
  }

  private async retry(queueId: string) {
    this.busy = true;
    this.error = '';
    try {
      await erplora().command('verifactu.contingency.retry', { queue_id: queueId });
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo reencolar';
    } finally {
      this.busy = false;
    }
  }

  private async cancel(queueId: string) {
    this.busy = true;
    this.error = '';
    try {
      await erplora().command('verifactu.contingency.cancel', { queue_id: queueId });
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo cancelar';
    } finally {
      this.busy = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Cola de contingencia</h2>
          <ion-button size="small" disabled={this.busy} onClick={() => this.processQueue()}>
            {this.busy ? 'Procesando…' : 'Procesar cola'}
          </ion-button>
        </header>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.entries as unknown as Record<string, unknown>[]}
          searchKeys={['record_id', 'status']}
          searchPlaceholder="Buscar registro o estado…"
          emptyMessage={this.loading ? 'Cargando…' : 'Cola vacía.'}
          actions={[
            { id: 'retry', label: 'Reintentar' },
            { id: 'cancel', label: 'Cancelar', color: 'danger' },
          ]}
          onRowAction={(e: CustomEvent<{ actionId: string; row: Record<string, unknown> }>) => {
            const { actionId, row } = e.detail;
            if (actionId === 'retry') this.retry(row.id as string);
            else if (actionId === 'cancel') this.cancel(row.id as string);
          }}
        />
      </div>
    );
  }
}
