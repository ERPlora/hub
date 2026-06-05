import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `fiscal_france` — vista Factur-X. Mini-app: lista de
// documentos Factur-X (PDF/A-3 + ZUGFeRD) con su estado + alta rápida de un draft.
// Es la pieza `ui.entry` que el shell carga en runtime.
//
// La lógica fiscal (validación SIRET, cálculo TTC, numeración, serialización XML,
// transiciones de estado) vive en Rust/WASM: este componente NO toca la BD; solo
// llama al SDK (erplora.query/command/on). El listado usa el DataTable compartido.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface FacturXDoc {
  id: string;
  document_number: string;
  invoice_ref: string;
  supplier_siret: string;
  customer_siret: string;
  total_amount_ht: string;
  vat_amount: string;
  total_amount_ttc: string;
  status: string;
  submission_date: string | null;
  created_at: string | null;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-fiscal-france-facturx',
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
export class ErpFiscalFranceFacturx {
  @State() docs: FacturXDoc[] = [];
  @State() loading = true;
  @State() error = '';
  @State() saving = false;
  @State() newSupplier = '';
  @State() newCustomer = '';
  @State() newHt = '';
  @State() newVat = '';
  @State() newRef = '';

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'document_number', header: 'Nº documento' },
    { key: 'supplier_siret', header: 'SIRET emisor' },
    { key: 'customer_siret', header: 'SIRET receptor' },
    { key: 'total_amount_ttc', header: 'Total TTC', align: 'right', format: (r) => Number(r.total_amount_ttc).toFixed(2) },
    { key: 'status', header: 'Estado' },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const offs = [
        erplora().on('fiscal_france.facturx.created', () => this.refresh()),
        erplora().on('fiscal_france.facturx.generated', () => this.refresh()),
        erplora().on('fiscal_france.facturx.submitted', () => this.refresh()),
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
      const docs = await erplora().query<FacturXDoc[]>('fiscal_france.facturx.list', { status: '', limit: 100 });
      this.docs = docs ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando documentos Factur-X';
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
      await erplora().command('fiscal_france.facturx.create', {
        invoice_ref: this.newRef.trim(),
        supplier_siret: this.newSupplier.trim(),
        customer_siret: this.newCustomer.trim(),
        total_amount_ht: this.newHt.trim() || '0',
        vat_amount: this.newVat.trim() || '0',
      });
      this.newSupplier = '';
      this.newCustomer = '';
      this.newHt = '';
      this.newVat = '';
      this.newRef = '';
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
          <h2>Documentos Factur-X</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createDoc(e)}>
          <ion-input
            placeholder="SIRET emisor (14)"
            value={this.newSupplier}
            onIonInput={(e: any) => (this.newSupplier = e.target.value)}
          />
          <ion-input
            placeholder="SIRET receptor (14)"
            value={this.newCustomer}
            onIonInput={(e: any) => (this.newCustomer = e.target.value)}
          />
          <ion-input
            type="number"
            step="0.01"
            placeholder="Base HT"
            value={this.newHt}
            onIonInput={(e: any) => (this.newHt = e.target.value)}
          />
          <ion-input
            type="number"
            step="0.01"
            placeholder="IVA"
            value={this.newVat}
            onIonInput={(e: any) => (this.newVat = e.target.value)}
          />
          <ion-input
            placeholder="Ref factura (opcional)"
            value={this.newRef}
            onIonInput={(e: any) => (this.newRef = e.target.value)}
          />
          <ion-button type="submit" size="small" disabled={this.saving || !this.newSupplier || !this.newCustomer}>
            {this.saving ? 'Guardando…' : 'Crear draft'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.docs as unknown as Record<string, unknown>[]}
          searchKeys={['document_number', 'supplier_siret', 'customer_siret']}
          searchPlaceholder="Buscar nº o SIRET…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin documentos Factur-X.'}
        />
      </div>
    );
  }
}
