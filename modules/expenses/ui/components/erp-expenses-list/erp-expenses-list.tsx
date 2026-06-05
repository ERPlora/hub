import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `expenses` (Stencil). Mini-app: lista de gastos de empresa
// con filtro por estado + alta rápida (status inicial draft) + acciones de flujo
// (enviar / aprobar / rechazar). Es la pieza `ui.entry` que el shell carga en runtime
// (modules/expenses/dist/expenses.esm.js).
//
// El WC NUNCA toca la BD: lee con erplora.query y muta con erplora.command. La lógica
// de transición de estado vive en el handler WASM (ver WASM-TODO.md).

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface Expense {
  id: string;
  category_id: string;
  description: string;
  amount: string;
  expense_date: string;
  supplier_name: string;
  status: string;
  notes: string;
  approved_by: string | null;
  approved_at: string | null;
  rejection_reason: string;
}

interface ExpenseCategory {
  id: string;
  code: string;
  name: string;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-expenses-list',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .form { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; }
    .form ion-input, .form ion-select { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:8rem; }
    .filters { display:flex; gap:.5rem; align-items:center; margin-bottom:.5rem; }
    .actions { display:flex; gap:.25rem; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpExpensesList {
  @State() expenses: Expense[] = [];
  @State() categories: ExpenseCategory[] = [];
  @State() loading = true;
  @State() error = '';
  @State() statusFilter = '';
  @State() saving = false;
  @State() newCategory = '';
  @State() newDescription = '';
  @State() newAmount = '';
  @State() newDate = '';
  @State() newSupplier = '';

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'expense_date', header: 'Fecha' },
    { key: 'description', header: 'Concepto' },
    { key: 'category_id', header: 'Categoría', format: (r) => this.catName(r.category_id as string) },
    { key: 'supplier_name', header: 'Proveedor' },
    { key: 'amount', header: 'Importe', align: 'right', format: (r) => Number(r.amount).toFixed(2) },
    { key: 'status', header: 'Estado' },
    {
      key: 'id',
      header: 'Acciones',
      format: (r) => this.rowActions(r as unknown as Expense),
    },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('expenses.expense.created', () => this.refresh());
      const off2 = erplora().on('expenses.expense.submitted', () => this.refresh());
      const off3 = erplora().on('expenses.expense.approved', () => this.refresh());
      const off4 = erplora().on('expenses.expense.rejected', () => this.refresh());
      const off5 = erplora().on('expenses.category.created', () => this.refresh());
      this.unsub = () => {
        off1();
        off2();
        off3();
        off4();
        off5();
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
      const [expenses, cats] = await Promise.all([
        erplora().query<Expense[]>('expenses.expenses.list', {
          status: this.statusFilter,
          category_id: '',
        }),
        erplora().query<ExpenseCategory[]>('expenses.categories.list'),
      ]);
      this.expenses = expenses ?? [];
      this.categories = cats ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando gastos';
    } finally {
      this.loading = false;
    }
  }

  private async createExpense(ev: Event) {
    ev.preventDefault();
    if (!this.newDescription.trim() || !this.newCategory || !this.newAmount.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('expenses.expenses.create', {
        category_id: this.newCategory,
        description: this.newDescription.trim(),
        amount: this.newAmount.trim(),
        expense_date: this.newDate.trim(),
        supplier_name: this.newSupplier.trim(),
        notes: '',
      });
      this.newDescription = '';
      this.newAmount = '';
      this.newDate = '';
      this.newSupplier = '';
      this.newCategory = '';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear el gasto';
    } finally {
      this.saving = false;
    }
  }

  private async transition(name: string, payload: Record<string, unknown>) {
    this.error = '';
    try {
      await erplora().command(name, payload);
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo actualizar el gasto';
    }
  }

  private rowActions(e: Expense) {
    if (e.status === 'draft') {
      return (
        <span class="actions">
          <ion-button size="small" fill="outline" onClick={() => this.transition('expenses.expenses.submit', { expense_id: e.id })}>
            Enviar
          </ion-button>
        </span>
      );
    }
    if (e.status === 'submitted') {
      return (
        <span class="actions">
          <ion-button size="small" onClick={() => this.transition('expenses.expenses.approve', { expense_id: e.id })}>
            Aprobar
          </ion-button>
          <ion-button size="small" color="danger" fill="outline" onClick={() => this.rejectExpense(e.id)}>
            Rechazar
          </ion-button>
        </span>
      );
    }
    return <span>—</span>;
  }

  private async rejectExpense(id: string) {
    const reason = (globalThis as { prompt?: (m: string) => string | null }).prompt?.('Motivo del rechazo:') ?? '';
    if (!reason.trim()) return;
    await this.transition('expenses.expenses.reject', { expense_id: id, reason: reason.trim() });
  }

  private catName(id: string): string {
    return this.categories.find((c) => c.id === id)?.code ?? '—';
  }

  render() {
    return (
      <div>
        <header>
          <h2>Gastos</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createExpense(e)}>
          <ion-select
            placeholder="Categoría…"
            value={this.newCategory}
            onIonChange={(e: any) => (this.newCategory = e.target.value)}
          >
            {this.categories.map((c) => (
              <ion-select-option value={c.id} key={c.id}>
                {c.code}
              </ion-select-option>
            ))}
          </ion-select>
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
          <ion-input
            type="date"
            value={this.newDate}
            onIonInput={(e: any) => (this.newDate = e.target.value)}
          />
          <ion-input
            placeholder="Proveedor"
            value={this.newSupplier}
            onIonInput={(e: any) => (this.newSupplier = e.target.value)}
          />
          <ion-button
            type="submit"
            size="small"
            disabled={this.saving || !this.newDescription || !this.newCategory || !this.newAmount}
          >
            {this.saving ? 'Guardando…' : 'Añadir'}
          </ion-button>
        </form>

        <div class="filters">
          <ion-select
            placeholder="Todos los estados"
            value={this.statusFilter}
            onIonChange={(e: any) => {
              this.statusFilter = e.target.value;
              this.refresh();
            }}
          >
            <ion-select-option value="">Todos</ion-select-option>
            <ion-select-option value="draft">Borrador</ion-select-option>
            <ion-select-option value="submitted">Enviado</ion-select-option>
            <ion-select-option value="approved">Aprobado</ion-select-option>
            <ion-select-option value="rejected">Rechazado</ion-select-option>
          </ion-select>
        </div>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.expenses as unknown as Record<string, unknown>[]}
          searchKeys={['description', 'supplier_name']}
          searchPlaceholder="Buscar concepto o proveedor…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin gastos.'}
        />
      </div>
    );
  }
}
