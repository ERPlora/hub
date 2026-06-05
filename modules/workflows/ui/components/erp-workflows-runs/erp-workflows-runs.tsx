import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `workflows` (Stencil), vista `runs`. Historial de
// ejecuciones del hub con filtro por estado. Es parte de la pieza `ui.entry`.
//
// El componente NO toca la BD; lee vía erplora.query y escucha eventos del SDK.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface WorkflowRun {
  id: string;
  workflow_id: string;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  error_message: string;
  created_at: string;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

const STATUSES = ['', 'running', 'completed', 'failed', 'cancelled'];

@Component({
  tag: 'erp-workflows-runs',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .filters { display:flex; gap:.5rem; align-items:end; margin:.5rem 0 1rem; }
    .filters ion-select { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:10rem; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpWorkflowsRuns {
  @State() runs: WorkflowRun[] = [];
  @State() loading = true;
  @State() error = '';
  @State() status = '';

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'created_at', header: 'Fecha' },
    { key: 'workflow_id', header: 'Workflow' },
    { key: 'status', header: 'Estado' },
    { key: 'started_at', header: 'Inicio' },
    { key: 'completed_at', header: 'Fin' },
    { key: 'error_message', header: 'Error' },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('workflows.run.completed', () => this.refresh());
      this.unsub = () => {
        off1();
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
      const rows = await erplora().query<WorkflowRun[]>('workflows.runs.list', {
        workflow_id: '',
        status: this.status,
        limit: 100,
      });
      this.runs = rows ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando ejecuciones';
    } finally {
      this.loading = false;
    }
  }

  private async onStatus(value: string) {
    this.status = value;
    await this.refresh();
  }

  render() {
    return (
      <div>
        <header>
          <h2>Ejecuciones</h2>
        </header>

        <div class="filters">
          <ion-select
            placeholder="Estado…"
            value={this.status}
            onIonChange={(e: any) => this.onStatus(e.target.value)}
          >
            {STATUSES.map((s) => (
              <ion-select-option value={s} key={s || 'all'}>
                {s || 'Todos'}
              </ion-select-option>
            ))}
          </ion-select>
        </div>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.runs as unknown as Record<string, unknown>[]}
          searchKeys={['workflow_id', 'status']}
          searchPlaceholder="Buscar ejecución…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin ejecuciones.'}
        />
      </div>
    );
  }
}
