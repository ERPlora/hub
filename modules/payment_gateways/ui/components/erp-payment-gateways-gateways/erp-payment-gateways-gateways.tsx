import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `payment_gateways` (Stencil). Mini-app: lista de pasarelas
// configuradas + alta rápida de una pasarela. Es la pieza `ui.entry` que el shell carga
// en runtime (modules/payment_gateways/dist/payment_gateways.esm.js).
//
// El grueso de la lógica de pagos (mintado atómico de referencias, máquina de estados de
// transacciones, reembolsos parciales, resumen agregado) vive en Rust/WASM: este componente
// NO toca la BD; llama al SDK (erplora.query/command/on). Toda escritura la valida y ejecuta
// el runtime. El cliente se obtiene de `globalThis.erplora` (lo monta el shell en el boot).
// El listado usa el DataTable compartido + Ionic.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface Gateway {
  id: string;
  code: string;
  name: string;
  provider: string;
  is_active: number;
  is_test_mode: number;
  supports_refunds: number;
}

const PROVIDERS = ['stripe', 'redsys', 'paypal', 'manual', 'other'];

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-payment-gateways-gateways',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ion-text-color, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .form { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; }
    .form ion-input, .form ion-select { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:8rem; }
    .err { color:#d9480f; font-weight:600; }
    .badge { font-size:.7rem; padding:.1rem .4rem; border-radius:6px; background:#eef6fb; color:#1496d6; }
    .test { background:#fff4e6; color:#d9480f; }
  `,
})
export class ErpPaymentGatewaysGateways {
  @State() gateways: Gateway[] = [];
  @State() loading = true;
  @State() error = '';
  @State() newCode = '';
  @State() newName = '';
  @State() newProvider = 'manual';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'code', header: 'Código' },
    { key: 'name', header: 'Nombre' },
    { key: 'provider', header: 'Proveedor' },
    { key: 'is_test_mode', header: 'Modo', format: (r) => (r.is_test_mode ? 'test' : 'live') },
    { key: 'supports_refunds', header: 'Reembolsos', format: (r) => (r.supports_refunds ? 'Sí' : 'No') },
  ];

  async componentWillLoad() {
    await this.refresh();
    // Reactividad: recargamos la lista cuando el runtime emite que se creó una pasarela.
    try {
      this.unsub = erplora().on('payment_gateways.gateway.created', () => this.refresh());
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
      const rows = await erplora().query<Gateway[]>('payment_gateways.gateways.list');
      this.gateways = rows ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando pasarelas';
    } finally {
      this.loading = false;
    }
  }

  private async createGateway(ev: Event) {
    ev.preventDefault();
    if (!this.newCode.trim() || !this.newName.trim()) return;
    this.saving = true;
    try {
      await erplora().command('payment_gateways.gateways.create', {
        code: this.newCode.trim(),
        name: this.newName.trim(),
        provider: this.newProvider,
        is_test_mode: 1,
        config: '{}',
        supports_refunds: 1,
        supported_currencies: '[]',
      });
      this.newCode = '';
      this.newName = '';
      this.newProvider = 'manual';
      await this.refresh(); // (además del evento; garantiza refresco inmediato)
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear la pasarela';
    } finally {
      this.saving = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Pasarelas de pago</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createGateway(e)}>
          <ion-input
            placeholder="Código (p.ej. stripe_main)"
            value={this.newCode}
            onIonInput={(e: any) => (this.newCode = e.target.value)}
          />
          <ion-input
            placeholder="Nombre"
            value={this.newName}
            onIonInput={(e: any) => (this.newName = e.target.value)}
          />
          <ion-select
            placeholder="Proveedor…"
            value={this.newProvider}
            onIonChange={(e: any) => (this.newProvider = e.target.value)}
          >
            {PROVIDERS.map((p) => (
              <ion-select-option value={p} key={p}>
                {p}
              </ion-select-option>
            ))}
          </ion-select>
          <ion-button type="submit" size="small" disabled={this.saving || !this.newCode || !this.newName}>
            {this.saving ? 'Guardando…' : 'Añadir'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.gateways as unknown as Record<string, unknown>[]}
          searchKeys={['code', 'name', 'provider']}
          searchPlaceholder="Buscar código, nombre o proveedor…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin pasarelas configuradas.'}
        />
      </div>
    );
  }
}
