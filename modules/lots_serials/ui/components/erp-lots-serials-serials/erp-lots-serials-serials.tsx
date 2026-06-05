import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn, DataTableAction } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `lots_serials` (vista Serial Numbers). Mini-app: lista de
// unidades por nº de serie + alta rápida + marcar vendido. El componente NUNCA toca la
// BD: todo va por el SDK (erplora.query/command/on). El alta y las transiciones de
// estado son comandos SQL declarativos Tier 0 (con guard de estado en el WHERE).

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface SerialRow {
  id: string;
  serial: string;
  product_ref: string;
  status: string;
  current_location_ref: string;
  sold_to_customer: string;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-lots-serials-serials',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .form { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; }
    .form ion-input { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:8rem; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpLotsSerialsSerials {
  @State() serials: SerialRow[] = [];
  @State() loading = true;
  @State() error = '';
  @State() statusFilter = '';
  @State() newSerial = '';
  @State() newProduct = '';
  @State() newLocation = '';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'serial', header: 'Serie' },
    { key: 'product_ref', header: 'Producto' },
    { key: 'status', header: 'Estado' },
    { key: 'current_location_ref', header: 'Ubicación', format: (r) => (r.current_location_ref as string) || '—' },
    { key: 'sold_to_customer', header: 'Cliente', format: (r) => (r.sold_to_customer as string) || '—' },
  ];

  private actions: DataTableAction[] = [{ id: 'sell', label: 'Vender', color: 'primary' }];

  private onRowAction = (ev: CustomEvent<{ actionId: string; row: Record<string, unknown> }>) => {
    if (ev.detail.actionId === 'sell') this.markSold(ev.detail.row as unknown as SerialRow);
  };

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('lots_serials.serial.registered', () => this.refresh());
      const off2 = erplora().on('lots_serials.serial.sold', () => this.refresh());
      const off3 = erplora().on('lots_serials.serial.returned', () => this.refresh());
      this.unsub = () => {
        off1();
        off2();
        off3();
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
      const serials = await erplora().query<SerialRow[]>('lots_serials.serials.list', {
        product_ref: '',
        status: this.statusFilter,
      });
      this.serials = serials ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando números de serie';
    } finally {
      this.loading = false;
    }
  }

  private async registerSerial(ev: Event) {
    ev.preventDefault();
    if (!this.newSerial.trim() || !this.newProduct.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('lots_serials.serials.register', {
        serial: this.newSerial.trim(),
        product_ref: this.newProduct.trim(),
        lot_id: null,
        current_location_ref: this.newLocation.trim(),
        notes: '',
      });
      this.newSerial = '';
      this.newProduct = '';
      this.newLocation = '';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo registrar el número de serie';
    } finally {
      this.saving = false;
    }
  }

  private async markSold(row: SerialRow) {
    const customer = (globalThis as any).prompt?.('Cliente comprador:');
    if (!customer || !customer.trim()) return;
    this.error = '';
    try {
      await erplora().command('lots_serials.serials.mark_sold', {
        serial_id: row.id,
        customer_name: customer.trim(),
      });
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo marcar como vendido';
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Números de serie</h2>
        </header>

        <form class="form" onSubmit={(e) => this.registerSerial(e)}>
          <ion-input
            placeholder="Nº de serie"
            value={this.newSerial}
            onIonInput={(e: any) => (this.newSerial = e.target.value)}
          />
          <ion-input
            placeholder="Producto (ref)"
            value={this.newProduct}
            onIonInput={(e: any) => (this.newProduct = e.target.value)}
          />
          <ion-input
            placeholder="Ubicación"
            value={this.newLocation}
            onIonInput={(e: any) => (this.newLocation = e.target.value)}
          />
          <ion-button type="submit" size="small" disabled={this.saving || !this.newSerial || !this.newProduct}>
            {this.saving ? 'Guardando…' : 'Registrar'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.serials as unknown as Record<string, unknown>[]}
          searchKeys={['serial', 'product_ref']}
          searchPlaceholder="Buscar serie o producto…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin números de serie.'}
          actions={this.actions}
          onRowAction={this.onRowAction}
        />
      </div>
    );
  }
}
