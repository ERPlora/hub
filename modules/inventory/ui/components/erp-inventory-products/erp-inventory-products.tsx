import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `inventory` (Stencil). Mini-app: lista de productos +
// búsqueda + alta rápida + indicador de stock bajo. Es la pieza `ui.entry` que el
// shell carga en runtime (modules/inventory/dist/inventory.esm.js).
//
// 90% de la lógica vive en Rust: este componente NO toca la BD; llama al SDK
// (erplora.query/command/on). Toda escritura la valida y ejecuta el runtime.
// El cliente se obtiene de `globalThis.erplora` (lo monta el shell en el boot,
// eligiendo HttpWsTransport en cloud o IpcTransport en Tauri).
// El listado usa el DataTable compartido + Ionic.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface Product {
  id: string;
  name: string;
  sku: string;
  price: number;
  stock: number;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-inventory-products',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ion-text-color, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .form { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; }
    .form ion-input { --background:var(--surface-2,#f7f4ec); border:1px solid var(--ion-border-color,#e0ddd4); border-radius:8px; flex:1; min-width:7rem; }
    .err { color:#d9480f; font-weight:600; }
    .low { color:#d9480f; font-weight:600; }
  `,
})
export class ErpInventoryProducts {
  @State() products: Product[] = [];
  @State() loading = true;
  @State() error = '';
  @State() newName = '';
  @State() newSku = '';
  @State() newPrice = '';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'name', header: 'Nombre' },
    { key: 'sku', header: 'SKU' },
    { key: 'price', header: 'Precio', align: 'right', format: (r) => Number(r.price).toFixed(2) },
    { key: 'stock', header: 'Stock', align: 'right' },
  ];

  async componentWillLoad() {
    await this.refresh();
    // Reactividad: cuando el runtime emite que cambió el stock o se creó un
    // producto, recargamos la lista (eventos de dominio vía SDK/WS).
    try {
      const off1 = erplora().on('inventory.stock_changed', () => this.refresh());
      const off2 = erplora().on('inventory.product.created', () => this.refresh());
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
      const rows = await erplora().query<Product[]>('inventory.products.list');
      this.products = rows ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando productos';
    } finally {
      this.loading = false;
    }
  }

  private async createProduct(ev: Event) {
    ev.preventDefault();
    if (!this.newName.trim() || !this.newSku.trim()) return;
    this.saving = true;
    try {
      await erplora().command('inventory.products.create', {
        name: this.newName.trim(),
        sku: this.newSku.trim(),
        price: Number(this.newPrice) || 0,
        cost: 0,
        stock: 0,
        low_stock_threshold: 10,
        product_type: 'physical',
        ean13: null,
        description: '',
        tax_class_id: null,
        image: '',
      });
      this.newName = '';
      this.newSku = '';
      this.newPrice = '';
      await this.refresh(); // (además del evento; garantiza refresco inmediato)
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear';
    } finally {
      this.saving = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Productos</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createProduct(e)}>
          <ion-input
            placeholder="Nombre"
            value={this.newName}
            onIonInput={(e: any) => (this.newName = e.target.value)}
          />
          <ion-input
            placeholder="SKU"
            value={this.newSku}
            onIonInput={(e: any) => (this.newSku = e.target.value)}
          />
          <ion-input
            type="number"
            step="0.01"
            placeholder="Precio"
            value={this.newPrice}
            onIonInput={(e: any) => (this.newPrice = e.target.value)}
          />
          <ion-button type="submit" size="small" disabled={this.saving || !this.newName || !this.newSku}>
            {this.saving ? 'Guardando…' : 'Añadir'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.products as unknown as Record<string, unknown>[]}
          searchKeys={['name', 'sku']}
          searchPlaceholder="Buscar nombre o SKU…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin productos.'}
        />
      </div>
    );
  }
}
