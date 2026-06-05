import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`. (4 niveles)
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `uber_eats` (vista restaurants). Mini-app: lista de tiendas
// Uber Eats registradas + alta rápida. Pieza cargada por el shell en runtime.
//
// El WC NUNCA toca la BD: todo va por el SDK (erplora.query/command/on). El listado usa
// el DataTable compartido + Ionic. Rust valida permiso, hub_id y payload.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface UEStore {
  id: string;
  store_id: string;
  name: string;
  status: string;
  country: string;
  currency: string;
  is_active: number;
  last_sync_at: string | null;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-uber-eats-restaurants',
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
export class ErpUberEatsRestaurants {
  @State() stores: UEStore[] = [];
  @State() loading = true;
  @State() error = '';
  @State() saving = false;
  @State() newStoreId = '';
  @State() newName = '';
  @State() newCountry = 'ES';

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'name', header: 'Restaurante' },
    { key: 'store_id', header: 'ID Uber' },
    { key: 'status', header: 'Estado' },
    { key: 'country', header: 'País' },
    { key: 'currency', header: 'Moneda' },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('uber_eats.store.created', () => this.refresh());
      const off2 = erplora().on('uber_eats.store.status_changed', () => this.refresh());
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
      const stores = await erplora().query<UEStore[]>('uber_eats.stores.list', { active_only: '1' });
      this.stores = stores ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando restaurantes';
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
      await erplora().command('uber_eats.stores.create', {
        store_id: this.newStoreId.trim(),
        name: this.newName.trim(),
        country: this.newCountry.trim().toUpperCase() || 'ES',
        currency: 'EUR',
      });
      this.newStoreId = '';
      this.newName = '';
      this.newCountry = 'ES';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo registrar el restaurante';
    } finally {
      this.saving = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Restaurantes Uber Eats</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createStore(e)}>
          <ion-input
            placeholder="ID de tienda (Uber)"
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
          <ion-button type="submit" size="small" disabled={this.saving || !this.newStoreId || !this.newName}>
            {this.saving ? 'Guardando…' : 'Registrar'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.stores as unknown as Record<string, unknown>[]}
          searchKeys={['name', 'store_id']}
          searchPlaceholder="Buscar restaurante o ID…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin restaurantes registrados.'}
        />
      </div>
    );
  }
}
