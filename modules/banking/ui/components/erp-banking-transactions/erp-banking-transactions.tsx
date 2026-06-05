import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `banking` (Stencil). Mini-app: libro de apuntes bancarios
// del hub, filtrable por cuenta, + alta de apunte y conciliación. Es la vista
// `transactions` declarada en module.json.navigation.
//
// El alta de apunte (banking.transactions.add) es un command WASM: mantiene el saldo
// cacheado de la cuenta y dispara el invariant banking.balance_matches_movements en Rust.
// Este componente NO toca la BD; solo llama al SDK (erplora.query/command/on).

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface BankAccount {
  id: string;
  name: string;
  currency: string;
}

interface BankTransaction {
  id: string;
  account_id: string;
  transaction_date: string;
  value_date: string | null;
  amount: string;
  description: string;
  counterparty: string;
  reference: string;
  is_reconciled: number;
  reconciled_at: string | null;
  source: string;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-banking-transactions',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .filters, .form { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0; }
    .form { margin-bottom:1rem; }
    .form ion-input, .filters ion-select, .form ion-select { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:8rem; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpBankingTransactions {
  @State() transactions: BankTransaction[] = [];
  @State() accounts: BankAccount[] = [];
  @State() loading = true;
  @State() error = '';
  @State() filterAccount = '';
  @State() saving = false;
  @State() newAccount = '';
  @State() newDate = '';
  @State() newAmount = '';
  @State() newDescription = '';

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'transaction_date', header: 'Fecha' },
    { key: 'description', header: 'Concepto' },
    { key: 'counterparty', header: 'Contraparte' },
    { key: 'amount', header: 'Importe', align: 'right', format: (r) => Number(r.amount).toFixed(2) },
    { key: 'is_reconciled', header: 'Conciliado', format: (r) => (r.is_reconciled ? 'Sí' : 'No') },
  ];

  async componentWillLoad() {
    await this.loadAccounts();
    await this.refresh();
    try {
      const off1 = erplora().on('banking.transaction.added', () => this.refresh());
      const off2 = erplora().on('banking.transaction.reconciled', () => this.refresh());
      const off3 = erplora().on('banking.transaction.unreconciled', () => this.refresh());
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

  private async loadAccounts() {
    try {
      const accounts = await erplora().query<BankAccount[]>('banking.accounts.list', { active_only: '1' });
      this.accounts = accounts ?? [];
    } catch {
      this.accounts = [];
    }
  }

  private async refresh() {
    this.loading = true;
    this.error = '';
    try {
      const rows = await erplora().query<BankTransaction[]>('banking.transactions.list', {
        account_id: this.filterAccount,
        start_date: '',
        end_date: '',
        reconciled: '',
        limit: 100,
      });
      this.transactions = rows ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando apuntes bancarios';
    } finally {
      this.loading = false;
    }
  }

  private async onFilterChange(value: string) {
    this.filterAccount = value;
    await this.refresh();
  }

  private async addTransaction(ev: Event) {
    ev.preventDefault();
    if (!this.newAccount || !this.newDate || !this.newAmount.trim() || !this.newDescription.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('banking.transactions.add', {
        account_id: this.newAccount,
        transaction_date: this.newDate,
        value_date: null,
        amount: Number(this.newAmount) || 0,
        description: this.newDescription.trim(),
        counterparty: '',
        reference: '',
        source: 'manual',
      });
      this.newAmount = '';
      this.newDescription = '';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo añadir el apunte';
    } finally {
      this.saving = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Apuntes bancarios</h2>
        </header>

        <div class="filters">
          <ion-select
            placeholder="Todas las cuentas"
            value={this.filterAccount}
            onIonChange={(e: any) => this.onFilterChange(e.target.value)}
          >
            <ion-select-option value="">Todas las cuentas</ion-select-option>
            {this.accounts.map((a) => (
              <ion-select-option value={a.id} key={a.id}>
                {a.name}
              </ion-select-option>
            ))}
          </ion-select>
        </div>

        <form class="form" onSubmit={(e) => this.addTransaction(e)}>
          <ion-select
            placeholder="Cuenta…"
            value={this.newAccount}
            onIonChange={(e: any) => (this.newAccount = e.target.value)}
          >
            {this.accounts.map((a) => (
              <ion-select-option value={a.id} key={a.id}>
                {a.name}
              </ion-select-option>
            ))}
          </ion-select>
          <ion-input
            type="date"
            placeholder="Fecha"
            value={this.newDate}
            onIonInput={(e: any) => (this.newDate = e.target.value)}
          />
          <ion-input
            type="number"
            step="0.01"
            placeholder="Importe (+/-)"
            value={this.newAmount}
            onIonInput={(e: any) => (this.newAmount = e.target.value)}
          />
          <ion-input
            placeholder="Concepto"
            value={this.newDescription}
            onIonInput={(e: any) => (this.newDescription = e.target.value)}
          />
          <ion-button
            type="submit"
            size="small"
            disabled={this.saving || !this.newAccount || !this.newDate || !this.newAmount || !this.newDescription}
          >
            {this.saving ? 'Guardando…' : 'Añadir apunte'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.transactions as unknown as Record<string, unknown>[]}
          searchKeys={['description', 'counterparty', 'reference']}
          searchPlaceholder="Buscar concepto o contraparte…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin apuntes.'}
        />
      </div>
    );
  }
}
