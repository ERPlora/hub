import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild lo
// empaquete dentro del bundle del módulo. El shell provee los `ion-*` (4 niveles).
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `delivery` (Stencil): listado de repartidores + alta rápida.
// NO toca la BD: llama al SDK (erplora.query/command/on). El alta es CRUD declarativo
// (command `delivery.drivers.create`); el borrado tiene guarda de dependientes en WASM.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface Driver {
  id: string;
  name: string;
  phone: string;
  vehicle_type: string;
  is_active: number;
  is_external: number;
  notes: string;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-delivery-drivers',
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
export class ErpDeliveryDrivers {
  @State() drivers: Driver[] = [];
  @State() loading = true;
  @State() error = '';
  @State() saving = false;
  @State() newName = '';
  @State() newPhone = '';
  @State() newVehicle = '';

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'name', header: 'Nombre' },
    { key: 'phone', header: 'Teléfono' },
    { key: 'vehicle_type', header: 'Vehículo' },
    { key: 'is_external', header: 'Externo', format: (r) => (r.is_external ? 'Sí' : 'No') },
    { key: 'is_active', header: 'Activo', format: (r) => (r.is_active ? 'Sí' : 'No') },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('delivery.driver.created', () => this.refresh());
      const off2 = erplora().on('delivery.driver.updated', () => this.refresh());
      const off3 = erplora().on('delivery.driver.deleted', () => this.refresh());
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
      const drivers = await erplora().query<Driver[]>('delivery.drivers.list', { active_only: '' });
      this.drivers = drivers ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando repartidores';
    } finally {
      this.loading = false;
    }
  }

  private async createDriver(ev: Event) {
    ev.preventDefault();
    if (!this.newName.trim() || !this.newPhone.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('delivery.drivers.create', {
        name: this.newName.trim(),
        phone: this.newPhone.trim(),
        vehicle_type: this.newVehicle.trim(),
        is_active: true,
        is_external: false,
        notes: '',
      });
      this.newName = '';
      this.newPhone = '';
      this.newVehicle = '';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear el repartidor';
    } finally {
      this.saving = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Repartidores</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createDriver(e)}>
          <ion-input
            placeholder="Nombre"
            value={this.newName}
            onIonInput={(e: any) => (this.newName = e.target.value)}
          />
          <ion-input
            placeholder="Teléfono"
            value={this.newPhone}
            onIonInput={(e: any) => (this.newPhone = e.target.value)}
          />
          <ion-input
            placeholder="Vehículo (moto, coche…)"
            value={this.newVehicle}
            onIonInput={(e: any) => (this.newVehicle = e.target.value)}
          />
          <ion-button type="submit" size="small" disabled={this.saving || !this.newName || !this.newPhone}>
            {this.saving ? 'Guardando…' : 'Añadir'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.drivers as unknown as Record<string, unknown>[]}
          searchKeys={['name', 'phone']}
          searchPlaceholder="Buscar repartidor…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin repartidores.'}
        />
      </div>
    );
  }
}
