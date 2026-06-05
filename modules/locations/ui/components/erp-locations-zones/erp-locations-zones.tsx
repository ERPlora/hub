import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `locations` (vista zones). Mini-app: elige un almacén y
// gestiona sus zonas (alta rápida). Es parte de la pieza `ui.entry` que el shell carga
// en runtime (modules/locations/dist/locations.esm.js).
//
// La lógica vive en Rust: este componente NO toca la BD; llama al SDK
// (erplora.query/command/on). El listado usa el DataTable compartido + Ionic.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface Warehouse {
  id: string;
  code: string;
  name: string;
  is_default: number;
}

interface Zone {
  id: string;
  warehouse_id: string;
  code: string;
  name: string;
  zone_type: string;
  is_active: number;
}

const ZONE_TYPES = ['storage', 'picking', 'packing', 'receiving', 'shipping'];

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-locations-zones',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .form { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; }
    .form ion-input, .form ion-select { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:8rem; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpLocationsZones {
  @State() warehouses: Warehouse[] = [];
  @State() zones: Zone[] = [];
  @State() warehouseId = '';
  @State() loading = true;
  @State() error = '';
  @State() newCode = '';
  @State() newName = '';
  @State() newType = 'storage';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'code', header: 'Código' },
    { key: 'name', header: 'Nombre' },
    { key: 'zone_type', header: 'Tipo' },
    { key: 'is_active', header: 'Activa', format: (r) => (r.is_active ? 'Sí' : 'No') },
  ];

  async componentWillLoad() {
    await this.loadWarehouses();
    try {
      const off1 = erplora().on('locations.warehouse.created', () => this.loadWarehouses());
      const off2 = erplora().on('locations.zone.created', () => this.refreshZones());
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

  private async loadWarehouses() {
    this.loading = true;
    this.error = '';
    try {
      const whs = await erplora().query<Warehouse[]>('locations.warehouses.list', { active_only: '1' });
      this.warehouses = whs ?? [];
      if (!this.warehouseId && this.warehouses.length) {
        const def = this.warehouses.find((w) => w.is_default) ?? this.warehouses[0];
        this.warehouseId = def.id;
      }
      await this.refreshZones();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando almacenes';
    } finally {
      this.loading = false;
    }
  }

  private async refreshZones() {
    if (!this.warehouseId) {
      this.zones = [];
      return;
    }
    this.error = '';
    try {
      const zs = await erplora().query<Zone[]>('locations.zones.list', {
        warehouse_id: this.warehouseId,
        zone_type: '',
      });
      this.zones = zs ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando zonas';
    }
  }

  private async onWarehouseChange(id: string) {
    this.warehouseId = id;
    await this.refreshZones();
  }

  private async createZone(ev: Event) {
    ev.preventDefault();
    if (!this.warehouseId || !this.newCode.trim() || !this.newName.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('locations.zones.create', {
        warehouse_id: this.warehouseId,
        code: this.newCode.trim(),
        name: this.newName.trim(),
        zone_type: this.newType,
      });
      this.newCode = '';
      this.newName = '';
      this.newType = 'storage';
      await this.refreshZones();
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
          <h2>Zonas</h2>
          <ion-select
            placeholder="Almacén…"
            value={this.warehouseId}
            onIonChange={(e: any) => this.onWarehouseChange(e.target.value)}
          >
            {this.warehouses.map((w) => (
              <ion-select-option value={w.id} key={w.id}>
                {w.code} — {w.name}
              </ion-select-option>
            ))}
          </ion-select>
        </header>

        <form class="form" onSubmit={(e) => this.createZone(e)}>
          <ion-input
            placeholder="Código (A1)"
            value={this.newCode}
            onIonInput={(e: any) => (this.newCode = e.target.value)}
          />
          <ion-input
            placeholder="Nombre"
            value={this.newName}
            onIonInput={(e: any) => (this.newName = e.target.value)}
          />
          <ion-select
            placeholder="Tipo…"
            value={this.newType}
            onIonChange={(e: any) => (this.newType = e.target.value)}
          >
            {ZONE_TYPES.map((t) => (
              <ion-select-option value={t} key={t}>
                {t}
              </ion-select-option>
            ))}
          </ion-select>
          <ion-button
            type="submit"
            size="small"
            disabled={this.saving || !this.warehouseId || !this.newCode || !this.newName}
          >
            {this.saving ? 'Guardando…' : 'Añadir zona'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.zones as unknown as Record<string, unknown>[]}
          searchKeys={['code', 'name', 'zone_type']}
          searchPlaceholder="Buscar zona…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin zonas en este almacén.'}
        />
      </div>
    );
  }
}
