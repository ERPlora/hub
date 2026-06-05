import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `work_centers` (Stencil). Mini-app: lista de centros de
// producción + alta rápida + desactivación. Es la pieza `ui.entry` que el shell carga
// en runtime (modules/work_centers/dist/work_centers.esm.js).
//
// 90% de la lógica vive en Rust/WASM: este componente NO toca la BD; llama al SDK
// (erplora.query/command/on). El listado usa el DataTable compartido + Ionic.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface WorkCenter {
  id: string;
  code: string;
  name: string;
  center_type: string;
  capacity_per_hour: string;
  hourly_cost: string;
  location_ref: string;
  is_active: number;
}

const CENTER_TYPES = ['machine', 'line', 'station', 'cell'];

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-work-centers-list',
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
export class ErpWorkCentersList {
  @State() centers: WorkCenter[] = [];
  @State() loading = true;
  @State() error = '';
  @State() newCode = '';
  @State() newName = '';
  @State() newType = 'machine';
  @State() newCapacity = '';
  @State() newCost = '';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'code', header: 'Código' },
    { key: 'name', header: 'Nombre' },
    { key: 'center_type', header: 'Tipo' },
    { key: 'capacity_per_hour', header: 'Capacidad/h', align: 'right', format: (r) => Number(r.capacity_per_hour).toFixed(3) },
    { key: 'hourly_cost', header: 'Coste/h', align: 'right', format: (r) => Number(r.hourly_cost).toFixed(2) },
    { key: 'location_ref', header: 'Ubicación' },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('work_centers.center.created', () => this.refresh());
      const off2 = erplora().on('work_centers.center.deactivated', () => this.refresh());
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
      const centers = await erplora().query<WorkCenter[]>('work_centers.centers.list', {
        active_only: 1,
        center_type: '',
      });
      this.centers = centers ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando centros de trabajo';
    } finally {
      this.loading = false;
    }
  }

  private async createCenter(ev: Event) {
    ev.preventDefault();
    if (!this.newCode.trim() || !this.newName.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('work_centers.centers.create', {
        code: this.newCode.trim(),
        name: this.newName.trim(),
        center_type: this.newType,
        capacity_per_hour: Number(this.newCapacity) || 0,
        hourly_cost: Number(this.newCost) || 0,
        location_ref: '',
        calendar: '{}',
        notes: '',
      });
      this.newCode = '';
      this.newName = '';
      this.newType = 'machine';
      this.newCapacity = '';
      this.newCost = '';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear el centro';
    } finally {
      this.saving = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Centros de trabajo</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createCenter(e)}>
          <ion-input
            placeholder="Código (CNC-01)"
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
            {CENTER_TYPES.map((t) => (
              <ion-select-option value={t} key={t}>
                {t}
              </ion-select-option>
            ))}
          </ion-select>
          <ion-input
            type="number"
            step="0.001"
            placeholder="Capacidad/h"
            value={this.newCapacity}
            onIonInput={(e: any) => (this.newCapacity = e.target.value)}
          />
          <ion-input
            type="number"
            step="0.01"
            placeholder="Coste/h"
            value={this.newCost}
            onIonInput={(e: any) => (this.newCost = e.target.value)}
          />
          <ion-button type="submit" size="small" disabled={this.saving || !this.newCode || !this.newName}>
            {this.saving ? 'Guardando…' : 'Añadir'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.centers as unknown as Record<string, unknown>[]}
          searchKeys={['code', 'name', 'center_type']}
          searchPlaceholder="Buscar código o nombre…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin centros de trabajo.'}
        />
      </div>
    );
  }
}
