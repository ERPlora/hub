import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild lo
// empaquete dentro del bundle del módulo. El shell provee los `ion-*` (4 niveles).
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `delivery` (Stencil): listado de zonas de reparto + alta rápida.
// NO toca la BD: llama al SDK (erplora.query/command/on). El alta es CRUD declarativo
// (command `delivery.zones.create`); el borrado tiene guarda de dependientes en WASM.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface DeliveryZone {
  id: string;
  name: string;
  is_active: number;
  min_order: string;
  delivery_fee: string;
  estimated_time: number;
  sort_order: number;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-delivery-zones',
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
export class ErpDeliveryZones {
  @State() zones: DeliveryZone[] = [];
  @State() loading = true;
  @State() error = '';
  @State() saving = false;
  @State() newName = '';
  @State() newFee = '';
  @State() newMinOrder = '';
  @State() newTime = '';

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'name', header: 'Zona' },
    { key: 'min_order', header: 'Pedido mín.', align: 'right', format: (r) => Number(r.min_order).toFixed(2) },
    { key: 'delivery_fee', header: 'Tarifa', align: 'right', format: (r) => Number(r.delivery_fee).toFixed(2) },
    { key: 'estimated_time', header: 'Tiempo (min)', align: 'right' },
    { key: 'is_active', header: 'Activa', format: (r) => (r.is_active ? 'Sí' : 'No') },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('delivery.zone.created', () => this.refresh());
      const off2 = erplora().on('delivery.zone.updated', () => this.refresh());
      const off3 = erplora().on('delivery.zone.deleted', () => this.refresh());
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
      const zones = await erplora().query<DeliveryZone[]>('delivery.zones.list', { active_only: '' });
      this.zones = zones ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando zonas';
    } finally {
      this.loading = false;
    }
  }

  private async createZone(ev: Event) {
    ev.preventDefault();
    if (!this.newName.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('delivery.zones.create', {
        name: this.newName.trim(),
        delivery_fee: Number(this.newFee) || 0,
        min_order: Number(this.newMinOrder) || 0,
        estimated_time: Number(this.newTime) || 30,
        is_active: true,
        zip_codes: [],
        sort_order: 0,
      });
      this.newName = '';
      this.newFee = '';
      this.newMinOrder = '';
      this.newTime = '';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear la zona';
    } finally {
      this.saving = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Zonas de reparto</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createZone(e)}>
          <ion-input
            placeholder="Nombre"
            value={this.newName}
            onIonInput={(e: any) => (this.newName = e.target.value)}
          />
          <ion-input
            type="number"
            step="0.01"
            placeholder="Tarifa"
            value={this.newFee}
            onIonInput={(e: any) => (this.newFee = e.target.value)}
          />
          <ion-input
            type="number"
            step="0.01"
            placeholder="Pedido mín."
            value={this.newMinOrder}
            onIonInput={(e: any) => (this.newMinOrder = e.target.value)}
          />
          <ion-input
            type="number"
            placeholder="Tiempo (min)"
            value={this.newTime}
            onIonInput={(e: any) => (this.newTime = e.target.value)}
          />
          <ion-button type="submit" size="small" disabled={this.saving || !this.newName}>
            {this.saving ? 'Guardando…' : 'Añadir'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.zones as unknown as Record<string, unknown>[]}
          searchKeys={['name']}
          searchPlaceholder="Buscar zona…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin zonas.'}
        />
      </div>
    );
  }
}
