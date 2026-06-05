import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `credit_notes` (Stencil). Mini-app: lista de notas de abono
// (abonos) con filtro por dirección/estado + alta rápida de una nota draft de una sola línea.
// Es la pieza `ui.entry` que el shell carga en runtime (modules/credit_notes/dist/credit_notes.esm.js).
//
// El componente NO toca la BD: llama al SDK (erplora.query/command/on). Toda escritura la
// valida y ejecuta el runtime (Tier 0 SQL + handlers WASM Tier 2: número atómico, batch de
// líneas, recálculo de total, validación de crédito restante). El cliente se obtiene de
// `globalThis.erplora` (lo monta el shell en el boot). El listado usa el DataTable
// compartido + los formularios usan elementos Ionic.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface CreditNote {
  id: string;
  credit_note_number: string;
  direction: string;
  counterparty_name: string;
  total_amount: number;
  applied_amount: number;
  status: string;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-credit-notes-list',
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
export class ErpCreditNotesList {
  @State() notes: CreditNote[] = [];
  @State() loading = true;
  @State() error = '';
  @State() filterDirection = '';
  @State() filterStatus = '';
  @State() newCounterparty = '';
  @State() newDescription = '';
  @State() newAmount = '';
  @State() newDirection = 'issued_to_customer';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'credit_note_number', header: 'Número' },
    { key: 'counterparty_name', header: 'Contraparte' },
    { key: 'total_amount', header: 'Total', align: 'right', format: (r) => Number(r.total_amount).toFixed(2) },
    { key: 'applied_amount', header: 'Aplicado', align: 'right', format: (r) => Number(r.applied_amount).toFixed(2) },
    { key: 'status', header: 'Estado' },
  ];

  async componentWillLoad() {
    await this.refresh();
    // Reactividad: recargamos al crear/emitir/aplicar/cancelar notas (eventos de dominio vía SDK/WS).
    try {
      const offs = [
        erplora().on('credit_notes.note.created', () => this.refresh()),
        erplora().on('credit_notes.note.issued', () => this.refresh()),
        erplora().on('credit_notes.note.applied', () => this.refresh()),
        erplora().on('credit_notes.note.unapplied', () => this.refresh()),
        erplora().on('credit_notes.note.cancelled', () => this.refresh()),
      ];
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
      const rows = await erplora().query<CreditNote[]>('credit_notes.notes.list', {
        direction: this.filterDirection,
        status: this.filterStatus,
        counterparty_name: '',
        limit: 50,
      });
      this.notes = rows ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando notas de abono';
    } finally {
      this.loading = false;
    }
  }

  private async createNote(ev: Event) {
    ev.preventDefault();
    if (!this.newCounterparty.trim() || !this.newDescription.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      // El handler WASM genera el número atómico, calcula line_total y total_amount.
      await erplora().command('credit_notes.notes.create', {
        direction: this.newDirection,
        counterparty_name: this.newCounterparty.trim(),
        counterparty_tax_id: '',
        original_invoice_ref: '',
        reason: '',
        issue_date: null,
        tax_amount: '0.00',
        notes: '',
        lines: [
          {
            description: this.newDescription.trim(),
            quantity: '1',
            unit_price: this.newAmount || '0',
            tax_rate: '0',
          },
        ],
      });
      this.newCounterparty = '';
      this.newDescription = '';
      this.newAmount = '';
      await this.refresh(); // (además del evento; garantiza refresco inmediato)
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear la nota';
    } finally {
      this.saving = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Notas de abono</h2>
          <ion-select
            placeholder="Todas las direcciones"
            value={this.filterDirection}
            onIonChange={(e: any) => {
              this.filterDirection = e.target.value;
              this.refresh();
            }}
          >
            <ion-select-option value="">Todas las direcciones</ion-select-option>
            <ion-select-option value="issued_to_customer">A clientes</ion-select-option>
            <ion-select-option value="received_from_supplier">De proveedores</ion-select-option>
          </ion-select>
          <ion-select
            placeholder="Todos los estados"
            value={this.filterStatus}
            onIonChange={(e: any) => {
              this.filterStatus = e.target.value;
              this.refresh();
            }}
          >
            <ion-select-option value="">Todos los estados</ion-select-option>
            <ion-select-option value="draft">Borrador</ion-select-option>
            <ion-select-option value="issued">Emitida</ion-select-option>
            <ion-select-option value="applied">Aplicada</ion-select-option>
            <ion-select-option value="cancelled">Cancelada</ion-select-option>
          </ion-select>
        </header>

        <form class="form" onSubmit={(e) => this.createNote(e)}>
          <ion-select
            placeholder="Dirección"
            value={this.newDirection}
            onIonChange={(e: any) => (this.newDirection = e.target.value)}
          >
            <ion-select-option value="issued_to_customer">A cliente</ion-select-option>
            <ion-select-option value="received_from_supplier">De proveedor</ion-select-option>
          </ion-select>
          <ion-input
            placeholder="Contraparte"
            value={this.newCounterparty}
            onIonInput={(e: any) => (this.newCounterparty = e.target.value)}
          />
          <ion-input
            placeholder="Concepto"
            value={this.newDescription}
            onIonInput={(e: any) => (this.newDescription = e.target.value)}
          />
          <ion-input
            type="number"
            step="0.01"
            placeholder="Importe"
            value={this.newAmount}
            onIonInput={(e: any) => (this.newAmount = e.target.value)}
          />
          <ion-button
            type="submit"
            size="small"
            disabled={this.saving || !this.newCounterparty || !this.newDescription}
          >
            {this.saving ? 'Guardando…' : 'Nueva nota'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.notes as unknown as Record<string, unknown>[]}
          searchKeys={['credit_note_number', 'counterparty_name']}
          searchPlaceholder="Buscar número o contraparte…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin notas de abono.'}
        />
      </div>
    );
  }
}
