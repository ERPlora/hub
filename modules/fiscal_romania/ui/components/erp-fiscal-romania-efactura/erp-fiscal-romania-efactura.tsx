import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `fiscal_romania` (vista e-Factura). Mini-app: lista de
// facturas electrónicas salientes a ANAF + alta rápida de un borrador. Es parte de
// la pieza `ui.entry` que el shell carga en runtime (dist/fiscal_romania.esm.js).
//
// El grueso de la lógica vive en Rust/WASM (auto-numeración EFR-..., generación de
// XML UBL 2.1, guardas de estado): este componente NO toca la BD; llama al SDK
// (erplora.query/command/on). El listado usa el DataTable compartido + Ionic.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface EFactura {
  id: string;
  document_number: string;
  invoice_ref: string;
  document_type: string;
  supplier_cif: string;
  customer_cif: string;
  total_amount: string;
  vat_amount: string;
  status: string;
  upload_id: string;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-fiscal-romania-efactura',
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
export class ErpFiscalRomaniaEfactura {
  @State() docs: EFactura[] = [];
  @State() loading = true;
  @State() error = '';
  @State() statusFilter = '';
  @State() newSupplier = '';
  @State() newCustomer = '';
  @State() newTotal = '';
  @State() newVat = '';
  @State() newType = 'invoice';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'document_number', header: 'Número' },
    { key: 'document_type', header: 'Tipo' },
    { key: 'customer_cif', header: 'Cliente CIF' },
    { key: 'total_amount', header: 'Total', align: 'right', format: (r) => Number(r.total_amount).toFixed(2) },
    { key: 'vat_amount', header: 'IVA', align: 'right', format: (r) => Number(r.vat_amount).toFixed(2) },
    { key: 'status', header: 'Estado' },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('fiscal_romania.efactura.created', () => this.refresh());
      const off2 = erplora().on('fiscal_romania.efactura.submitted', () => this.refresh());
      const off3 = erplora().on('fiscal_romania.efactura.validated', () => this.refresh());
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
      const docs = await erplora().query<EFactura[]>('fiscal_romania.efactura.list', {
        status: this.statusFilter,
        limit: 100,
      });
      this.docs = docs ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando e-Facturas';
    } finally {
      this.loading = false;
    }
  }

  private async createDoc(ev: Event) {
    ev.preventDefault();
    if (!this.newSupplier.trim() || !this.newCustomer.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('fiscal_romania.efactura.create', {
        invoice_ref: '',
        supplier_cif: this.newSupplier.trim(),
        customer_cif: this.newCustomer.trim(),
        total_amount: String(this.newTotal || '0.00'),
        vat_amount: String(this.newVat || '0.00'),
        document_type: this.newType,
      });
      this.newSupplier = '';
      this.newCustomer = '';
      this.newTotal = '';
      this.newVat = '';
      this.newType = 'invoice';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear la e-Factura';
    } finally {
      this.saving = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>e-Factura</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createDoc(e)}>
          <ion-input
            placeholder="CIF emisor (RO...)"
            value={this.newSupplier}
            onIonInput={(e: any) => (this.newSupplier = e.target.value)}
          />
          <ion-input
            placeholder="CIF cliente (RO...)"
            value={this.newCustomer}
            onIonInput={(e: any) => (this.newCustomer = e.target.value)}
          />
          <ion-input
            type="number"
            step="0.01"
            placeholder="Total"
            value={this.newTotal}
            onIonInput={(e: any) => (this.newTotal = e.target.value)}
          />
          <ion-input
            type="number"
            step="0.01"
            placeholder="IVA"
            value={this.newVat}
            onIonInput={(e: any) => (this.newVat = e.target.value)}
          />
          <ion-select
            placeholder="Tipo…"
            value={this.newType}
            onIonChange={(e: any) => (this.newType = e.target.value)}
          >
            <ion-select-option value="invoice">Factura</ion-select-option>
            <ion-select-option value="credit_note">Abono</ion-select-option>
          </ion-select>
          <ion-button type="submit" size="small" disabled={this.saving || !this.newSupplier || !this.newCustomer}>
            {this.saving ? 'Guardando…' : 'Nueva e-Factura'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.docs as unknown as Record<string, unknown>[]}
          searchKeys={['document_number', 'customer_cif', 'status']}
          searchPlaceholder="Buscar número, CIF o estado…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin e-Facturas.'}
        />
      </div>
    );
  }
}
