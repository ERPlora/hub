import { Component, State, h } from '@stencil/core';

// Web Component del módulo `inventory` (Stencil). Mini-app: lista de productos +
// búsqueda + alta rápida + indicador de stock bajo. Es la pieza `ui.entry` que el
// shell carga en runtime (modules/inventory/dist/inventory.esm.js).
//
// 90% de la lógica vive en Rust: este componente NO toca la BD; llama al SDK
// (erplora.query/command/on). Toda escritura la valida y ejecuta el runtime.
// El cliente se obtiene de `globalThis.erplora` (lo monta el shell en el boot,
// eligiendo HttpWsTransport en cloud o IpcTransport en Tauri).

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
    input { padding:.45rem .6rem; border:1px solid var(--ion-border-color,#e0ddd4); border-radius:8px; font-size:.9rem; }
    button { padding:.45rem .8rem; border:0; border-radius:8px; background:#1496d6; color:#fff; font-size:.85rem; cursor:pointer; }
    button:disabled { opacity:.5; cursor:not-allowed; }
    table { width:100%; border-collapse:collapse; font-size:.9rem; }
    th { text-align:left; color:#8b897f; font-weight:600; padding:.5rem .6rem; border-bottom:1px solid #e7e2d6; }
    td { padding:.55rem .6rem; border-bottom:1px solid #f1ede4; }
    .low { color:#d9480f; font-weight:600; }
    .muted { color:#8b897f; font-size:.85rem; }
    .form { display:flex; gap:.4rem; flex-wrap:wrap; margin:.5rem 0 1rem; }
    .form input { flex:1; min-width:7rem; }
  `,
})
export class ErpInventoryProducts {
  @State() products: Product[] = [];
  @State() loading = true;
  @State() error = '';
  @State() search = '';
  @State() newName = '';
  @State() newSku = '';
  @State() newPrice = '';
  @State() saving = false;

  private unsub?: () => void;

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

  private get filtered(): Product[] {
    const q = this.search.trim().toLowerCase();
    if (!q) return this.products;
    return this.products.filter(
      (p) => p.name.toLowerCase().includes(q) || p.sku.toLowerCase().includes(q),
    );
  }

  render() {
    return (
      <div>
        <header>
          <h2>Productos</h2>
          <input
            type="search"
            placeholder="Buscar nombre o SKU…"
            value={this.search}
            onInput={(e) => (this.search = (e.target as HTMLInputElement).value)}
          />
        </header>

        <form class="form" onSubmit={(e) => this.createProduct(e)}>
          <input
            placeholder="Nombre"
            value={this.newName}
            onInput={(e) => (this.newName = (e.target as HTMLInputElement).value)}
          />
          <input
            placeholder="SKU"
            value={this.newSku}
            onInput={(e) => (this.newSku = (e.target as HTMLInputElement).value)}
          />
          <input
            placeholder="Precio"
            type="number"
            step="0.01"
            value={this.newPrice}
            onInput={(e) => (this.newPrice = (e.target as HTMLInputElement).value)}
          />
          <button type="submit" disabled={this.saving || !this.newName || !this.newSku}>
            {this.saving ? 'Guardando…' : 'Añadir'}
          </button>
        </form>

        {this.error && <p class="low">{this.error}</p>}
        {this.loading ? (
          <p class="muted">Cargando…</p>
        ) : this.filtered.length === 0 ? (
          <p class="muted">Sin productos.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Nombre</th>
                <th>SKU</th>
                <th>Precio</th>
                <th>Stock</th>
              </tr>
            </thead>
            <tbody>
              {this.filtered.map((p) => (
                <tr key={p.id}>
                  <td>{p.name}</td>
                  <td>{p.sku}</td>
                  <td>{Number(p.price).toFixed(2)}</td>
                  <td class={p.stock <= 0 ? 'low' : ''}>{p.stock}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    );
  }
}
