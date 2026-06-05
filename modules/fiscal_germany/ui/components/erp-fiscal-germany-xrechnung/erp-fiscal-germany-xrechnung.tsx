import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `fiscal_germany` (vista XRechnung). Mini-app: lista de
// documentos XRechnung (factura electrónica B2G UBL 2.1) + alta rápida de borrador.
// Es una de las piezas `ui.entry` que el shell carga en runtime.
//
// Toda la lógica fiscal (autonumeración, generación de XML, validación, envío PEPPOL)
// vive en WASM. Este componente NO toca la BD: llama al SDK (erplora.query/command/on).

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface XRechnungDoc {
  id: string;
  document_number: string;
  invoice_ref: string;
  supplier_ust_id: string;
  customer_leitweg_id: string;
  total_netto: string;
  total_steuer: string;
  total_brutto: string;
  status: string;
  submission_date: string | null;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-fiscal-germany-xrechnung',
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
export class ErpFiscalGermanyXrechnung {
  @State() docs: XRechnungDoc[] = [];
  @State() loading = true;
  @State() error = '';
  @State() saving = false;
  @State() newInvoiceRef = '';
  @State() newSupplier = '';
  @State() newLeitweg = '';
  @State() newNetto = '';
  @State() newSteuer = '';

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'document_number', header: 'Nº documento' },
    { key: 'customer_leitweg_id', header: 'Leitweg-ID' },
    { key: 'supplier_ust_id', header: 'USt-IdNr proveedor' },
    { key: 'total_brutto', header: 'Bruto', align: 'right', format: (r) => Number(r.total_brutto).toFixed(2) },
    { key: 'status', header: 'Estado' },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('fiscal_germany.xrechnung.created', () => this.refresh());
      const off2 = erplora().on('fiscal_germany.xrechnung.validated', () => this.refresh());
      const off3 = erplora().on('fiscal_germany.xrechnung.submitted', () => this.refresh());
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
      const docs = await erplora().query<XRechnungDoc[]>('fiscal_germany.xrechnung.list', {
        status: '',
        limit: 100,
      });
      this.docs = docs ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando XRechnung';
    } finally {
      this.loading = false;
    }
  }

  private async createDoc(ev: Event) {
    ev.preventDefault();
    if (!this.newSupplier.trim() || !this.newLeitweg.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('fiscal_germany.xrechnung.create', {
        invoice_ref: this.newInvoiceRef.trim(),
        supplier_ust_id: this.newSupplier.trim().toUpperCase(),
        customer_leitweg_id: this.newLeitweg.trim(),
        total_netto: this.newNetto.trim() || '0.00',
        total_steuer: this.newSteuer.trim() || '0.00',
      });
      this.newInvoiceRef = '';
      this.newSupplier = '';
      this.newLeitweg = '';
      this.newNetto = '';
      this.newSteuer = '';
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
          <h2>XRechnung (B2G)</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createDoc(e)}>
          <ion-input
            placeholder="Ref. factura"
            value={this.newInvoiceRef}
            onIonInput={(e: any) => (this.newInvoiceRef = e.target.value)}
          />
          <ion-input
            placeholder="USt-IdNr (DE123456789)"
            value={this.newSupplier}
            onIonInput={(e: any) => (this.newSupplier = e.target.value)}
          />
          <ion-input
            placeholder="Leitweg-ID"
            value={this.newLeitweg}
            onIonInput={(e: any) => (this.newLeitweg = e.target.value)}
          />
          <ion-input
            type="number"
            step="0.01"
            placeholder="Neto"
            value={this.newNetto}
            onIonInput={(e: any) => (this.newNetto = e.target.value)}
          />
          <ion-input
            type="number"
            step="0.01"
            placeholder="Impuesto"
            value={this.newSteuer}
            onIonInput={(e: any) => (this.newSteuer = e.target.value)}
          />
          <ion-button type="submit" size="small" disabled={this.saving || !this.newSupplier || !this.newLeitweg}>
            {this.saving ? 'Guardando…' : 'Crear borrador'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.docs as unknown as Record<string, unknown>[]}
          searchKeys={['document_number', 'customer_leitweg_id', 'supplier_ust_id']}
          searchPlaceholder="Buscar nº o Leitweg-ID…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin documentos XRechnung.'}
        />
      </div>
    );
  }
}
