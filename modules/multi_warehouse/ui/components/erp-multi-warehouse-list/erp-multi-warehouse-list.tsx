import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `multi_warehouse` (vista almacenes). Lista los almacenes del
// hub + alta rápida. Es una de las piezas que el shell carga vía ui.entry
// (modules/multi_warehouse/dist/multi_warehouse.esm.js).
//
// El componente NO toca la BD: llama al SDK (erplora.query/command/on). La unicidad de
// code, el demote del default anterior y demás lógica viven en WASM/runtime.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface Warehouse {
  id: string;
  code: string;
  name: string;
  address: string;
  type: string;
  is_active: number;
  is_default: number;
  owner_organization_ref: string;
}

const WAREHOUSE_TYPES = ['main', 'secondary', 'store', 'dropship'];

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-multi-warehouse-list',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .form { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; }
    .form ion-input, .form ion-select { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:8rem; }
    .err { color:#d9480f; font-weight:600; }
    .badge { font-size:.75rem; padding:.1rem .4rem; border-radius:6px; background:var(--surface-2,#f7f4ec); }
  `,
})
export class ErpMultiWarehouseList {
  @State() warehouses: Warehouse[] = [];
  @State() loading = true;
  @State() error = '';
  @State() newCode = '';
  @State() newName = '';
  @State() newType = 'secondary';
  @State() newDefault = false;
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'code', header: 'Código' },
    { key: 'name', header: 'Nombre' },
    { key: 'type', header: 'Tipo' },
    {
      key: 'is_default',
      header: 'Por defecto',
      format: (r) => (Number(r.is_default) ? 'Sí' : '—'),
    },
    {
      key: 'is_active',
      header: 'Activo',
      format: (r) => (Number(r.is_active) ? 'Sí' : 'No'),
    },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('multi_warehouse.warehouse.created', () => this.refresh());
      const off2 = erplora().on('multi_warehouse.warehouse.default_changed', () => this.refresh());
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
      const rows = await erplora().query<Warehouse[]>('multi_warehouse.warehouses.list', {
        active_only: '1',
      });
      this.warehouses = rows ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando almacenes';
    } finally {
      this.loading = false;
    }
  }

  private async createWarehouse(ev: Event) {
    ev.preventDefault();
    if (!this.newCode.trim() || !this.newName.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('multi_warehouse.warehouses.create', {
        code: this.newCode.trim(),
        name: this.newName.trim(),
        type: this.newType,
        address: '',
        is_default: this.newDefault,
        owner_organization_ref: '',
      });
      this.newCode = '';
      this.newName = '';
      this.newType = 'secondary';
      this.newDefault = false;
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear el almacén';
    } finally {
      this.saving = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Almacenes</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createWarehouse(e)}>
          <ion-input
            placeholder="Código (MAIN)"
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
            {WAREHOUSE_TYPES.map((t) => (
              <ion-select-option value={t} key={t}>
                {t}
              </ion-select-option>
            ))}
          </ion-select>
          <ion-checkbox
            checked={this.newDefault}
            onIonChange={(e: any) => (this.newDefault = e.target.checked)}
          >
            Por defecto
          </ion-checkbox>
          <ion-button type="submit" size="small" disabled={this.saving || !this.newCode || !this.newName}>
            {this.saving ? 'Guardando…' : 'Añadir'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.warehouses as unknown as Record<string, unknown>[]}
          searchKeys={['code', 'name', 'type']}
          searchPlaceholder="Buscar código o nombre…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin almacenes.'}
        />
      </div>
    );
  }
}
