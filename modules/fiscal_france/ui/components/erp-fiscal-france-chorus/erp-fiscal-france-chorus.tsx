import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn, DataTableAction } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `fiscal_france` — vista Chorus Pro. Mini-app: lista de
// facturas B2G enviadas al portal Chorus Pro con su estado + alta rápida de un draft.
// Es la pieza `ui.entry` que el shell carga en runtime.
//
// La lógica (numeración atómica, parseo de importe, máquina de estados Chorus Pro,
// anomaly_code) vive en Rust/WASM: este componente NO toca la BD; solo llama al SDK.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface ChorusInvoice {
  id: string;
  document_number: string;
  invoice_ref: string;
  recipient_service_code: string;
  total_amount: string;
  status: string;
  upload_id: string;
  anomaly_code: string;
  created_at: string | null;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-fiscal-france-chorus',
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
export class ErpFiscalFranceChorus {
  @State() docs: ChorusInvoice[] = [];
  @State() loading = true;
  @State() error = '';
  @State() saving = false;
  @State() newServiceCode = '';
  @State() newAmount = '';
  @State() newRef = '';

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'document_number', header: 'Nº documento' },
    { key: 'recipient_service_code', header: 'Código servicio' },
    { key: 'total_amount', header: 'Total', align: 'right', format: (r) => Number(r.total_amount).toFixed(2) },
    { key: 'status', header: 'Estado' },
    { key: 'anomaly_code', header: 'Anomalía', format: (r) => (r.anomaly_code as string) || '—' },
  ];

  // Acción de fila: enviar a Chorus Pro (solo aplica a drafts; la guarda real la
  // hace el comando SQL en su WHERE status='draft').
  private actions: DataTableAction[] = [
    { id: 'submit', label: 'Enviar', icon: 'cloud-upload-outline', color: 'primary' },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const offs = [
        erplora().on('fiscal_france.chorus.created', () => this.refresh()),
        erplora().on('fiscal_france.chorus.uploaded', () => this.refresh()),
        erplora().on('fiscal_france.chorus.status_changed', () => this.refresh()),
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
      const docs = await erplora().query<ChorusInvoice[]>('fiscal_france.chorus.list', { status: '', limit: 100 });
      this.docs = docs ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando facturas Chorus Pro';
    } finally {
      this.loading = false;
    }
  }

  private async createInvoice(ev: Event) {
    ev.preventDefault();
    if (!this.newServiceCode.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('fiscal_france.chorus.create', {
        invoice_ref: this.newRef.trim(),
        recipient_service_code: this.newServiceCode.trim(),
        total_amount: this.newAmount.trim() || '0',
      });
      this.newServiceCode = '';
      this.newAmount = '';
      this.newRef = '';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear la factura';
    } finally {
      this.saving = false;
    }
  }

  private async onRowAction(ev: CustomEvent<{ actionId: string; row: Record<string, unknown> }>) {
    const doc = ev.detail.row as unknown as ChorusInvoice;
    if (ev.detail.actionId !== 'submit' || doc.status !== 'draft') return;
    this.error = '';
    try {
      await erplora().command('fiscal_france.chorus.submit', { chorus_id: doc.id });
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo enviar la factura';
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Facturas Chorus Pro</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createInvoice(e)}>
          <ion-input
            placeholder="Código servicio destinatario"
            value={this.newServiceCode}
            onIonInput={(e: any) => (this.newServiceCode = e.target.value)}
          />
          <ion-input
            type="number"
            step="0.01"
            placeholder="Total"
            value={this.newAmount}
            onIonInput={(e: any) => (this.newAmount = e.target.value)}
          />
          <ion-input
            placeholder="Ref factura (opcional)"
            value={this.newRef}
            onIonInput={(e: any) => (this.newRef = e.target.value)}
          />
          <ion-button type="submit" size="small" disabled={this.saving || !this.newServiceCode}>
            {this.saving ? 'Guardando…' : 'Crear draft'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.docs as unknown as Record<string, unknown>[]}
          searchKeys={['document_number', 'recipient_service_code']}
          searchPlaceholder="Buscar nº o código servicio…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin facturas Chorus Pro.'}
          actions={this.actions}
          onRowAction={(e: CustomEvent<{ actionId: string; row: Record<string, unknown> }>) => this.onRowAction(e)}
        />
      </div>
    );
  }
}
