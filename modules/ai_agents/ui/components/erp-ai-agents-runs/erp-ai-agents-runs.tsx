import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild lo
// empaquete dentro del bundle del módulo. El shell provee los `ion-*`. (4 niveles arriba.)
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `ai_agents` — vista "runs". Lista las ejecuciones recientes
// con su estado y contabilidad de tokens/coste. El WC NUNCA toca la BD: llama al SDK.
// El alta de un run (start) es un command con handler WASM (genera run_number + estado).

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface AgentRow {
  id: string;
  code: string;
  name: string;
}

interface Run {
  id: string;
  run_number: string;
  agent_id: string;
  trigger_type: string;
  status: string;
  iterations_used: number;
  tokens_used: number;
  cost_eur: string;
  created_at: string;
}

const STATUSES = ['', 'queued', 'running', 'completed', 'failed', 'timeout'];

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-ai-agents-runs',
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
export class ErpAiAgentsRuns {
  @State() runs: Run[] = [];
  @State() agents: AgentRow[] = [];
  @State() loading = true;
  @State() error = '';
  @State() statusFilter = '';
  @State() starting = false;
  @State() runAgent = '';
  @State() runQuery = '';

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'run_number', header: 'Nº' },
    { key: 'agent_id', header: 'Agente', format: (r) => this.agentName(r.agent_id as string) },
    { key: 'trigger_type', header: 'Disparo' },
    { key: 'status', header: 'Estado' },
    { key: 'iterations_used', header: 'Iter.', align: 'right' },
    { key: 'tokens_used', header: 'Tokens', align: 'right' },
    { key: 'cost_eur', header: 'Coste €', align: 'right', format: (r) => Number(r.cost_eur).toFixed(2) },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('ai_agents.run.started', () => this.refresh());
      const off2 = erplora().on('ai_agents.run.completed', () => this.refresh());
      const off3 = erplora().on('ai_agents.run.failed', () => this.refresh());
      const off4 = erplora().on('ai_agents.run.step_recorded', () => this.refresh());
      this.unsub = () => {
        off1();
        off2();
        off3();
        off4();
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
      const [runs, agents] = await Promise.all([
        erplora().query<Run[]>('ai_agents.runs.list', { agent_id: '', status: this.statusFilter, limit: 50 }),
        erplora().query<AgentRow[]>('ai_agents.agents.list', { active_only: 1, agent_type: '' }),
      ]);
      this.runs = runs ?? [];
      this.agents = agents ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando runs';
    } finally {
      this.loading = false;
    }
  }

  private async onStatusChange(value: string) {
    this.statusFilter = value;
    await this.refresh();
  }

  private async startRun(ev: Event) {
    ev.preventDefault();
    if (!this.runAgent || !this.runQuery.trim()) return;
    this.starting = true;
    this.error = '';
    try {
      await erplora().command('ai_agents.runs.start', {
        agent_id: this.runAgent,
        input_query: this.runQuery.trim(),
        trigger_type: 'manual',
      });
      this.runQuery = '';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo lanzar el run';
    } finally {
      this.starting = false;
    }
  }

  private agentName(id: string): string {
    return this.agents.find((a) => a.id === id)?.code ?? '—';
  }

  render() {
    return (
      <div>
        <header>
          <h2>Ejecuciones</h2>
          <ion-select
            placeholder="Estado…"
            value={this.statusFilter}
            onIonChange={(e: any) => this.onStatusChange(e.target.value)}
          >
            {STATUSES.map((s) => (
              <ion-select-option value={s} key={s || 'all'}>
                {s || 'Todos'}
              </ion-select-option>
            ))}
          </ion-select>
        </header>

        <form class="form" onSubmit={(e) => this.startRun(e)}>
          <ion-select
            placeholder="Agente…"
            value={this.runAgent}
            onIonChange={(e: any) => (this.runAgent = e.target.value)}
          >
            {this.agents.map((a) => (
              <ion-select-option value={a.id} key={a.id}>
                {a.code}
              </ion-select-option>
            ))}
          </ion-select>
          <ion-input
            placeholder="Consulta de entrada…"
            value={this.runQuery}
            onIonInput={(e: any) => (this.runQuery = e.target.value)}
          />
          <ion-button type="submit" size="small" disabled={this.starting || !this.runAgent || !this.runQuery}>
            {this.starting ? 'Lanzando…' : 'Lanzar run'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.runs as unknown as Record<string, unknown>[]}
          searchKeys={['run_number', 'status', 'trigger_type']}
          searchPlaceholder="Buscar run…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin ejecuciones.'}
        />
      </div>
    );
  }
}
