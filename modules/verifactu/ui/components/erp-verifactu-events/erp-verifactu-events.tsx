import { Component, State, h } from '@stencil/core';
// DataTable compartido (efecto secundario: auto-registro + bundling).
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `verifactu`: log de auditoría / eventos (append-only).
// Solo lectura: transmisiones, errores, reintentos, cambios de config. El WC NO toca la BD.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface VerifactuEvent {
  id: string;
  record_id: string | null;
  event_type: string;
  severity: string;
  message: string;
  timestamp: string;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-verifactu-events',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .filters { display:flex; gap:.5rem; flex-wrap:wrap; margin:.5rem 0 1rem; }
    .filters ion-select { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:10rem; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpVerifactuEvents {
  @State() events: VerifactuEvent[] = [];
  @State() loading = true;
  @State() error = '';
  @State() severity = '';

  private columns: DataTableColumn[] = [
    { key: 'timestamp', header: 'Cuándo' },
    { key: 'severity', header: 'Severidad' },
    { key: 'event_type', header: 'Tipo' },
    { key: 'message', header: 'Mensaje' },
  ];

  async componentWillLoad() {
    await this.refresh();
  }

  private async refresh() {
    this.loading = true;
    this.error = '';
    try {
      const rows = await erplora().query<VerifactuEvent[]>('verifactu.events.list', {
        event_type: '',
        severity: this.severity,
        limit: 100,
      });
      this.events = rows ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando eventos';
    } finally {
      this.loading = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Eventos de auditoría</h2>
        </header>

        <div class="filters">
          <ion-select
            placeholder="Severidad…"
            value={this.severity}
            onIonChange={(e: any) => {
              this.severity = e.target.value;
              this.refresh();
            }}
          >
            <ion-select-option value="">Todas</ion-select-option>
            <ion-select-option value="debug">Debug</ion-select-option>
            <ion-select-option value="info">Info</ion-select-option>
            <ion-select-option value="warning">Aviso</ion-select-option>
            <ion-select-option value="error">Error</ion-select-option>
            <ion-select-option value="critical">Crítico</ion-select-option>
          </ion-select>
        </div>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.events as unknown as Record<string, unknown>[]}
          searchKeys={['event_type', 'message']}
          searchPlaceholder="Buscar tipo o mensaje…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin eventos.'}
        />
      </div>
    );
  }
}
