import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn, DataTableAction } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `services` (Stencil). Mini-app: lista de servicios del
// catálogo + búsqueda + alta rápida (con categoría) + borrado. Es la pieza
// `ui.entry` que el shell carga en runtime (modules/services/dist/services.esm.js).
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

interface Service {
  id: string;
  name: string;
  price: string;
  pricing_type: string;
  duration_minutes: number;
  is_bookable: number;
  category_id: string | null;
  category: string | null;
}

interface Category {
  id: string;
  name: string;
  slug: string;
  service_count: number;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-services-list',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ion-text-color, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .form { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; }
    .form ion-input, .form ion-select { --background:var(--surface-2,#f7f4ec); border:1px solid var(--ion-border-color,#e0ddd4); border-radius:8px; min-width:8rem; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpServicesList {
  @State() services: Service[] = [];
  @State() categories: Category[] = [];
  @State() loading = true;
  @State() error = '';
  @State() newName = '';
  @State() newPrice = '';
  @State() newDuration = '';
  @State() newCategory = '';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'name', header: 'Nombre' },
    { key: 'category', header: 'Categoría', format: (r) => (r.category as string) ?? '—' },
    { key: 'pricing_type', header: 'Tarifa' },
    { key: 'price', header: 'Precio', align: 'right', format: (r) => Number(r.price).toFixed(2) },
    { key: 'duration_minutes', header: 'Duración (min)', align: 'right' },
  ];

  private actions: DataTableAction[] = [{ id: 'delete', label: 'Eliminar', icon: 'trash', color: 'danger' }];

  async componentWillLoad() {
    await this.refresh();
    // Reactividad: el runtime emite eventos de dominio vía SDK/WS; recargamos.
    try {
      const off1 = erplora().on('services.service.created', () => this.refresh());
      const off2 = erplora().on('services.service.updated', () => this.refresh());
      const off3 = erplora().on('services.service.deleted', () => this.refresh());
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
      const [services, cats] = await Promise.all([
        erplora().query<Service[]>('services.services.list'),
        erplora().query<Category[]>('services.categories.list'),
      ]);
      this.services = services ?? [];
      this.categories = cats ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando servicios';
    } finally {
      this.loading = false;
    }
  }

  private async createService(ev: Event) {
    ev.preventDefault();
    if (!this.newName.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('services.services.create', {
        name: this.newName.trim(),
        description: '',
        short_description: '',
        category_id: this.newCategory || null,
        pricing_type: 'fixed',
        price: Number(this.newPrice) || 0,
        cost: 0,
        duration_minutes: Number(this.newDuration) || 60,
        buffer_before: 0,
        buffer_after: 0,
        max_capacity: 1,
        is_bookable: 1,
        requires_confirmation: 0,
        allow_online_booking: 1,
        sort_order: 0,
        is_featured: 0,
        sku: '',
        barcode: '',
        notes: '',
      });
      this.newName = '';
      this.newPrice = '';
      this.newDuration = '';
      this.newCategory = '';
      await this.refresh(); // (además del evento; garantiza refresco inmediato)
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear el servicio';
    } finally {
      this.saving = false;
    }
  }

  private async onRowAction(ev: CustomEvent<{ actionId: string; row: Record<string, unknown> }>) {
    const { actionId, row } = ev.detail;
    if (actionId !== 'delete') return;
    this.error = '';
    try {
      await erplora().command('services.services.delete', { service_id: row.id });
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo eliminar el servicio';
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Servicios</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createService(e)}>
          <ion-input
            placeholder="Nombre"
            value={this.newName}
            onIonInput={(e: any) => (this.newName = e.target.value)}
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
            placeholder="Duración (min)"
            value={this.newDuration}
            onIonInput={(e: any) => (this.newDuration = e.target.value)}
          />
          <ion-select
            placeholder="Categoría…"
            value={this.newCategory}
            onIonChange={(e: any) => (this.newCategory = e.target.value)}
          >
            <ion-select-option value="">Sin categoría</ion-select-option>
            {this.categories.map((c) => (
              <ion-select-option value={c.id} key={c.id}>
                {c.name}
              </ion-select-option>
            ))}
          </ion-select>
          <ion-button type="submit" size="small" disabled={this.saving || !this.newName}>
            {this.saving ? 'Guardando…' : 'Añadir'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.services as unknown as Record<string, unknown>[]}
          searchKeys={['name', 'pricing_type']}
          searchPlaceholder="Buscar servicio…"
          actions={this.actions}
          emptyMessage={this.loading ? 'Cargando…' : 'Sin servicios.'}
          onRowAction={(e: CustomEvent) => this.onRowAction(e)}
        />
      </div>
    );
  }
}
