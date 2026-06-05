import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn, DataTableAction } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `bank_reconciliation` (Stencil). Mini-app: lista de extractos
// bancarios + alta rápida + cierre. Es una de las piezas `ui.entry` que el shell carga en
// runtime (modules/bank_reconciliation/dist/bank_reconciliation.esm.js).
//
// La lógica vive en Rust/WASM: este componente NO toca la BD; llama al SDK
// (erplora.query/command/on). El listado usa el DataTable compartido + Ionic.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface BankStatement {
  id: string;
  statement_number: string;
  bank_account_ref: string;
  statement_date: string | null;
  period_start: string | null;
  period_end: string | null;
  opening_balance: string;
  closing_balance: string;
  status: string;
  notes: string;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-bank-reconciliation-statements',
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
export class ErpBankReconciliationStatements {
  @State() statements: BankStatement[] = [];
  @State() loading = true;
  @State() error = '';
  @State() statusFilter = '';
  @State() newAccount = '';
  @State() newNumber = '';
  @State() newOpening = '';
  @State() newClosing = '';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'statement_number', header: 'Nº extracto' },
    { key: 'bank_account_ref', header: 'Cuenta' },
    { key: 'statement_date', header: 'Fecha', format: (r) => (r.statement_date as string) ?? '—' },
    { key: 'closing_balance', header: 'Saldo cierre', align: 'right', format: (r) => Number(r.closing_balance).toFixed(2) },
    { key: 'status', header: 'Estado' },
  ];

  private rowActions: DataTableAction[] = [{ id: 'close', label: 'Cerrar', icon: 'lock-closed-outline' }];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('bank_reconciliation.statement.created', () => this.refresh());
      const off2 = erplora().on('bank_reconciliation.statement.closed', () => this.refresh());
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
      const rows = await erplora().query<BankStatement[]>('bank_reconciliation.statements.list', {
        status: this.statusFilter,
        bank_account_ref: '',
        limit: 50,
      });
      this.statements = rows ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando extractos';
    } finally {
      this.loading = false;
    }
  }

  private async createStatement(ev: Event) {
    ev.preventDefault();
    if (!this.newAccount.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('bank_reconciliation.statements.create', {
        bank_account_ref: this.newAccount.trim(),
        statement_number: this.newNumber.trim(),
        statement_date: null,
        period_start: null,
        period_end: null,
        opening_balance: Number(this.newOpening) || 0,
        closing_balance: Number(this.newClosing) || 0,
        notes: '',
        lines: [],
      });
      this.newAccount = '';
      this.newNumber = '';
      this.newOpening = '';
      this.newClosing = '';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear el extracto';
    } finally {
      this.saving = false;
    }
  }

  private async closeStatement(id: string) {
    this.error = '';
    try {
      await erplora().command('bank_reconciliation.statements.close', { statement_id: id });
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo cerrar el extracto';
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Extractos bancarios</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createStatement(e)}>
          <ion-input
            placeholder="Cuenta (ES12...)"
            value={this.newAccount}
            onIonInput={(e: any) => (this.newAccount = e.target.value)}
          />
          <ion-input
            placeholder="Nº (opcional)"
            value={this.newNumber}
            onIonInput={(e: any) => (this.newNumber = e.target.value)}
          />
          <ion-input
            type="number"
            step="0.01"
            placeholder="Saldo inicial"
            value={this.newOpening}
            onIonInput={(e: any) => (this.newOpening = e.target.value)}
          />
          <ion-input
            type="number"
            step="0.01"
            placeholder="Saldo cierre"
            value={this.newClosing}
            onIonInput={(e: any) => (this.newClosing = e.target.value)}
          />
          <ion-button type="submit" size="small" disabled={this.saving || !this.newAccount}>
            {this.saving ? 'Guardando…' : 'Crear extracto'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.statements as unknown as Record<string, unknown>[]}
          searchKeys={['statement_number', 'bank_account_ref']}
          searchPlaceholder="Buscar nº o cuenta…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin extractos bancarios.'}
          actions={this.rowActions}
          onRowAction={(e: CustomEvent<{ actionId: string; row: Record<string, unknown> }>) => {
            if (e.detail.actionId === 'close') this.closeStatement(e.detail.row.id as string);
          }}
        />
      </div>
    );
  }
}
