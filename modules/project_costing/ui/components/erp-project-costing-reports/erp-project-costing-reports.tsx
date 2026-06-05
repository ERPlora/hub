import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `project_costing` — vista de informes/entradas de coste.
// Mini-app: lista de entradas de coste (con filtros) + alta rápida de coste y
// acciones de aprobación/rechazo. NO toca la BD: todo vía SDK.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface CostEntry {
  id: string;
  project_ref: string;
  entry_date: string | null;
  cost_type: string;
  description: string;
  amount: string;
  hours: string | null;
  employee_ref: string;
  supplier_ref: string;
  status: string;
  notes: string;
}

const COST_TYPES = ['labor', 'material', 'expense', 'subcontract', 'overhead'];

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-project-costing-reports',
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
export class ErpProjectCostingReports {
  @State() entries: CostEntry[] = [];
  @State() loading = true;
  @State() error = '';
  @State() projectFilter = '';
  @State() costTypeFilter = '';
  @State() statusFilter = 'approved';
  @State() newProjectRef = '';
  @State() newCostType = 'expense';
  @State() newAmount = '';
  @State() newDescription = '';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'entry_date', header: 'Fecha' },
    { key: 'project_ref', header: 'Proyecto' },
    { key: 'cost_type', header: 'Tipo' },
    { key: 'description', header: 'Descripción' },
    { key: 'amount', header: 'Importe', align: 'right', format: (r) => Number(r.amount).toFixed(2) },
    { key: 'status', header: 'Estado' },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('project_costing.entry.recorded', () => this.refresh());
      const off2 = erplora().on('project_costing.entry.approved', () => this.refresh());
      const off3 = erplora().on('project_costing.entry.rejected', () => this.refresh());
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
      const entries = await erplora().query<CostEntry[]>('project_costing.entries.list', {
        project_ref: this.projectFilter,
        cost_type: this.costTypeFilter,
        status: this.statusFilter,
        limit: 200,
      });
      this.entries = entries ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando entradas de coste';
    } finally {
      this.loading = false;
    }
  }

  private async recordCost(ev: Event) {
    ev.preventDefault();
    if (!this.newProjectRef.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('project_costing.entries.record', {
        project_ref: this.newProjectRef.trim(),
        cost_type: this.newCostType,
        amount: Number(this.newAmount) || 0,
        description: this.newDescription.trim(),
        entry_date: null,
        hours: null,
        employee_ref: '',
        supplier_ref: '',
        notes: '',
      });
      this.newProjectRef = '';
      this.newAmount = '';
      this.newDescription = '';
      this.newCostType = 'expense';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo registrar el coste';
    } finally {
      this.saving = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Entradas de coste</h2>
          <ion-select
            placeholder="Estado…"
            value={this.statusFilter}
            onIonChange={(e: any) => {
              this.statusFilter = e.target.value;
              this.refresh();
            }}
          >
            <ion-select-option value="">Todos</ion-select-option>
            <ion-select-option value="pending">Pendiente</ion-select-option>
            <ion-select-option value="approved">Aprobado</ion-select-option>
            <ion-select-option value="rejected">Rechazado</ion-select-option>
          </ion-select>
        </header>

        <form class="form" onSubmit={(e) => this.recordCost(e)}>
          <ion-input
            placeholder="Proyecto (ref)"
            value={this.newProjectRef}
            onIonInput={(e: any) => (this.newProjectRef = e.target.value)}
          />
          <ion-select
            placeholder="Tipo…"
            value={this.newCostType}
            onIonChange={(e: any) => (this.newCostType = e.target.value)}
          >
            {COST_TYPES.map((t) => (
              <ion-select-option value={t} key={t}>
                {t}
              </ion-select-option>
            ))}
          </ion-select>
          <ion-input
            type="number"
            step="0.01"
            placeholder="Importe"
            value={this.newAmount}
            onIonInput={(e: any) => (this.newAmount = e.target.value)}
          />
          <ion-input
            placeholder="Descripción"
            value={this.newDescription}
            onIonInput={(e: any) => (this.newDescription = e.target.value)}
          />
          <ion-button type="submit" size="small" disabled={this.saving || !this.newProjectRef}>
            {this.saving ? 'Guardando…' : 'Registrar coste'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.entries as unknown as Record<string, unknown>[]}
          searchKeys={['project_ref', 'cost_type', 'description']}
          searchPlaceholder="Buscar proyecto, tipo o descripción…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin entradas de coste.'}
        />
      </div>
    );
  }
}
