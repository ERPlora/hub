import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `picking_packing` — vista de Pick Lists.
// Mini-app: lista las pick lists del hub + alta rápida de una nueva (con una línea
// inicial). NO toca la BD: todo va por el SDK (erplora.query/command/on). La generación
// de número (contador), el batch de líneas y la máquina de estados viven en WASM.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface PickList {
  id: string;
  pick_number: string;
  order_ref: string;
  status: string;
  assigned_to_ref: string;
  created_at: string;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-picking-packing-picks',
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
export class ErpPickingPackingPicks {
  @State() picks: PickList[] = [];
  @State() loading = true;
  @State() error = '';
  @State() statusFilter = '';
  @State() newOrderRef = '';
  @State() newAssigned = '';
  @State() newProduct = '';
  @State() newQty = '';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'pick_number', header: 'Nº pick' },
    { key: 'order_ref', header: 'Pedido', format: (r) => (r.order_ref as string) || '—' },
    { key: 'status', header: 'Estado' },
    { key: 'assigned_to_ref', header: 'Operario', format: (r) => (r.assigned_to_ref as string) || '—' },
    { key: 'created_at', header: 'Creado' },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const offs = [
        erplora().on('picking_packing.pick.created', () => this.refresh()),
        erplora().on('picking_packing.pick.started', () => this.refresh()),
        erplora().on('picking_packing.pick.completed', () => this.refresh()),
        erplora().on('picking_packing.pick.cancelled', () => this.refresh()),
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
      const picks = await erplora().query<PickList[]>('picking_packing.picks.list', {
        status: this.statusFilter,
        assigned_to: '',
        limit: 50,
      });
      this.picks = picks ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando pick lists';
    } finally {
      this.loading = false;
    }
  }

  private async createPick(ev: Event) {
    ev.preventDefault();
    if (!this.newProduct.trim() || !(Number(this.newQty) > 0)) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('picking_packing.picks.create', {
        order_ref: this.newOrderRef.trim(),
        assigned_to_ref: this.newAssigned.trim(),
        notes: '',
        lines: [
          {
            product_ref: this.newProduct.trim(),
            quantity_requested: Number(this.newQty),
            location_ref: '',
            lot_ref: '',
          },
        ],
      });
      this.newOrderRef = '';
      this.newAssigned = '';
      this.newProduct = '';
      this.newQty = '';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear la pick list';
    } finally {
      this.saving = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Pick Lists</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createPick(e)}>
          <ion-input
            placeholder="Pedido (ref)"
            value={this.newOrderRef}
            onIonInput={(e: any) => (this.newOrderRef = e.target.value)}
          />
          <ion-input
            placeholder="Operario (ref)"
            value={this.newAssigned}
            onIonInput={(e: any) => (this.newAssigned = e.target.value)}
          />
          <ion-input
            placeholder="Producto (SKU)"
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
          <ion-button type="submit" size="small" disabled={this.saving || !this.newProduct || !(Number(this.newQty) > 0)}>
            {this.saving ? 'Guardando…' : 'Crear pick'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.picks as unknown as Record<string, unknown>[]}
          searchKeys={['pick_number', 'order_ref', 'assigned_to_ref']}
          searchPlaceholder="Buscar nº, pedido u operario…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin pick lists.'}
        />
      </div>
    );
  }
}
