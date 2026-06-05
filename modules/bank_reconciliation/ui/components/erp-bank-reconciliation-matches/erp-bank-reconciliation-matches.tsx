import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn, DataTableAction } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `bank_reconciliation` (Stencil). Mini-app: lista de
// conciliaciones (matches) + alta manual + eliminación. Es una de las piezas `ui.entry`
// que el shell carga en runtime (modules/bank_reconciliation/dist/bank_reconciliation.esm.js).
//
// La lógica vive en Rust/WASM: este componente NO toca la BD; llama al SDK
// (erplora.query/command/on). El listado usa el DataTable compartido + Ionic.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface ReconMatch {
  id: string;
  statement_line_id: string;
  ledger_entry_ref: string;
  amount_matched: string;
  match_type: string;
  confidence_score: string;
  notes: string;
}

interface StatementLine {
  id: string;
  statement_id: string;
  amount: string;
  description: string;
  is_matched: number;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-bank-reconciliation-matches',
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
export class ErpBankReconciliationMatches {
  @State() matches: ReconMatch[] = [];
  @State() unmatched: StatementLine[] = [];
  @State() loading = true;
  @State() error = '';
  @State() newLine = '';
  @State() newLedgerRef = '';
  @State() newAmount = '';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'ledger_entry_ref', header: 'Apunte' },
    { key: 'amount_matched', header: 'Importe', align: 'right', format: (r) => Number(r.amount_matched).toFixed(2) },
    { key: 'match_type', header: 'Tipo' },
    { key: 'confidence_score', header: 'Confianza', align: 'right', format: (r) => Number(r.confidence_score).toFixed(3) },
    { key: 'notes', header: 'Notas' },
  ];

  private rowActions: DataTableAction[] = [{ id: 'remove', label: 'Eliminar', icon: 'trash-outline', color: 'danger' }];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('bank_reconciliation.match.created', () => this.refresh());
      const off2 = erplora().on('bank_reconciliation.match.removed', () => this.refresh());
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
      const [matches, unmatched] = await Promise.all([
        erplora().query<ReconMatch[]>('bank_reconciliation.matches.list', {
          match_type: '',
          statement_id: '',
          statement_line_id: '',
        }),
        erplora().query<StatementLine[]>('bank_reconciliation.lines.unmatched', {
          statement_id: '',
          limit: 100,
        }),
      ]);
      this.matches = matches ?? [];
      this.unmatched = unmatched ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando conciliaciones';
    } finally {
      this.loading = false;
    }
  }

  private async createMatch(ev: Event) {
    ev.preventDefault();
    if (!this.newLine || !this.newLedgerRef.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('bank_reconciliation.matches.create', {
        statement_line_id: this.newLine,
        ledger_entry_ref: this.newLedgerRef.trim(),
        amount_matched: Number(this.newAmount) || 0,
        match_type: 'manual',
        confidence_score: 1.0,
        notes: '',
      });
      this.newLine = '';
      this.newLedgerRef = '';
      this.newAmount = '';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear la conciliación';
    } finally {
      this.saving = false;
    }
  }

  private async removeMatch(id: string) {
    this.error = '';
    try {
      await erplora().command('bank_reconciliation.matches.remove', { match_id: id });
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo eliminar la conciliación';
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Conciliaciones</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createMatch(e)}>
          <ion-select
            placeholder="Línea sin conciliar…"
            value={this.newLine}
            onIonChange={(e: any) => (this.newLine = e.target.value)}
          >
            {this.unmatched.map((l) => (
              <ion-select-option value={l.id} key={l.id}>
                {`${Number(l.amount).toFixed(2)} · ${l.description || l.id.slice(0, 8)}`}
              </ion-select-option>
            ))}
          </ion-select>
          <ion-input
            placeholder="Ref. apunte"
            value={this.newLedgerRef}
            onIonInput={(e: any) => (this.newLedgerRef = e.target.value)}
          />
          <ion-input
            type="number"
            step="0.01"
            placeholder="Importe"
            value={this.newAmount}
            onIonInput={(e: any) => (this.newAmount = e.target.value)}
          />
          <ion-button type="submit" size="small" disabled={this.saving || !this.newLine || !this.newLedgerRef}>
            {this.saving ? 'Guardando…' : 'Conciliar'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.matches as unknown as Record<string, unknown>[]}
          searchKeys={['ledger_entry_ref', 'match_type']}
          searchPlaceholder="Buscar apunte o tipo…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin conciliaciones.'}
          actions={this.rowActions}
          onRowAction={(e: CustomEvent<{ actionId: string; row: Record<string, unknown> }>) => {
            if (e.detail.actionId === 'remove') this.removeMatch(e.detail.row.id as string);
          }}
        />
      </div>
    );
  }
}
