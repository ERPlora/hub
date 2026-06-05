import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `fiscal_italy` — vista FatturaPA. Mini-app: lista de
// documentos FatturaPA salientes (vía SdI) + alta rápida de un borrador.
// Es una de las piezas `ui.entry` que el shell carga en runtime
// (modules/fiscal_italy/dist/fiscal_italy.esm.js).
//
// El grueso de la lógica (auto-numeración FPA-YYYYMMDD-NNNN, generación de XML
// 1.2, transiciones de estado SdI) vive en Rust/WASM: este componente NO toca
// la BD; llama al SDK (erplora.query/command/on).

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface FatturaPADoc {
  id: string;
  document_number: string;
  invoice_ref: string;
  supplier_piva: string;
  customer_piva: string;
  customer_codice_destinatario: string;
  total_imponibile: string;
  total_iva: string;
  total_documento: string;
  status: string;
  sdi_id: string;
  submission_date: string | null;
  rejection_reason: string;
  created_at: string | null;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-fiscal-italy-fatturapa',
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
export class ErpFiscalItalyFatturapa {
  @State() docs: FatturaPADoc[] = [];
  @State() loading = true;
  @State() error = '';
  @State() statusFilter = '';
  @State() newInvoiceRef = '';
  @State() newSupplierPiva = '';
  @State() newCustomerPiva = '';
  @State() newImponibile = '';
  @State() newIva = '';
  @State() newCodiceDest = '';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'document_number', header: 'Documento' },
    { key: 'customer_piva', header: 'Cliente P.IVA' },
    { key: 'total_documento', header: 'Total', align: 'right', format: (r) => Number(r.total_documento).toFixed(2) },
    { key: 'status', header: 'Estado' },
    { key: 'sdi_id', header: 'SdI ID' },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('fiscal_italy.fatturapa.created', () => this.refresh());
      const off2 = erplora().on('fiscal_italy.fatturapa.submitted', () => this.refresh());
      const off3 = erplora().on('fiscal_italy.fatturapa.status_changed', () => this.refresh());
      const off4 = erplora().on('fiscal_italy.fatturapa.xml_generated', () => this.refresh());
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
      const docs = await erplora().query<FatturaPADoc[]>('fiscal_italy.fatturapa.list', {
        status: this.statusFilter,
      });
      this.docs = docs ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando documentos FatturaPA';
    } finally {
      this.loading = false;
    }
  }

  private async createDoc(ev: Event) {
    ev.preventDefault();
    if (!this.newSupplierPiva.trim() || !this.newCustomerPiva.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('fiscal_italy.fatturapa.create', {
        invoice_ref: this.newInvoiceRef.trim(),
        supplier_piva: this.newSupplierPiva.trim(),
        customer_piva: this.newCustomerPiva.trim(),
        customer_codice_destinatario: this.newCodiceDest.trim() || '0000000',
        total_imponibile: Number(this.newImponibile) || 0,
        total_iva: Number(this.newIva) || 0,
      });
      this.newInvoiceRef = '';
      this.newSupplierPiva = '';
      this.newCustomerPiva = '';
      this.newImponibile = '';
      this.newIva = '';
      this.newCodiceDest = '';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear el documento';
    } finally {
      this.saving = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>FatturaPA</h2>
          <ion-select
            placeholder="Estado…"
            value={this.statusFilter}
            onIonChange={(e: any) => {
              this.statusFilter = e.target.value;
              this.refresh();
            }}
          >
            <ion-select-option value="">Todos</ion-select-option>
            <ion-select-option value="draft">Borrador</ion-select-option>
            <ion-select-option value="uploaded">Enviado</ion-select-option>
            <ion-select-option value="delivered">Entregado</ion-select-option>
            <ion-select-option value="accepted">Aceptado</ion-select-option>
            <ion-select-option value="rejected">Rechazado</ion-select-option>
          </ion-select>
        </header>

        <form class="form" onSubmit={(e) => this.createDoc(e)}>
          <ion-input
            placeholder="Ref. factura"
            value={this.newInvoiceRef}
            onIonInput={(e: any) => (this.newInvoiceRef = e.target.value)}
          />
          <ion-input
            placeholder="Proveedor P.IVA"
            value={this.newSupplierPiva}
            onIonInput={(e: any) => (this.newSupplierPiva = e.target.value)}
          />
          <ion-input
            placeholder="Cliente P.IVA"
            value={this.newCustomerPiva}
            onIonInput={(e: any) => (this.newCustomerPiva = e.target.value)}
          />
          <ion-input
            placeholder="Codice Dest. (7)"
            value={this.newCodiceDest}
            onIonInput={(e: any) => (this.newCodiceDest = e.target.value)}
          />
          <ion-input
            type="number"
            step="0.01"
            placeholder="Imponibile"
            value={this.newImponibile}
            onIonInput={(e: any) => (this.newImponibile = e.target.value)}
          />
          <ion-input
            type="number"
            step="0.01"
            placeholder="IVA"
            value={this.newIva}
            onIonInput={(e: any) => (this.newIva = e.target.value)}
          />
          <ion-button
            type="submit"
            size="small"
            disabled={this.saving || !this.newSupplierPiva || !this.newCustomerPiva}
          >
            {this.saving ? 'Guardando…' : 'Nuevo borrador'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.docs as unknown as Record<string, unknown>[]}
          searchKeys={['document_number', 'customer_piva', 'supplier_piva']}
          searchPlaceholder="Buscar documento o P.IVA…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin documentos FatturaPA.'}
        />
      </div>
    );
  }
}
