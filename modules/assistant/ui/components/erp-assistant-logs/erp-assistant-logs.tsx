import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `assistant` (Stencil): log de acciones ejecutadas por
// el asistente (auditoría). Lista vía erplora.query y permite cancelar acciones
// pendientes de confirmación vía erplora.command. El WC NUNCA toca la BD.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface ActionLog {
  id: string;
  conversation_id: string | null;
  tool_name: string;
  tool_args: string;
  result: string;
  success: number;
  confirmed: number;
  error_message: string;
  created_at: string;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-assistant-logs',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpAssistantLogs {
  @State() logs: ActionLog[] = [];
  @State() loading = true;
  @State() error = '';
  @State() busyId = '';

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'tool_name', header: 'Herramienta' },
    {
      key: 'confirmed',
      header: 'Estado',
      format: (r) =>
        (r.confirmed as number) ? ((r.success as number) ? 'OK' : 'Error') : 'Pendiente',
    },
    { key: 'error_message', header: 'Detalle' },
    { key: 'created_at', header: 'Fecha' },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('assistant.action.confirmed', () => this.refresh());
      const off2 = erplora().on('assistant.action.cancelled', () => this.refresh());
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
      const logs = await erplora().query<ActionLog[]>('assistant.logs.list');
      this.logs = logs ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando el log';
    } finally {
      this.loading = false;
    }
  }

  private async cancel(log: ActionLog) {
    if (log.confirmed) return;
    this.busyId = log.id;
    this.error = '';
    try {
      await erplora().command('assistant.actions.cancel', { log_id: log.id });
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo cancelar la acción';
    } finally {
      this.busyId = '';
    }
  }

  render() {
    const pending = this.logs.filter((l) => !l.confirmed);
    return (
      <div>
        <header>
          <h2>Log de acciones</h2>
        </header>

        {this.error && <p class="err">{this.error}</p>}

        {pending.length > 0 && (
          <ion-list>
            {pending.map((l) => (
              <ion-item key={l.id}>
                <ion-label>{l.tool_name} — pendiente de confirmar</ion-label>
                <ion-button
                  slot="end"
                  size="small"
                  fill="outline"
                  disabled={this.busyId === l.id}
                  onClick={() => this.cancel(l)}
                >
                  {this.busyId === l.id ? '…' : 'Cancelar'}
                </ion-button>
              </ion-item>
            ))}
          </ion-list>
        )}

        <data-table
          columns={this.columns}
          rows={this.logs as unknown as Record<string, unknown>[]}
          searchKeys={['tool_name', 'error_message']}
          searchPlaceholder="Buscar herramienta…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin acciones registradas.'}
        />
      </div>
    );
  }
}
