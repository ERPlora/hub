import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `courier_integrations` (Stencil). Vista de logs:
// auditoría de llamadas a las APIs de transportista, más reciente primero,
// con filtros por estado y tipo de llamada. Solo lectura — el WC nunca toca la BD.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface APICall {
  id: string;
  connection_id: string;
  call_number: string;
  call_type: string;
  status_code: number | null;
  status: string;
  called_at: string;
  response_time_ms: number;
  error_message: string;
}

const STATUSES = ['', 'success', 'failed', 'timeout'];
const CALL_TYPES = ['', 'create_shipment', 'get_label', 'track_shipment', 'cancel_shipment', 'get_rate'];

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-courier-integrations-logs',
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
export class ErpCourierIntegrationsLogs {
  @State() calls: APICall[] = [];
  @State() loading = true;
  @State() error = '';
  @State() statusFilter = '';
  @State() callTypeFilter = '';

  private columns: DataTableColumn[] = [
    { key: 'call_number', header: 'Nº llamada' },
    { key: 'call_type', header: 'Tipo' },
    { key: 'status', header: 'Estado' },
    { key: 'status_code', header: 'Código', align: 'right', format: (r) => (r.status_code != null ? String(r.status_code) : '—') },
    { key: 'response_time_ms', header: 'ms', align: 'right', format: (r) => String(r.response_time_ms ?? 0) },
    { key: 'called_at', header: 'Fecha' },
  ];

  async componentWillLoad() {
    await this.refresh();
  }

  private async refresh() {
    this.loading = true;
    this.error = '';
    try {
      const rows = await erplora().query<APICall[]>('courier_integrations.calls.list', {
        connection_id: '',
        status: this.statusFilter,
        call_type: this.callTypeFilter,
        limit: 100,
      });
      this.calls = rows ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando el log de llamadas';
    } finally {
      this.loading = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Log de llamadas a la API</h2>
        </header>

        <div class="form">
          <ion-select
            placeholder="Estado…"
            value={this.statusFilter}
            onIonChange={(e: any) => {
              this.statusFilter = e.target.value;
              this.refresh();
            }}
          >
            {STATUSES.map((s) => (
              <ion-select-option value={s} key={s || 'all'}>
                {s || 'Todos los estados'}
              </ion-select-option>
            ))}
          </ion-select>
          <ion-select
            placeholder="Tipo…"
            value={this.callTypeFilter}
            onIonChange={(e: any) => {
              this.callTypeFilter = e.target.value;
              this.refresh();
            }}
          >
            {CALL_TYPES.map((t) => (
              <ion-select-option value={t} key={t || 'all'}>
                {t || 'Todos los tipos'}
              </ion-select-option>
            ))}
          </ion-select>
        </div>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.calls as unknown as Record<string, unknown>[]}
          searchKeys={['call_number', 'call_type', 'status']}
          searchPlaceholder="Buscar nº de llamada o tipo…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin llamadas registradas.'}
        />
      </div>
    );
  }
}
