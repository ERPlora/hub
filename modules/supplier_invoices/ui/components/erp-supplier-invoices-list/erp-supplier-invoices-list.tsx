import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn, DataTableAction } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `supplier_invoices` (Stencil). Mini-app: lista de
// facturas recibidas de proveedores + filtro + alta rápida de una factura con
// una línea. Es la pieza `ui.entry` que el shell carga en runtime
// (modules/supplier_invoices/dist/supplier_invoices.esm.js).
//
// 90% de la lógica vive en Rust/WASM: este componente NO toca la BD; llama al
// SDK (erplora.query/command/on). El alta (con líneas + totales) la ejecuta el
// handler WASM `create_invoice`; las transiciones de estado (validate/mark_paid/
// cancel) son comandos Tier 0 que valida el runtime.
// El cliente se obtiene de `globalThis.erplora` (lo monta el shell en el boot).
// El listado usa el DataTable compartido + Ionic; el alta usa elementos Ionic.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface Invoice {
  id: string;
  supplier_name: string;
  invoice_number: string;
  invoice_date: string | null;
  total_amount: string | number;
  status: string;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

const STATUS_LABEL: Record<string, string> = {
  pending: 'Pendiente',
  validated: 'Validada',
  paid: 'Pagada',
  cancelled: 'Cancelada',
};

@Component({
  tag: 'erp-supplier-invoices-list',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ion-text-color, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .form { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; }
    .form ion-input, .form ion-select { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:7rem; flex:1; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpSupplierInvoicesList {
  @State() invoices: Invoice[] = [];
  @State() loading = true;
  @State() error = '';
  @State() statusFilter = '';
  @State() newSupplier = '';
  @State() newNumber = '';
  @State() newDesc = '';
  @State() newQty = '1';
  @State() newPrice = '';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'supplier_name', header: 'Proveedor' },
    { key: 'invoice_number', header: 'Nº' },
    { key: 'invoice_date', header: 'Fecha', format: (r) => (r.invoice_date as string) ?? '—' },
    { key: 'total_amount', header: 'Total', align: 'right', format: (r) => Number(r.total_amount).toFixed(2) },
    { key: 'status', header: 'Estado', format: (r) => STATUS_LABEL[r.status as string] ?? (r.status as string) },
  ];

  // Acciones de fila: el DataTable las muestra todas; el handler las aplica solo
  // si el estado de la factura lo permite (no-op en caso contrario).
  private actions: DataTableAction[] = [
    { id: 'validate', label: 'Validar', icon: 'checkmark-outline', color: 'primary' },
    { id: 'mark_paid', label: 'Marcar pagada', icon: 'cash-outline', color: 'success' },
    { id: 'cancel', label: 'Cancelar', icon: 'close-outline', color: 'danger' },
  ];

  async componentWillLoad() {
    await this.refresh();
    // Reactividad: recargamos cuando el runtime emite cambios de dominio.
    try {
      const off1 = erplora().on('supplier_invoices.invoice.created', () => this.refresh());
      const off2 = erplora().on('supplier_invoices.invoice.validated', () => this.refresh());
      const off3 = erplora().on('supplier_invoices.invoice.paid', () => this.refresh());
      const off4 = erplora().on('supplier_invoices.invoice.cancelled', () => this.refresh());
      this.unsub = () => {
        off1();
        off2();
        off3();
        off4();
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
      const rows = await erplora().query<Invoice[]>('supplier_invoices.invoices.list');
      this.invoices = rows ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando facturas';
    } finally {
      this.loading = false;
    }
  }

  private async createInvoice(ev: Event) {
    ev.preventDefault();
    if (!this.newSupplier.trim() || !this.newNumber.trim() || !this.newDesc.trim()) return;
    this.saving = true;
    try {
      await erplora().command('supplier_invoices.invoices.create', {
        supplier_name: this.newSupplier.trim(),
        invoice_number: this.newNumber.trim(),
        supplier_tax_id: '',
        invoice_date: null,
        due_date: null,
        purchase_order_ref: '',
        tax_amount: '0.00',
        notes: '',
        lines: [
          {
            description: this.newDesc.trim(),
            quantity: Number(this.newQty) || 1,
            unit_price: Number(this.newPrice) || 0,
          },
        ],
      });
      this.newSupplier = '';
      this.newNumber = '';
      this.newDesc = '';
      this.newQty = '1';
      this.newPrice = '';
      await this.refresh(); // (además del evento; garantiza refresco inmediato)
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear la factura';
    } finally {
      this.saving = false;
    }
  }

  private async transition(name: string, invoice_id: string, extra: Record<string, unknown> = {}) {
    this.error = '';
    try {
      await erplora().command(name, { invoice_id, ...extra });
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo actualizar la factura';
    }
  }

  // Despacha el botón de fila del DataTable según el estado de la factura.
  private onRowAction(ev: CustomEvent<{ actionId: string; row: Record<string, unknown> }>) {
    const { actionId, row } = ev.detail;
    const inv = row as unknown as Invoice;
    if (actionId === 'validate' && inv.status === 'pending') {
      this.transition('supplier_invoices.invoices.validate', inv.id);
    } else if (actionId === 'mark_paid' && inv.status === 'validated') {
      this.transition('supplier_invoices.invoices.mark_paid', inv.id, {
        payment_date: new Date().toISOString().slice(0, 10),
      });
    } else if (actionId === 'cancel' && inv.status !== 'paid' && inv.status !== 'cancelled') {
      this.transition('supplier_invoices.invoices.cancel', inv.id, { reason: '' });
    }
  }

  private get filtered(): Invoice[] {
    if (!this.statusFilter) return this.invoices;
    return this.invoices.filter((i) => i.status === this.statusFilter);
  }

  render() {
    return (
      <div>
        <header>
          <h2>Facturas de proveedor</h2>
          <ion-select
            placeholder="Todos los estados"
            value={this.statusFilter}
            onIonChange={(e: any) => (this.statusFilter = e.target.value)}
          >
            <ion-select-option value="">Todos los estados</ion-select-option>
            <ion-select-option value="pending">Pendiente</ion-select-option>
            <ion-select-option value="validated">Validada</ion-select-option>
            <ion-select-option value="paid">Pagada</ion-select-option>
            <ion-select-option value="cancelled">Cancelada</ion-select-option>
          </ion-select>
        </header>

        <form class="form" onSubmit={(e) => this.createInvoice(e)}>
          <ion-input
            placeholder="Proveedor"
            value={this.newSupplier}
            onIonInput={(e: any) => (this.newSupplier = e.target.value)}
          />
          <ion-input
            placeholder="Nº factura"
            value={this.newNumber}
            onIonInput={(e: any) => (this.newNumber = e.target.value)}
          />
          <ion-input
            placeholder="Concepto"
            value={this.newDesc}
            onIonInput={(e: any) => (this.newDesc = e.target.value)}
          />
          <ion-input
            type="number"
            step="0.001"
            placeholder="Cant."
            value={this.newQty}
            onIonInput={(e: any) => (this.newQty = e.target.value)}
          />
          <ion-input
            type="number"
            step="0.01"
            placeholder="Precio"
            value={this.newPrice}
            onIonInput={(e: any) => (this.newPrice = e.target.value)}
          />
          <ion-button
            type="submit"
            size="small"
            disabled={this.saving || !this.newSupplier || !this.newNumber || !this.newDesc}
          >
            {this.saving ? 'Guardando…' : 'Añadir'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.filtered as unknown as Record<string, unknown>[]}
          actions={this.actions}
          searchKeys={['supplier_name', 'invoice_number']}
          searchPlaceholder="Buscar proveedor o nº…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin facturas.'}
          onRowAction={(e: CustomEvent<{ actionId: string; row: Record<string, unknown> }>) => this.onRowAction(e)}
        />
      </div>
    );
  }
}
