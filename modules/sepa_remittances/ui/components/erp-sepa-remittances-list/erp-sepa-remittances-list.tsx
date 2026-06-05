import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn, DataTableAction } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `sepa_remittances` (vista "list"). Mini-app: lista de remesas
// SEPA + filtros por estado/tipo + alta rápida de una transferencia (1 línea) + acciones
// "generar XML" y "marcar enviada". Es la pieza `ui.entry` que el shell carga en runtime
// (modules/sepa_remittances/dist/sepa_remittances.esm.js).
//
// La lógica de batch, totales, contador atómico (SEPA-YYYYMMDD-NNNN) y el XML pain.008/
// pain.001 vive en el handler WASM (ver WASM-TODO.md). Este componente NO toca la BD;
// solo recoge inputs y llama al SDK (erplora.query/command/on) de `globalThis.erplora`.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface Remittance {
  id: string;
  remittance_id: string;
  remittance_type: string;
  execution_date: string;
  total_amount: string;
  total_count: number;
  currency: string;
  status: string;
}

const STATUS_LABELS: Record<string, string> = {
  draft: 'Borrador',
  generated: 'Generada',
  sent: 'Enviada',
  processed: 'Procesada',
  rejected: 'Rechazada',
};

const TYPE_LABELS: Record<string, string> = {
  direct_debit: 'Adeudo directo',
  credit_transfer: 'Transferencia',
};

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-sepa-remittances-list',
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
export class ErpSepaRemittancesList {
  @State() remittances: Remittance[] = [];
  @State() loading = true;
  @State() error = '';
  @State() statusFilter = '';
  @State() typeFilter = '';
  // Alta rápida de una transferencia de 1 línea.
  @State() newExecDate = '';
  @State() newName = '';
  @State() newIban = '';
  @State() newAmount = '';
  @State() newConcept = '';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'remittance_id', header: 'Referencia' },
    { key: 'remittance_type', header: 'Tipo', format: (r) => TYPE_LABELS[r.remittance_type as string] ?? (r.remittance_type as string) },
    { key: 'execution_date', header: 'Ejecución' },
    { key: 'total_count', header: 'Líneas', align: 'right' },
    { key: 'total_amount', header: 'Importe', align: 'right', format: (r) => `${Number(r.total_amount).toFixed(2)} ${r.currency}` },
    { key: 'status', header: 'Estado', format: (r) => STATUS_LABELS[r.status as string] ?? (r.status as string) },
  ];

  private actions: DataTableAction[] = [
    { id: 'generate', label: 'Generar XML', color: 'primary' },
    { id: 'send', label: 'Marcar enviada', color: 'medium' },
  ];

  private onRowAction = (ev: CustomEvent<{ actionId: string; row: Record<string, unknown> }>) => {
    const { actionId, row } = ev.detail;
    const r = row as unknown as Remittance;
    if (actionId === 'generate' && r.status === 'draft') {
      this.generateXml(r);
    } else if (actionId === 'send' && r.status === 'generated') {
      this.markSent(r);
    }
  };

  async componentWillLoad() {
    await this.refresh();
    try {
      const events = [
        'sepa_remittances.remittance.created',
        'sepa_remittances.remittance.generated',
        'sepa_remittances.remittance.sent',
        'sepa_remittances.remittance.processed',
        'sepa_remittances.remittance.rejected',
      ];
      const offs = events.map((ev) => erplora().on(ev, () => this.refresh()));
      this.unsub = () => offs.forEach((off) => off());
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
      const rows = await erplora().query<Remittance[]>('sepa_remittances.remittances.list', {
        status: this.statusFilter,
        remittance_type: this.typeFilter,
        limit: 50,
      });
      this.remittances = rows ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando remesas';
    } finally {
      this.loading = false;
    }
  }

  private async onStatusChange(value: string) {
    this.statusFilter = value;
    await this.refresh();
  }

  private async onTypeChange(value: string) {
    this.typeFilter = value;
    await this.refresh();
  }

  private async createTransfer(ev: Event) {
    ev.preventDefault();
    if (!this.newExecDate || !this.newName.trim() || !this.newIban.trim() || !(Number(this.newAmount) > 0)) {
      return;
    }
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('sepa_remittances.remittances.create_credit_transfer', {
        execution_date: this.newExecDate,
        currency: 'EUR',
        notes: '',
        lines: [
          {
            counterparty_name: this.newName.trim(),
            counterparty_iban: this.newIban.trim().toUpperCase(),
            amount: Number(this.newAmount),
            concept: this.newConcept.trim(),
          },
        ],
      });
      this.newExecDate = '';
      this.newName = '';
      this.newIban = '';
      this.newAmount = '';
      this.newConcept = '';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear la remesa';
    } finally {
      this.saving = false;
    }
  }

  private async generateXml(r: Remittance) {
    this.error = '';
    try {
      await erplora().command('sepa_remittances.remittances.generate_xml', { remittance_id: r.id });
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo generar el XML';
    }
  }

  private async markSent(r: Remittance) {
    this.error = '';
    try {
      await erplora().command('sepa_remittances.remittances.mark_sent', { remittance_id: r.id });
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo marcar como enviada';
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Remesas SEPA</h2>
          <ion-select
            value={this.typeFilter}
            interface="popover"
            placeholder="Tipo"
            onIonChange={(e: any) => this.onTypeChange(e.target.value)}
          >
            <ion-select-option value="">Todos los tipos</ion-select-option>
            <ion-select-option value="direct_debit">Adeudo directo</ion-select-option>
            <ion-select-option value="credit_transfer">Transferencia</ion-select-option>
          </ion-select>
          <ion-select
            value={this.statusFilter}
            interface="popover"
            placeholder="Estado"
            onIonChange={(e: any) => this.onStatusChange(e.target.value)}
          >
            <ion-select-option value="">Todos</ion-select-option>
            <ion-select-option value="draft">Borrador</ion-select-option>
            <ion-select-option value="generated">Generada</ion-select-option>
            <ion-select-option value="sent">Enviada</ion-select-option>
            <ion-select-option value="processed">Procesada</ion-select-option>
            <ion-select-option value="rejected">Rechazada</ion-select-option>
          </ion-select>
        </header>

        <form class="form" onSubmit={(e) => this.createTransfer(e)}>
          <ion-input
            type="date"
            placeholder="Fecha ejecución"
            value={this.newExecDate}
            onIonInput={(e: any) => (this.newExecDate = e.target.value)}
          />
          <ion-input
            placeholder="Beneficiario"
            value={this.newName}
            onIonInput={(e: any) => (this.newName = e.target.value)}
          />
          <ion-input
            placeholder="IBAN beneficiario"
            value={this.newIban}
            onIonInput={(e: any) => (this.newIban = e.target.value)}
          />
          <ion-input
            type="number"
            step="0.01"
            placeholder="Importe"
            value={this.newAmount}
            onIonInput={(e: any) => (this.newAmount = e.target.value)}
          />
          <ion-input
            placeholder="Concepto"
            value={this.newConcept}
            onIonInput={(e: any) => (this.newConcept = e.target.value)}
          />
          <ion-button
            type="submit"
            size="small"
            disabled={this.saving || !this.newExecDate || !this.newName || !this.newIban || !(Number(this.newAmount) > 0)}
          >
            {this.saving ? 'Guardando…' : 'Nueva transferencia'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.remittances as unknown as Record<string, unknown>[]}
          actions={this.actions}
          onRowAction={this.onRowAction}
          searchKeys={['remittance_id', 'remittance_type']}
          searchPlaceholder="Buscar referencia o tipo…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin remesas.'}
        />
      </div>
    );
  }
}
