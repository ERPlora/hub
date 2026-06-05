import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `workflows` (Stencil), vista `list`. Mini-app: lista de
// workflows del hub + alta rápida + activar/desactivar/ejecutar. Es la pieza `ui.entry`
// que el shell carga en runtime (modules/workflows/dist/workflows.esm.js).
//
// 90% de la lógica vive en Rust/WASM: este componente NO toca la BD; llama al SDK
// (erplora.query/command/on). El listado usa el DataTable compartido + Ionic.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface Workflow {
  id: string;
  name: string;
  description: string;
  trigger_type: string;
  is_active: number;
  total_runs: number;
  last_run_at: string | null;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

const TRIGGERS = ['manual', 'scheduled', 'event', 'webhook'];

@Component({
  tag: 'erp-workflows-list',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .form { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; }
    .form ion-input, .form ion-select { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:8rem; }
    .err { color:#d9480f; font-weight:600; }
    .actions { display:flex; gap:.35rem; }
  `,
})
export class ErpWorkflowsList {
  @State() workflows: Workflow[] = [];
  @State() loading = true;
  @State() error = '';
  @State() saving = false;
  @State() newName = '';
  @State() newTrigger = 'manual';

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'name', header: 'Nombre' },
    { key: 'trigger_type', header: 'Disparador' },
    {
      key: 'is_active',
      header: 'Estado',
      format: (r) => (Number(r.is_active) ? 'Activo' : 'Inactivo'),
    },
    { key: 'total_runs', header: 'Ejecuciones', align: 'right' },
    {
      key: 'id',
      header: 'Acciones',
      format: (r) => (Number(r.is_active) ? 'Activo — Ejecutar/Desactivar' : 'Inactivo — Activar'),
    },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('workflows.workflow.created', () => this.refresh());
      const off2 = erplora().on('workflows.workflow.updated', () => this.refresh());
      const off3 = erplora().on('workflows.workflow.activated', () => this.refresh());
      const off4 = erplora().on('workflows.workflow.deactivated', () => this.refresh());
      const off5 = erplora().on('workflows.workflow.deleted', () => this.refresh());
      const off6 = erplora().on('workflows.run.completed', () => this.refresh());
      this.unsub = () => {
        off1();
        off2();
        off3();
        off4();
        off5();
        off6();
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
      const rows = await erplora().query<Workflow[]>('workflows.workflows.list', {
        is_active: '',
        trigger_type: '',
        limit: 50,
      });
      this.workflows = rows ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando workflows';
    } finally {
      this.loading = false;
    }
  }

  private async createWorkflow(ev: Event) {
    ev.preventDefault();
    if (!this.newName.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      // Alta mínima: una acción noop manual. Las acciones/condiciones reales se
      // editan en una vista de detalle (fuera del MVP de esta lista).
      await erplora().command('workflows.workflows.create', {
        name: this.newName.trim(),
        description: '',
        trigger_type: this.newTrigger,
        trigger_config: {},
        conditions: [],
        actions: [{ type: 'noop', params: {} }],
        is_active: false,
      });
      this.newName = '';
      this.newTrigger = 'manual';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear el workflow';
    } finally {
      this.saving = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Workflows</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createWorkflow(e)}>
          <ion-input
            placeholder="Nombre del workflow"
            value={this.newName}
            onIonInput={(e: any) => (this.newName = e.target.value)}
          />
          <ion-select
            placeholder="Disparador…"
            value={this.newTrigger}
            onIonChange={(e: any) => (this.newTrigger = e.target.value)}
          >
            {TRIGGERS.map((t) => (
              <ion-select-option value={t} key={t}>
                {t}
              </ion-select-option>
            ))}
          </ion-select>
          <ion-button type="submit" size="small" disabled={this.saving || !this.newName}>
            {this.saving ? 'Guardando…' : 'Añadir'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.workflows as unknown as Record<string, unknown>[]}
          searchKeys={['name', 'trigger_type']}
          searchPlaceholder="Buscar workflow…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin workflows.'}
        />
      </div>
    );
  }
}
