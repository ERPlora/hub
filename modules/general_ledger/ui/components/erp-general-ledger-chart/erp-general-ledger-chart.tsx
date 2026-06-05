import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `general_ledger` (Stencil) — vista Chart.
// Mini-app: plan de cuentas extendido + centros de coste, con alta rápida de cuenta.
// NO toca la BD: llama al SDK (erplora.query/command/on). El listado usa el DataTable
// compartido + Ionic. La inferencia de normal_balance y validaciones viven en Rust.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface GLAccount {
  id: string;
  code: string;
  name: string;
  account_type: string;
  normal_balance: string;
  parent_id: string | null;
  is_summary: number;
  is_active: number;
  currency: string;
}

interface CostCenter {
  id: string;
  code: string;
  name: string;
  parent_id: string | null;
  is_active: number;
}

const ACCOUNT_TYPES = ['asset', 'liability', 'equity', 'income', 'expense'];

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-general-ledger-chart',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .form { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; }
    .form ion-input, .form ion-select { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:8rem; }
    section { margin-bottom:1.5rem; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpGeneralLedgerChart {
  @State() accounts: GLAccount[] = [];
  @State() costCenters: CostCenter[] = [];
  @State() loading = true;
  @State() error = '';
  @State() typeFilter = '';
  @State() newCode = '';
  @State() newName = '';
  @State() newType = 'asset';
  @State() saving = false;

  private unsub?: () => void;

  private accountColumns: DataTableColumn[] = [
    { key: 'code', header: 'Código' },
    { key: 'name', header: 'Nombre' },
    { key: 'account_type', header: 'Tipo' },
    { key: 'normal_balance', header: 'Saldo normal' },
    { key: 'is_summary', header: 'Agregadora', format: (r) => ((r.is_summary as number) ? 'Sí' : '') },
  ];

  private costCenterColumns: DataTableColumn[] = [
    { key: 'code', header: 'Código' },
    { key: 'name', header: 'Nombre' },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('general_ledger.account.created', () => this.refresh());
      const off2 = erplora().on('general_ledger.cost_center.created', () => this.refresh());
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
      const [accounts, centers] = await Promise.all([
        erplora().query<GLAccount[]>('general_ledger.accounts.list', {
          account_type: this.typeFilter,
          active_only: 1,
        }),
        erplora().query<CostCenter[]>('general_ledger.cost_centers.list', { active_only: 1 }),
      ]);
      this.accounts = accounts ?? [];
      this.costCenters = centers ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando el plan contable';
    } finally {
      this.loading = false;
    }
  }

  private async createAccount(ev: Event) {
    ev.preventDefault();
    if (!this.newCode.trim() || !this.newName.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('general_ledger.accounts.create', {
        code: this.newCode.trim(),
        name: this.newName.trim(),
        account_type: this.newType,
        parent_id: null,
        is_summary: false,
        currency: 'EUR',
      });
      this.newCode = '';
      this.newName = '';
      this.newType = 'asset';
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
          <h2>Plan contable</h2>
          <ion-select
            placeholder="Tipo…"
            value={this.typeFilter}
            onIonChange={(e: any) => {
              this.typeFilter = e.target.value;
              this.refresh();
            }}
          >
            <ion-select-option value="">Todos</ion-select-option>
            {ACCOUNT_TYPES.map((t) => (
              <ion-select-option value={t} key={t}>
                {t}
              </ion-select-option>
            ))}
          </ion-select>
        </header>

        <form class="form" onSubmit={(e) => this.createAccount(e)}>
          <ion-input
            placeholder="Código (570)"
            value={this.newCode}
            onIonInput={(e: any) => (this.newCode = e.target.value)}
          />
          <ion-input
            placeholder="Nombre (Caja)"
            value={this.newName}
            onIonInput={(e: any) => (this.newName = e.target.value)}
          />
          <ion-select
            placeholder="Tipo…"
            value={this.newType}
            onIonChange={(e: any) => (this.newType = e.target.value)}
          >
            {ACCOUNT_TYPES.map((t) => (
              <ion-select-option value={t} key={t}>
                {t}
              </ion-select-option>
            ))}
          </ion-select>
          <ion-button type="submit" size="small" disabled={this.saving || !this.newCode || !this.newName}>
            {this.saving ? 'Guardando…' : 'Añadir cuenta'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <section>
          <data-table
            columns={this.accountColumns}
            rows={this.accounts as unknown as Record<string, unknown>[]}
            searchKeys={['code', 'name', 'account_type']}
            searchPlaceholder="Buscar cuenta…"
            emptyMessage={this.loading ? 'Cargando…' : 'Sin cuentas.'}
          />
        </section>

        <header>
          <h2>Centros de coste</h2>
        </header>
        <section>
          <data-table
            columns={this.costCenterColumns}
            rows={this.costCenters as unknown as Record<string, unknown>[]}
            searchKeys={['code', 'name']}
            searchPlaceholder="Buscar centro de coste…"
            emptyMessage={this.loading ? 'Cargando…' : 'Sin centros de coste.'}
          />
        </section>
      </div>
    );
  }
}
