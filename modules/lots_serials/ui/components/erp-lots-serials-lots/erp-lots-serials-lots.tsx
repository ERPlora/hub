import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `lots_serials` (vista Lots). Mini-app: lista de lotes de
// producción + alta rápida. Es una de las dos piezas que el shell carga vía la entry
// dist/lots_serials.esm.js.
//
// El componente NUNCA toca la BD: llama al SDK (erplora.query/command/on). La alta de
// lote (lots_serials.lots.create) la resuelve un handler WASM (apertura de movimiento
// intake + cantidades) — ver WASM-TODO.md.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface Lot {
  id: string;
  lot_number: string;
  product_ref: string;
  expiry_date: string | null;
  quantity_initial: string;
  quantity_current: string;
  status: string;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-lots-serials-lots',
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
export class ErpLotsSerialsLots {
  @State() lots: Lot[] = [];
  @State() loading = true;
  @State() error = '';
  @State() statusFilter = '';
  @State() newNumber = '';
  @State() newProduct = '';
  @State() newQty = '';
  @State() newExpiry = '';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'lot_number', header: 'Lote' },
    { key: 'product_ref', header: 'Producto' },
    { key: 'quantity_current', header: 'Cant. actual', align: 'right', format: (r) => Number(r.quantity_current).toFixed(3) },
    { key: 'quantity_initial', header: 'Cant. inicial', align: 'right', format: (r) => Number(r.quantity_initial).toFixed(3) },
    { key: 'expiry_date', header: 'Caduca', format: (r) => (r.expiry_date as string) ?? '—' },
    { key: 'status', header: 'Estado' },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('lots_serials.lot.created', () => this.refresh());
      const off2 = erplora().on('lots_serials.movement.recorded', () => this.refresh());
      const off3 = erplora().on('lots_serials.lot.recalled', () => this.refresh());
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
      const lots = await erplora().query<Lot[]>('lots_serials.lots.list', {
        product_ref: '',
        status: this.statusFilter,
      });
      this.lots = lots ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando lotes';
    } finally {
      this.loading = false;
    }
  }

  private async createLot(ev: Event) {
    ev.preventDefault();
    if (!this.newNumber.trim() || !this.newProduct.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('lots_serials.lots.create', {
        lot_number: this.newNumber.trim(),
        product_ref: this.newProduct.trim(),
        quantity_initial: this.newQty.trim() || '0',
        manufactured_date: null,
        expiry_date: this.newExpiry.trim() || null,
        notes: '',
      });
      this.newNumber = '';
      this.newProduct = '';
      this.newQty = '';
      this.newExpiry = '';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear el lote';
    } finally {
      this.saving = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Lotes</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createLot(e)}>
          <ion-input
            placeholder="Nº de lote"
            value={this.newNumber}
            onIonInput={(e: any) => (this.newNumber = e.target.value)}
          />
          <ion-input
            placeholder="Producto (ref)"
            value={this.newProduct}
            onIonInput={(e: any) => (this.newProduct = e.target.value)}
          />
          <ion-input
            type="number"
            step="0.001"
            placeholder="Cant. inicial"
            value={this.newQty}
            onIonInput={(e: any) => (this.newQty = e.target.value)}
          />
          <ion-input
            type="date"
            placeholder="Caducidad"
            value={this.newExpiry}
            onIonInput={(e: any) => (this.newExpiry = e.target.value)}
          />
          <ion-button type="submit" size="small" disabled={this.saving || !this.newNumber || !this.newProduct}>
            {this.saving ? 'Guardando…' : 'Añadir lote'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.lots as unknown as Record<string, unknown>[]}
          searchKeys={['lot_number', 'product_ref']}
          searchPlaceholder="Buscar lote o producto…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin lotes.'}
        />
      </div>
    );
  }
}
