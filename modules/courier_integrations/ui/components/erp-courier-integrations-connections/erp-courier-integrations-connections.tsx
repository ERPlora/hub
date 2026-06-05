import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `courier_integrations` (Stencil). Vista de conexiones:
// lista las conexiones a APIs de transportistas + alta rápida + desactivación.
// Es una de las piezas `ui.entry` que el shell carga en runtime.
//
// El WC NUNCA toca la BD: solo llama al SDK (erplora.query/command/on). La lógica
// de simulación de carrier, secuenciador de nº de llamada y métricas vive en WASM.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface CourierConnection {
  id: string;
  courier_code: string;
  name: string;
  api_endpoint: string;
  account_number: string;
  environment: string;
  is_active: number;
  last_call_at: string | null;
  last_call_status: string;
}

const COURIER_CODES = ['seur', 'mrw', 'gls', 'dhl', 'ups', 'correos', 'nacex'];

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-courier-integrations-connections',
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
export class ErpCourierIntegrationsConnections {
  @State() connections: CourierConnection[] = [];
  @State() loading = true;
  @State() error = '';
  @State() activeOnly = true;
  @State() newCourier = '';
  @State() newName = '';
  @State() newEndpoint = '';
  @State() newEnv = 'test';
  @State() saving = false;
  @State() deactivateId = '';

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'courier_code', header: 'Transportista', format: (r) => String(r.courier_code).toUpperCase() },
    { key: 'name', header: 'Nombre' },
    { key: 'environment', header: 'Entorno' },
    { key: 'is_active', header: 'Activa', format: (r) => (r.is_active ? 'Sí' : 'No') },
    { key: 'last_call_status', header: 'Última llamada', format: (r) => (r.last_call_status as string) || '—' },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('courier_integrations.connection.created', () => this.refresh());
      const off2 = erplora().on('courier_integrations.connection.deactivated', () => this.refresh());
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
      const rows = await erplora().query<CourierConnection[]>('courier_integrations.connections.list', {
        active_only: this.activeOnly ? 1 : 0,
        courier_code: '',
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
    if (!this.newCourier || !this.newName.trim() || !this.newEndpoint.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('courier_integrations.connections.create', {
        courier_code: this.newCourier,
        name: this.newName.trim(),
        api_endpoint: this.newEndpoint.trim(),
        account_number: '',
        environment: this.newEnv,
      });
      this.newCourier = '';
      this.newName = '';
      this.newEndpoint = '';
      this.newEnv = 'test';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear la conexión';
    } finally {
      this.saving = false;
    }
  }

  private async deactivate() {
    if (!this.deactivateId) return;
    this.error = '';
    try {
      await erplora().command('courier_integrations.connections.deactivate', {
        connection_id: this.deactivateId,
      });
      this.deactivateId = '';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo desactivar la conexión';
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Conexiones de transportista</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createConnection(e)}>
          <ion-select
            placeholder="Transportista…"
            value={this.newCourier}
            onIonChange={(e: any) => (this.newCourier = e.target.value)}
          >
            {COURIER_CODES.map((c) => (
              <ion-select-option value={c} key={c}>
                {c.toUpperCase()}
              </ion-select-option>
            ))}
          </ion-select>
          <ion-input
            placeholder="Nombre"
            value={this.newName}
            onIonInput={(e: any) => (this.newName = e.target.value)}
          />
          <ion-input
            placeholder="API endpoint (https://…)"
            value={this.newEndpoint}
            onIonInput={(e: any) => (this.newEndpoint = e.target.value)}
          />
          <ion-select
            placeholder="Entorno…"
            value={this.newEnv}
            onIonChange={(e: any) => (this.newEnv = e.target.value)}
          >
            <ion-select-option value="test">test</ion-select-option>
            <ion-select-option value="production">production</ion-select-option>
          </ion-select>
          <ion-button
            type="submit"
            size="small"
            disabled={this.saving || !this.newCourier || !this.newName || !this.newEndpoint}
          >
            {this.saving ? 'Guardando…' : 'Añadir'}
          </ion-button>
        </form>

        <div class="form">
          <ion-select
            placeholder="Desactivar conexión…"
            value={this.deactivateId}
            onIonChange={(e: any) => (this.deactivateId = e.target.value)}
          >
            {this.connections
              .filter((c) => c.is_active)
              .map((c) => (
                <ion-select-option value={c.id} key={c.id}>
                  {c.courier_code.toUpperCase()} — {c.name}
                </ion-select-option>
              ))}
          </ion-select>
          <ion-button size="small" color="danger" disabled={!this.deactivateId} onClick={() => this.deactivate()}>
            Desactivar
          </ion-button>
        </div>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.connections as unknown as Record<string, unknown>[]}
          searchKeys={['courier_code', 'name', 'environment']}
          searchPlaceholder="Buscar transportista o nombre…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin conexiones configuradas.'}
        />
      </div>
    );
  }
}
