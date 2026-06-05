import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `fiscal_germany` (vista ZUGFeRD). Mini-app: lista de
// documentos ZUGFeRD (factura híbrida PDF/A-3 + XML B2B) + alta rápida de borrador.
// Es una de las piezas `ui.entry` que el shell carga en runtime.
//
// La autonumeración y el ensamblado del PDF/A-3 viven en WASM. Este componente NO
// toca la BD: llama al SDK (erplora.query/command/on).

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface ZugferdDoc {
  id: string;
  document_number: string;
  invoice_ref: string;
  supplier_ust_id: string;
  customer_name: string;
  total_netto: string;
  total_brutto: string;
  profile: string;
  pdf_a3_path: string;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-fiscal-germany-zugferd',
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
export class ErpFiscalGermanyZugferd {
  @State() docs: ZugferdDoc[] = [];
  @State() loading = true;
  @State() error = '';
  @State() saving = false;
  @State() newInvoiceRef = '';
  @State() newSupplier = '';
  @State() newCustomer = '';
  @State() newNetto = '';
  @State() newBrutto = '';
  @State() newProfile = 'comfort';

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'document_number', header: 'Nº documento' },
    { key: 'customer_name', header: 'Cliente' },
    { key: 'profile', header: 'Perfil' },
    { key: 'total_brutto', header: 'Bruto', align: 'right', format: (r) => Number(r.total_brutto).toFixed(2) },
    { key: 'pdf_a3_path', header: 'PDF/A-3', format: (r) => ((r.pdf_a3_path as string) ? 'Sí' : '—') },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off = erplora().on('fiscal_germany.zugferd.created', () => this.refresh());
      this.unsub = () => off();
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
      const docs = await erplora().query<ZugferdDoc[]>('fiscal_germany.zugferd.list', {
        profile: '',
        limit: 100,
      });
      this.docs = docs ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando ZUGFeRD';
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
      await erplora().command('fiscal_germany.zugferd.create', {
        invoice_ref: this.newInvoiceRef.trim(),
        supplier_ust_id: this.newSupplier.trim().toUpperCase(),
        customer_name: this.newCustomer.trim(),
        total_netto: this.newNetto.trim() || '0.00',
        total_brutto: this.newBrutto.trim() || '0.00',
        profile: this.newProfile,
      });
      this.newInvoiceRef = '';
      this.newSupplier = '';
      this.newCustomer = '';
      this.newNetto = '';
      this.newBrutto = '';
      this.newProfile = 'comfort';
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
          <h2>ZUGFeRD (B2B)</h2>
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
            placeholder="Cliente"
            value={this.newCustomer}
            onIonInput={(e: any) => (this.newCustomer = e.target.value)}
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
            placeholder="Bruto"
            value={this.newBrutto}
            onIonInput={(e: any) => (this.newBrutto = e.target.value)}
          />
          <ion-select
            placeholder="Perfil…"
            value={this.newProfile}
            onIonChange={(e: any) => (this.newProfile = e.target.value)}
          >
            <ion-select-option value="basic">basic</ion-select-option>
            <ion-select-option value="comfort">comfort</ion-select-option>
            <ion-select-option value="extended">extended</ion-select-option>
          </ion-select>
          <ion-button type="submit" size="small" disabled={this.saving || !this.newSupplier || !this.newCustomer}>
            {this.saving ? 'Guardando…' : 'Crear borrador'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.docs as unknown as Record<string, unknown>[]}
          searchKeys={['document_number', 'customer_name', 'supplier_ust_id']}
          searchPlaceholder="Buscar nº o cliente…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin documentos ZUGFeRD.'}
        />
      </div>
    );
  }
}
