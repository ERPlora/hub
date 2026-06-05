import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn, DataTableAction } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `online_store` (Stencil). Vista: catálogo del escaparate
// (fichas de producto publicables) + alta rápida. Es una de las piezas `ui.entry` que
// el shell carga en runtime (modules/online_store/dist/online_store.esm.js).
//
// El componente NO toca la BD: llama al SDK (erplora.query/command/on). El listado usa
// el DataTable compartido + Ionic. Acciones por fila (publicar/ocultar/borrar) → rowAction.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface StoreProduct {
  id: string;
  product_ref: string;
  slug: string;
  name: string;
  price: string;
  stock_quantity: number;
  is_published: number;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-online-store-products',
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
export class ErpOnlineStoreProducts {
  @State() products: StoreProduct[] = [];
  @State() loading = true;
  @State() error = '';
  @State() newName = '';
  @State() newSlug = '';
  @State() newPrice = '';
  @State() newStock = '';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'name', header: 'Nombre' },
    { key: 'slug', header: 'Slug' },
    { key: 'price', header: 'Precio', align: 'right', format: (r) => Number(r.price).toFixed(2) },
    { key: 'stock_quantity', header: 'Stock', align: 'right' },
    { key: 'is_published', header: 'Estado', format: (r) => (Number(r.is_published) ? 'Publicado' : 'Borrador') },
  ];

  private actions: DataTableAction[] = [
    { id: 'publish', label: 'Publicar', icon: 'eye-outline', color: 'success' },
    { id: 'unpublish', label: 'Ocultar', icon: 'eye-off-outline', color: 'medium' },
    { id: 'delete', label: 'Borrar', icon: 'trash-outline', color: 'danger' },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const offs = [
        erplora().on('online_store.product.created', () => this.refresh()),
        erplora().on('online_store.product.published', () => this.refresh()),
        erplora().on('online_store.product.unpublished', () => this.refresh()),
        erplora().on('online_store.product.deleted', () => this.refresh()),
      ];
      this.unsub = () => offs.forEach((o) => o());
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
      const products = await erplora().query<StoreProduct[]>('online_store.products.list', {
        is_published: -1,
        search: '',
      });
      this.products = products ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando productos';
    } finally {
      this.loading = false;
    }
  }

  private async createProduct(ev: Event) {
    ev.preventDefault();
    if (!this.newName.trim() || !this.newSlug.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('online_store.products.create', {
        product_ref: '',
        name: this.newName.trim(),
        slug: this.newSlug.trim(),
        price: Number(this.newPrice) || 0,
        stock_quantity: Number(this.newStock) || 0,
        description: '',
      });
      this.newName = '';
      this.newSlug = '';
      this.newPrice = '';
      this.newStock = '';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear el producto';
    } finally {
      this.saving = false;
    }
  }

  private async onRowAction(ev: CustomEvent<{ actionId: string; row: Record<string, unknown> }>) {
    const { actionId, row } = ev.detail;
    const productId = String(row.id);
    this.error = '';
    try {
      if (actionId === 'publish') {
        await erplora().command('online_store.products.publish', { product_id: productId });
      } else if (actionId === 'unpublish') {
        await erplora().command('online_store.products.unpublish', { product_id: productId });
      } else if (actionId === 'delete') {
        await erplora().command('online_store.products.delete', { product_id: productId });
      }
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo completar la acción';
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Catálogo del escaparate</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createProduct(e)}>
          <ion-input
            placeholder="Nombre"
            value={this.newName}
            onIonInput={(e: any) => (this.newName = e.target.value)}
          />
          <ion-input
            placeholder="Slug (camiseta-azul)"
            value={this.newSlug}
            onIonInput={(e: any) => (this.newSlug = e.target.value)}
          />
          <ion-input
            type="number"
            step="0.01"
            placeholder="Precio"
            value={this.newPrice}
            onIonInput={(e: any) => (this.newPrice = e.target.value)}
          />
          <ion-input
            type="number"
            step="1"
            placeholder="Stock"
            value={this.newStock}
            onIonInput={(e: any) => (this.newStock = e.target.value)}
          />
          <ion-button type="submit" size="small" disabled={this.saving || !this.newName || !this.newSlug}>
            {this.saving ? 'Guardando…' : 'Añadir'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.products as unknown as Record<string, unknown>[]}
          searchKeys={['name', 'slug']}
          searchPlaceholder="Buscar nombre o slug…"
          actions={this.actions}
          onRowAction={(e: CustomEvent<{ actionId: string; row: Record<string, unknown> }>) => this.onRowAction(e)}
          emptyMessage={this.loading ? 'Cargando…' : 'Sin productos en el escaparate.'}
        />
      </div>
    );
  }
}
