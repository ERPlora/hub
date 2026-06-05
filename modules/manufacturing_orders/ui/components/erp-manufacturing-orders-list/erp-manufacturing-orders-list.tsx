import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn, DataTableAction } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `manufacturing_orders` (Stencil). Mini-app: lista de
// órdenes de fabricación + alta rápida (cabecera + 1 línea de material) +
// acciones de ciclo de vida (release/start/complete/cancel).
//
// La lógica real (contador atómico de mo_number, alta batch de materiales, derivación
// de estado del consumo, agregados del resumen) vive en Rust→WASM. Este componente NO
// toca la BD: llama al SDK (erplora.query/command/on).

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface ManufacturingOrder {
  id: string;
  mo_number: string;
  product_ref: string;
  quantity_planned: string;
  quantity_produced: string;
  scheduled_date: string | null;
  due_date: string | null;
  status: string;
  priority: string;
  work_center_ref: string;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

const STATUS_LABELS: Record<string, string> = {
  draft: 'Draft',
  released: 'Released',
  in_progress: 'In Progress',
  completed: 'Completed',
  cancelled: 'Cancelled',
};

@Component({
  tag: 'erp-manufacturing-orders-list',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .form { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; }
    .form ion-input, .form ion-select { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:8rem; }
    .err { color:#d9480f; font-weight:600; }
    .actions { display:flex; gap:.25rem; }
  `,
})
export class ErpManufacturingOrdersList {
  @State() orders: ManufacturingOrder[] = [];
  @State() loading = true;
  @State() error = '';
  @State() statusFilter = '';
  // Alta rápida (cabecera + 1 material). Para BOMs complejos, formulario dedicado aparte.
  @State() newProduct = '';
  @State() newQty = '';
  @State() newMaterialRef = '';
  @State() newMaterialQty = '';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'mo_number', header: 'Nº MO' },
    { key: 'product_ref', header: 'Producto' },
    { key: 'quantity_planned', header: 'Plan.', align: 'right', format: (r) => Number(r.quantity_planned).toFixed(3) },
    { key: 'quantity_produced', header: 'Prod.', align: 'right', format: (r) => Number(r.quantity_produced).toFixed(3) },
    { key: 'priority', header: 'Prioridad' },
    { key: 'status', header: 'Estado', format: (r) => STATUS_LABELS[r.status as string] ?? (r.status as string) },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const offs = [
        erplora().on('manufacturing_orders.mo.created', () => this.refresh()),
        erplora().on('manufacturing_orders.mo.released', () => this.refresh()),
        erplora().on('manufacturing_orders.mo.started', () => this.refresh()),
        erplora().on('manufacturing_orders.mo.completed', () => this.refresh()),
        erplora().on('manufacturing_orders.mo.cancelled', () => this.refresh()),
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
      this.orders =
        (await erplora().query<ManufacturingOrder[]>('manufacturing_orders.orders.list', {
          status: this.statusFilter,
          product_ref: '',
          limit: 50,
        })) ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando órdenes';
    } finally {
      this.loading = false;
    }
  }

  private async createOrder(ev: Event) {
    ev.preventDefault();
    if (!this.newProduct.trim() || !this.newMaterialRef.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('manufacturing_orders.orders.create', {
        product_ref: this.newProduct.trim(),
        quantity_planned: Number(this.newQty) || 0,
        scheduled_date: null,
        due_date: null,
        priority: 'normal',
        work_center_ref: '',
        notes: '',
        materials: [
          {
            material_ref: this.newMaterialRef.trim(),
            quantity_planned: Number(this.newMaterialQty) || 0,
            unit: 'unit',
          },
        ],
      });
      this.newProduct = '';
      this.newQty = '';
      this.newMaterialRef = '';
      this.newMaterialQty = '';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear la orden';
    } finally {
      this.saving = false;
    }
  }

  // El DataTable compartido emite `rowAction` con {actionId, row}. Mostramos los
  // tres botones de transición y validamos el estado aquí (el runtime/SQL revalida
  // con el guard WHERE status='...'); Rust es la única autoridad.
  private rowActions: DataTableAction[] = [
    { id: 'release', label: 'Release', color: 'medium' },
    { id: 'start', label: 'Start', color: 'medium' },
    { id: 'complete', label: 'Complete', color: 'primary' },
    { id: 'cancel', label: 'Cancel', color: 'danger' },
  ];

  private async onRowAction(ev: CustomEvent<{ actionId: string; row: Record<string, unknown> }>) {
    const o = ev.detail.row as unknown as ManufacturingOrder;
    this.error = '';
    try {
      switch (ev.detail.actionId) {
        case 'release':
          await erplora().command('manufacturing_orders.orders.release', { mo_id: o.id });
          break;
        case 'start':
          await erplora().command('manufacturing_orders.orders.start', { mo_id: o.id });
          break;
        case 'complete':
          await erplora().command('manufacturing_orders.orders.complete', {
            mo_id: o.id,
            quantity_produced: Number(o.quantity_planned) || 0,
          });
          break;
        case 'cancel':
          await erplora().command('manufacturing_orders.orders.cancel', { mo_id: o.id, reason: '' });
          break;
      }
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Acción no permitida en este estado';
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Órdenes de fabricación</h2>
          <ion-select
            placeholder="Estado…"
            value={this.statusFilter}
            onIonChange={(e: any) => {
              this.statusFilter = e.target.value;
              this.refresh();
            }}
          >
            <ion-select-option value="">Todos</ion-select-option>
            <ion-select-option value="draft">Draft</ion-select-option>
            <ion-select-option value="released">Released</ion-select-option>
            <ion-select-option value="in_progress">In Progress</ion-select-option>
            <ion-select-option value="completed">Completed</ion-select-option>
            <ion-select-option value="cancelled">Cancelled</ion-select-option>
          </ion-select>
        </header>

        <form class="form" onSubmit={(e) => this.createOrder(e)}>
          <ion-input
            placeholder="Producto"
            value={this.newProduct}
            onIonInput={(e: any) => (this.newProduct = e.target.value)}
          />
          <ion-input
            type="number"
            step="0.001"
            placeholder="Cantidad"
            value={this.newQty}
            onIonInput={(e: any) => (this.newQty = e.target.value)}
          />
          <ion-input
            placeholder="Material"
            value={this.newMaterialRef}
            onIonInput={(e: any) => (this.newMaterialRef = e.target.value)}
          />
          <ion-input
            type="number"
            step="0.001"
            placeholder="Cant. material"
            value={this.newMaterialQty}
            onIonInput={(e: any) => (this.newMaterialQty = e.target.value)}
          />
          <ion-button type="submit" size="small" disabled={this.saving || !this.newProduct || !this.newMaterialRef}>
            {this.saving ? 'Guardando…' : 'Nueva orden'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.orders as unknown as Record<string, unknown>[]}
          searchKeys={['mo_number', 'product_ref']}
          searchPlaceholder="Buscar Nº o producto…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin órdenes de fabricación.'}
          actions={this.rowActions}
          onRowAction={(e: CustomEvent<{ actionId: string; row: Record<string, unknown> }>) => this.onRowAction(e)}
        />
      </div>
    );
  }
}
