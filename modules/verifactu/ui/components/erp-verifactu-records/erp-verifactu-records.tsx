import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `verifactu` (Stencil): lista de registros fiscales
// VeriFactu (alta/anulacion) con su estado de transmisión a la AEAT. Es la pieza
// de navegación `records`. El WC NO toca la BD: solo llama al SDK (erplora.query).
// VeriFactu es de solo lectura para visibilidad (RD 1007/2023: sin escrituras vía UI;
// la creación de registros la dispara el evento invoice.created → handler WASM).

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface VerifactuRecord {
  id: string;
  sequence_number: number;
  invoice_number: string;
  invoice_date: string;
  record_type: string;
  invoice_type: string;
  issuer_nif: string;
  issuer_name: string;
  total_amount: string;
  status: string;
  retry_count: number;
  aeat_csv: string;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-verifactu-records',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .filters { display:flex; gap:.5rem; flex-wrap:wrap; margin:.5rem 0 1rem; }
    .filters ion-select { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:10rem; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpVerifactuRecords {
  @State() records: VerifactuRecord[] = [];
  @State() loading = true;
  @State() error = '';
  @State() statusFilter = '';
  @State() typeFilter = '';

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'sequence_number', header: 'Seq', align: 'right' },
    { key: 'invoice_number', header: 'Factura' },
    { key: 'invoice_date', header: 'Fecha' },
    { key: 'record_type', header: 'Tipo' },
    { key: 'invoice_type', header: 'F.' },
    { key: 'issuer_name', header: 'Emisor' },
    { key: 'total_amount', header: 'Total', align: 'right', format: (r) => Number(r.total_amount).toFixed(2) },
    { key: 'status', header: 'Estado' },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('verifactu.record.created', () => this.refresh());
      const off2 = erplora().on('verifactu.record.transmitted', () => this.refresh());
      this.unsub = () => {
        off1();
        off2();
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
      const rows = await erplora().query<VerifactuRecord[]>('verifactu.records.list', {
        search: '',
        status: this.statusFilter,
        record_type: this.typeFilter,
        limit: 100,
      });
      this.records = rows ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando registros';
    } finally {
      this.loading = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Registros VeriFactu</h2>
        </header>

        <div class="filters">
          <ion-select
            placeholder="Estado…"
            value={this.statusFilter}
            onIonChange={(e: any) => {
              this.statusFilter = e.target.value;
              this.refresh();
            }}
          >
            <ion-select-option value="">Todos los estados</ion-select-option>
            <ion-select-option value="pending">Pendiente</ion-select-option>
            <ion-select-option value="transmitted">Transmitido</ion-select-option>
            <ion-select-option value="accepted">Aceptado</ion-select-option>
            <ion-select-option value="rejected">Rechazado</ion-select-option>
            <ion-select-option value="error">Error</ion-select-option>
            <ion-select-option value="retry">Reintento</ion-select-option>
          </ion-select>
          <ion-select
            placeholder="Tipo…"
            value={this.typeFilter}
            onIonChange={(e: any) => {
              this.typeFilter = e.target.value;
              this.refresh();
            }}
          >
            <ion-select-option value="">Alta y anulación</ion-select-option>
            <ion-select-option value="alta">Alta</ion-select-option>
            <ion-select-option value="anulacion">Anulación</ion-select-option>
          </ion-select>
        </div>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.records as unknown as Record<string, unknown>[]}
          searchKeys={['invoice_number', 'issuer_name', 'issuer_nif']}
          searchPlaceholder="Buscar factura, emisor o NIF…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin registros VeriFactu.'}
        />
      </div>
    );
  }
}
