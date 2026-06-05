import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn, DataTableAction } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `fiscal_portugal` (vista SAF-T PT). Mini-app: lista de
// exports SAF-T PT del hub + generación rápida de un export para un período.
// Es una de las piezas que el shell carga desde modules/fiscal_portugal/dist/.
//
// Toda la lógica fiscal (autonumeración SAFT-YYYYMMDD-NNNN, totales, XML SAF-T PT)
// vive en el handler WASM — este componente NO toca la BD; llama al SDK
// (erplora.query/command/on). El listado usa el DataTable compartido + Ionic.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface SaftExport {
  id: string;
  document_number: string;
  period_start: string;
  period_end: string;
  period_type: string;
  total_invoices: number;
  total_amount: string;
  status: string;
  generated_at: string | null;
  submitted_at: string | null;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-fiscal-portugal-saft',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .form { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; }
    .form ion-input, .form ion-select { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:9rem; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpFiscalPortugalSaft {
  @State() exports: SaftExport[] = [];
  @State() loading = true;
  @State() error = '';
  @State() statusFilter = '';
  @State() newStart = '';
  @State() newEnd = '';
  @State() newType = 'monthly';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'document_number', header: 'Documento' },
    { key: 'period_type', header: 'Tipo' },
    { key: 'period_start', header: 'Desde' },
    { key: 'period_end', header: 'Hasta' },
    { key: 'total_invoices', header: 'Facturas', align: 'right' },
    { key: 'total_amount', header: 'Total', align: 'right', format: (r) => Number(r.total_amount).toFixed(2) },
    { key: 'status', header: 'Estado' },
  ];

  private actions: DataTableAction[] = [{ id: 'submit', label: 'Enviar a AT', color: 'primary' }];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('fiscal_portugal.saft.generated', () => this.refresh());
      const off2 = erplora().on('fiscal_portugal.saft.submitted', () => this.refresh());
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
      const rows = await erplora().query<SaftExport[]>('fiscal_portugal.saft.list', {
        status: this.statusFilter,
      });
      this.exports = rows ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando exports SAF-T PT';
    } finally {
      this.loading = false;
    }
  }

  private async generate(ev: Event) {
    ev.preventDefault();
    if (!this.newStart || !this.newEnd) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('fiscal_portugal.saft.generate', {
        period_start: this.newStart,
        period_end: this.newEnd,
        period_type: this.newType,
        invoices_data: [],
      });
      this.newStart = '';
      this.newEnd = '';
      this.newType = 'monthly';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo generar el SAF-T PT';
    } finally {
      this.saving = false;
    }
  }

  private async submit(id: string) {
    this.error = '';
    try {
      await erplora().command('fiscal_portugal.saft.submit', { saft_id: id });
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo enviar el SAF-T PT';
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Exports SAF-T PT</h2>
        </header>

        <form class="form" onSubmit={(e) => this.generate(e)}>
          <ion-input
            type="date"
            placeholder="Desde"
            value={this.newStart}
            onIonInput={(e: any) => (this.newStart = e.target.value)}
          />
          <ion-input
            type="date"
            placeholder="Hasta"
            value={this.newEnd}
            onIonInput={(e: any) => (this.newEnd = e.target.value)}
          />
          <ion-select
            placeholder="Tipo…"
            value={this.newType}
            onIonChange={(e: any) => (this.newType = e.target.value)}
          >
            <ion-select-option value="monthly">Mensual</ion-select-option>
            <ion-select-option value="yearly">Anual</ion-select-option>
            <ion-select-option value="audit">Auditoría</ion-select-option>
          </ion-select>
          <ion-button type="submit" size="small" disabled={this.saving || !this.newStart || !this.newEnd}>
            {this.saving ? 'Generando…' : 'Generar'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.exports as unknown as Record<string, unknown>[]}
          searchKeys={['document_number', 'status', 'period_type']}
          searchPlaceholder="Buscar documento o estado…"
          actions={this.actions}
          onRowAction={(e: CustomEvent<{ actionId: string; row: Record<string, unknown> }>) => {
            const row = e.detail.row as unknown as SaftExport;
            if (e.detail.actionId === 'submit' && row?.status === 'generated') this.submit(row.id);
          }}
          emptyMessage={this.loading ? 'Cargando…' : 'Sin exports SAF-T PT.'}
        />
      </div>
    );
  }
}
