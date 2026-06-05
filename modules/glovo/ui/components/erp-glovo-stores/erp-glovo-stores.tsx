import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `glovo` (Stencil). Vista de tiendas Glovo Partners:
// listado + alta rápida + cambio de estado operativo. Es parte de la pieza
// `ui.entry` que el shell carga en runtime (modules/glovo/dist/glovo.esm.js).
//
// El componente NO toca la BD: llama al SDK (erplora.query/command/on). Toda la
// lógica (idempotencia, contadores, sync) vive en Rust/WASM.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface GlovoStore {
  id: string;
  store_id: string;
  name: string;
  country: string;
  city: string;
  glovo_status: string;
  is_active: number;
  last_sync_at: string | null;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-glovo-stores',
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
export class ErpGlovoStores {
  @State() stores: GlovoStore[] = [];
  @State() loading = true;
  @State() error = '';
  @State() newStoreId = '';
  @State() newName = '';
  @State() newCountry = 'ES';
  @State() newCity = '';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'name', header: 'Nombre' },
    { key: 'store_id', header: 'ID Glovo' },
    { key: 'country', header: 'País' },
    { key: 'city', header: 'Ciudad' },
    { key: 'glovo_status', header: 'Estado' },
    { key: 'is_active', header: 'Activa', format: (r) => (Number(r.is_active) ? 'Sí' : 'No') },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('glovo.store.created', () => this.refresh());
      const off2 = erplora().on('glovo.store.status_changed', () => this.refresh());
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
      const stores = await erplora().query<GlovoStore[]>('glovo.stores.list', { active_only: '' });
      this.stores = stores ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando tiendas Glovo';
    } finally {
      this.loading = false;
    }
  }

  private async createStore(ev: Event) {
    ev.preventDefault();
    if (!this.newStoreId.trim() || !this.newName.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('glovo.stores.create', {
        store_id: this.newStoreId.trim(),
        name: this.newName.trim(),
        country: this.newCountry.trim().toUpperCase() || 'ES',
        city: this.newCity.trim(),
      });
      this.newStoreId = '';
      this.newName = '';
      this.newCity = '';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear la tienda';
    } finally {
      this.saving = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Tiendas Glovo</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createStore(e)}>
          <ion-input
            placeholder="ID Glovo (store_id)"
            value={this.newStoreId}
            onIonInput={(e: any) => (this.newStoreId = e.target.value)}
          />
          <ion-input
            placeholder="Nombre"
            value={this.newName}
            onIonInput={(e: any) => (this.newName = e.target.value)}
          />
          <ion-input
            placeholder="País (ES)"
            value={this.newCountry}
            onIonInput={(e: any) => (this.newCountry = e.target.value)}
          />
          <ion-input
            placeholder="Ciudad"
            value={this.newCity}
            onIonInput={(e: any) => (this.newCity = e.target.value)}
          />
          <ion-button
            type="submit"
            size="small"
            disabled={this.saving || !this.newStoreId || !this.newName}
          >
            {this.saving ? 'Guardando…' : 'Añadir'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.stores as unknown as Record<string, unknown>[]}
          searchKeys={['name', 'store_id', 'city']}
          searchPlaceholder="Buscar tienda…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin tiendas Glovo.'}
        />
      </div>
    );
  }
}
