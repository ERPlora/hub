import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `multi_warehouse` (vista traslados). Lista los documentos de
// traslado inter-almacén + alta rápida de un borrador (origen → destino, una línea).
// El alta completa multi-línea y las transiciones dispatch/receive se modelan en WASM;
// aquí ofrecemos el alta básica de borrador y la cancelación.
//
// El componente NO toca la BD: llama al SDK (erplora.query/command/on).

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface Transfer {
  id: string;
  transfer_number: string;
  source_warehouse_id: string;
  destination_warehouse_id: string;
  status: string;
  created_date: string | null;
  dispatched_date: string | null;
  received_date: string | null;
  carrier: string;
  tracking_ref: string;
  notes: string;
}

interface Warehouse {
  id: string;
  code: string;
  name: string;
}

const STATUS_LABELS: Record<string, string> = {
  draft: 'Borrador',
  in_transit: 'En tránsito',
  received: 'Recibido',
  cancelled: 'Cancelado',
};

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-multi-warehouse-transfers',
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
export class ErpMultiWarehouseTransfers {
  @State() transfers: Transfer[] = [];
  @State() warehouses: Warehouse[] = [];
  @State() loading = true;
  @State() error = '';
  @State() statusFilter = '';
  // alta de borrador (una línea)
  @State() newSource = '';
  @State() newDest = '';
  @State() newProduct = '';
  @State() newQty = '';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'transfer_number', header: 'Nº' },
    {
      key: 'source_warehouse_id',
      header: 'Origen',
      format: (r) => this.whName(r.source_warehouse_id as string),
    },
    {
      key: 'destination_warehouse_id',
      header: 'Destino',
      format: (r) => this.whName(r.destination_warehouse_id as string),
    },
    {
      key: 'status',
      header: 'Estado',
      format: (r) => STATUS_LABELS[r.status as string] ?? (r.status as string),
    },
    { key: 'created_date', header: 'Creado', format: (r) => (r.created_date as string) ?? '—' },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const events = [
        'multi_warehouse.transfer.created',
        'multi_warehouse.transfer.dispatched',
        'multi_warehouse.transfer.received',
        'multi_warehouse.transfer.cancelled',
      ];
      const offs = events.map((ev) => erplora().on(ev, () => this.refresh()));
      this.unsub = () => offs.forEach((off) => off());
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
      const [transfers, warehouses] = await Promise.all([
        erplora().query<Transfer[]>('multi_warehouse.transfers.list', {
          status: this.statusFilter,
          source_id: '',
          destination_id: '',
        }),
        erplora().query<Warehouse[]>('multi_warehouse.warehouses.list', { active_only: '1' }),
      ]);
      this.transfers = transfers ?? [];
      this.warehouses = warehouses ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando traslados';
    } finally {
      this.loading = false;
    }
  }

  private async createTransfer(ev: Event) {
    ev.preventDefault();
    if (!this.newSource || !this.newDest || !this.newProduct.trim() || !this.newQty) return;
    if (this.newSource === this.newDest) {
      this.error = 'Origen y destino deben ser distintos.';
      return;
    }
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('multi_warehouse.transfers.create', {
        source_warehouse_id: this.newSource,
        destination_warehouse_id: this.newDest,
        carrier: '',
        tracking_ref: '',
        notes: '',
        lines: [
          {
            product_ref: this.newProduct.trim(),
            quantity_requested: Number(this.newQty) || 0,
            lot_ref: '',
          },
        ],
      });
      this.newSource = '';
      this.newDest = '';
      this.newProduct = '';
      this.newQty = '';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear el traslado';
    } finally {
      this.saving = false;
    }
  }

  private whName(id: string): string {
    return this.warehouses.find((w) => w.id === id)?.code ?? '—';
  }

  render() {
    return (
      <div>
        <header>
          <h2>Traslados</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createTransfer(e)}>
          <ion-select
            placeholder="Origen…"
            value={this.newSource}
            onIonChange={(e: any) => (this.newSource = e.target.value)}
          >
            {this.warehouses.map((w) => (
              <ion-select-option value={w.id} key={w.id}>
                {w.code}
              </ion-select-option>
            ))}
          </ion-select>
          <ion-select
            placeholder="Destino…"
            value={this.newDest}
            onIonChange={(e: any) => (this.newDest = e.target.value)}
          >
            {this.warehouses.map((w) => (
              <ion-select-option value={w.id} key={w.id}>
                {w.code}
              </ion-select-option>
            ))}
          </ion-select>
          <ion-input
            placeholder="Producto (ref)"
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
          <ion-button
            type="submit"
            size="small"
            disabled={this.saving || !this.newSource || !this.newDest || !this.newProduct || !this.newQty}
          >
            {this.saving ? 'Guardando…' : 'Nuevo traslado'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.transfers as unknown as Record<string, unknown>[]}
          searchKeys={['transfer_number', 'status']}
          searchPlaceholder="Buscar nº o estado…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin traslados.'}
        />
      </div>
    );
  }
}
