import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `banking` (Stencil). Mini-app: lista de cuentas bancarias
// del hub + alta rápida. Es la vista `accounts` declarada en module.json.navigation.
//
// La lógica vive en Rust/WASM: este componente NO toca la BD; llama al SDK
// (erplora.query/command/on). El listado usa el DataTable compartido + Ionic.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface BankAccount {
  id: string;
  name: string;
  iban: string;
  bic: string;
  currency: string;
  opening_balance: string;
  current_balance: string;
  is_active: number;
  notes: string;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-banking-accounts',
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
export class ErpBankingAccounts {
  @State() accounts: BankAccount[] = [];
  @State() loading = true;
  @State() error = '';
  @State() saving = false;
  @State() newName = '';
  @State() newIban = '';
  @State() newCurrency = 'EUR';
  @State() newOpening = '';

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'name', header: 'Nombre' },
    { key: 'iban', header: 'IBAN' },
    { key: 'currency', header: 'Moneda' },
    { key: 'current_balance', header: 'Saldo', align: 'right', format: (r) => Number(r.current_balance).toFixed(2) },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('banking.account.created', () => this.refresh());
      const off2 = erplora().on('banking.transaction.added', () => this.refresh());
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
      const accounts = await erplora().query<BankAccount[]>('banking.accounts.list', { active_only: '1' });
      this.accounts = accounts ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando cuentas bancarias';
    } finally {
      this.loading = false;
    }
  }

  private async createAccount(ev: Event) {
    ev.preventDefault();
    if (!this.newName.trim() || !this.newIban.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('banking.accounts.create', {
        name: this.newName.trim(),
        iban: this.newIban.trim(),
        bic: '',
        currency: (this.newCurrency.trim() || 'EUR').toUpperCase(),
        opening_balance: Number(this.newOpening) || 0,
        notes: '',
      });
      this.newName = '';
      this.newIban = '';
      this.newCurrency = 'EUR';
      this.newOpening = '';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear la cuenta';
    } finally {
      this.saving = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Cuentas bancarias</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createAccount(e)}>
          <ion-input
            placeholder="Nombre"
            value={this.newName}
            onIonInput={(e: any) => (this.newName = e.target.value)}
          />
          <ion-input
            placeholder="IBAN"
            value={this.newIban}
            onIonInput={(e: any) => (this.newIban = e.target.value)}
          />
          <ion-input
            placeholder="Moneda (EUR)"
            value={this.newCurrency}
            onIonInput={(e: any) => (this.newCurrency = e.target.value)}
          />
          <ion-input
            type="number"
            step="0.01"
            placeholder="Saldo inicial"
            value={this.newOpening}
            onIonInput={(e: any) => (this.newOpening = e.target.value)}
          />
          <ion-button type="submit" size="small" disabled={this.saving || !this.newName || !this.newIban}>
            {this.saving ? 'Guardando…' : 'Añadir'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.accounts as unknown as Record<string, unknown>[]}
          searchKeys={['name', 'iban']}
          searchPlaceholder="Buscar nombre o IBAN…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin cuentas bancarias.'}
        />
      </div>
    );
  }
}
