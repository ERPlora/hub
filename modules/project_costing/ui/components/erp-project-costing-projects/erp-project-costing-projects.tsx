import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn, DataTableAction } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `project_costing` — vista de proyectos/presupuestos.
// Mini-app: lista de presupuestos de proyecto + alta rápida + acciones de
// ciclo de vida (aprobar/cerrar). NO toca la BD: todo vía SDK (erplora.query/command/on).

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface ProjectBudget {
  id: string;
  project_ref: string;
  budget_amount: string;
  currency: string;
  fiscal_year: number;
  status: string;
  approved_by_ref: string;
  approved_at: string | null;
  notes: string;
  created_at: string | null;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-project-costing-projects',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .form { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; }
    .form ion-input { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:8rem; }
    .err { color:#d9480f; font-weight:600; }
    .actions { display:flex; gap:.35rem; }
  `,
})
export class ErpProjectCostingProjects {
  @State() budgets: ProjectBudget[] = [];
  @State() loading = true;
  @State() error = '';
  @State() statusFilter = '';
  @State() newProjectRef = '';
  @State() newAmount = '';
  @State() newFiscalYear = '';
  @State() newCurrency = 'EUR';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'project_ref', header: 'Proyecto' },
    { key: 'fiscal_year', header: 'Año fiscal', align: 'right' },
    { key: 'budget_amount', header: 'Presupuesto', align: 'right', format: (r) => Number(r.budget_amount).toFixed(2) },
    { key: 'currency', header: 'Moneda' },
    { key: 'status', header: 'Estado' },
  ];

  // Botones por fila. El handler de rowAction decide qué transición aplica según
  // el estado real de la fila (draft→approve, active→close; en otros estados no-op).
  private actions: DataTableAction[] = [
    { id: 'approve', label: 'Aprobar', color: 'primary' },
    { id: 'close', label: 'Cerrar', color: 'medium' },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('project_costing.budget.created', () => this.refresh());
      const off2 = erplora().on('project_costing.budget.approved', () => this.refresh());
      const off3 = erplora().on('project_costing.budget.closed', () => this.refresh());
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

  private async refresh() {
    this.loading = true;
    this.error = '';
    try {
      const budgets = await erplora().query<ProjectBudget[]>('project_costing.budgets.list', {
        project_ref: '',
        status: this.statusFilter,
      });
      this.budgets = budgets ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando presupuestos';
    } finally {
      this.loading = false;
    }
  }

  private async createBudget(ev: Event) {
    ev.preventDefault();
    if (!this.newProjectRef.trim() || !this.newFiscalYear) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('project_costing.budgets.create', {
        project_ref: this.newProjectRef.trim(),
        budget_amount: Number(this.newAmount) || 0,
        fiscal_year: Number(this.newFiscalYear) || 0,
        currency: (this.newCurrency || 'EUR').toUpperCase(),
        notes: '',
      });
      this.newProjectRef = '';
      this.newAmount = '';
      this.newFiscalYear = '';
      this.newCurrency = 'EUR';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear el presupuesto';
    } finally {
      this.saving = false;
    }
  }

  private async approve(id: string) {
    await this.runAction('project_costing.budgets.approve', { budget_id: id });
  }

  private async close(id: string) {
    await this.runAction('project_costing.budgets.close', { budget_id: id });
  }

  private async runAction(name: string, payload: Record<string, unknown>) {
    this.error = '';
    try {
      await erplora().command(name, payload);
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Acción fallida';
    }
  }

  private onRowAction = (ev: CustomEvent<{ actionId: string; row: Record<string, unknown> }>) => {
    const b = ev.detail?.row as unknown as ProjectBudget;
    if (!b) return;
    if (ev.detail.actionId === 'approve' && b.status === 'draft') this.approve(b.id);
    else if (ev.detail.actionId === 'close' && b.status === 'active') this.close(b.id);
  };

  render() {
    return (
      <div>
        <header>
          <h2>Presupuestos de proyecto</h2>
          <ion-select
            placeholder="Estado…"
            value={this.statusFilter}
            onIonChange={(e: any) => {
              this.statusFilter = e.target.value;
              this.refresh();
            }}
          >
            <ion-select-option value="">Todos</ion-select-option>
            <ion-select-option value="draft">Borrador</ion-select-option>
            <ion-select-option value="active">Activo</ion-select-option>
            <ion-select-option value="closed">Cerrado</ion-select-option>
          </ion-select>
        </header>

        <form class="form" onSubmit={(e) => this.createBudget(e)}>
          <ion-input
            placeholder="Proyecto (ref)"
            value={this.newProjectRef}
            onIonInput={(e: any) => (this.newProjectRef = e.target.value)}
          />
          <ion-input
            type="number"
            step="0.01"
            placeholder="Importe"
            value={this.newAmount}
            onIonInput={(e: any) => (this.newAmount = e.target.value)}
          />
          <ion-input
            type="number"
            placeholder="Año fiscal"
            value={this.newFiscalYear}
            onIonInput={(e: any) => (this.newFiscalYear = e.target.value)}
          />
          <ion-input
            placeholder="Moneda (EUR)"
            value={this.newCurrency}
            onIonInput={(e: any) => (this.newCurrency = e.target.value)}
          />
          <ion-button type="submit" size="small" disabled={this.saving || !this.newProjectRef || !this.newFiscalYear}>
            {this.saving ? 'Guardando…' : 'Crear presupuesto'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.budgets as unknown as Record<string, unknown>[]}
          actions={this.actions}
          searchKeys={['project_ref', 'status']}
          searchPlaceholder="Buscar proyecto o estado…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin presupuestos.'}
          onRowAction={this.onRowAction}
        />
      </div>
    );
  }
}
