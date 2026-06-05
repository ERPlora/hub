import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn, DataTableAction } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `carriers` (Stencil). Vista "shipments": envíos del hub
// (más recientes primero) con filtro por estado + acción rápida de despacho /
// marcado como entregado. NO toca la BD: usa erplora.query/command/on.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface Shipment {
  id: string;
  carrier_id: string;
  shipment_number: string;
  tracking_number: string;
  reference: string;
  weight_kg: string;
  service_type: string;
  status: string;
  shipping_cost: string;
}

const STATUSES = ['', 'created', 'in_transit', 'delivered', 'returned', 'lost'];

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-carriers-shipments',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .filters { display:flex; gap:.5rem; align-items:end; margin:.5rem 0 1rem; }
    .filters ion-select { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:10rem; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpCarriersShipments {
  @State() shipments: Shipment[] = [];
  @State() loading = true;
  @State() error = '';
  @State() statusFilter = '';
  @State() busyId = '';

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'shipment_number', header: 'Nº envío' },
    { key: 'tracking_number', header: 'Seguimiento' },
    { key: 'reference', header: 'Referencia' },
    { key: 'service_type', header: 'Servicio' },
    { key: 'weight_kg', header: 'Peso (kg)', align: 'right' },
    { key: 'status', header: 'Estado' },
  ];

  // Acciones de fila (botones). El estado del envío decide cuál tiene efecto:
  // created → dispatch, in_transit → mark_delivered (otros estados: no-op).
  private actions: DataTableAction[] = [
    { id: 'dispatch', label: 'Despachar', icon: 'send-outline', color: 'primary' },
    { id: 'deliver', label: 'Entregado', icon: 'checkmark-done-outline', color: 'success' },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('carriers.shipment.created', () => this.refresh());
      const off2 = erplora().on('carriers.shipment.dispatched', () => this.refresh());
      const off3 = erplora().on('carriers.shipment.delivered', () => this.refresh());
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
      const rows = await erplora().query<Shipment[]>('carriers.shipments.list', {
        carrier_id: '',
        status: this.statusFilter,
        limit: 100,
      });
      this.shipments = rows ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando envíos';
    } finally {
      this.loading = false;
    }
  }

  private async onRowAction(actionId: string, s: Shipment) {
    this.busyId = s.id;
    this.error = '';
    try {
      if (actionId === 'dispatch') {
        await erplora().command('carriers.shipments.dispatch', { shipment_id: s.id });
      } else if (actionId === 'deliver') {
        await erplora().command('carriers.shipments.mark_delivered', { shipment_id: s.id });
      }
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo actualizar el envío';
    } finally {
      this.busyId = '';
    }
  }

  private async onStatusChange(v: string) {
    this.statusFilter = v;
    await this.refresh();
  }

  render() {
    return (
      <div>
        <header>
          <h2>Envíos</h2>
        </header>

        <div class="filters">
          <ion-select
            placeholder="Estado…"
            value={this.statusFilter}
            onIonChange={(e: any) => this.onStatusChange(e.target.value)}
          >
            {STATUSES.map((st) => (
              <ion-select-option value={st} key={st || 'all'}>
                {st || 'Todos'}
              </ion-select-option>
            ))}
          </ion-select>
        </div>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.shipments as unknown as Record<string, unknown>[]}
          actions={this.actions}
          searchKeys={['shipment_number', 'tracking_number', 'reference']}
          searchPlaceholder="Buscar nº, seguimiento o referencia…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin envíos.'}
          onRowAction={(e: CustomEvent<{ actionId: string; row: Record<string, unknown> }>) =>
            this.onRowAction(e.detail.actionId, e.detail.row as unknown as Shipment)
          }
        />
      </div>
    );
  }
}
