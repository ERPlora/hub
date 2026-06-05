import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild lo
// empaquete dentro del bundle del módulo. El shell provee los `ion-*`. (4 niveles arriba.)
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `ai_agents` — vista "agents". Lista las definiciones de
// agentes y permite alta rápida. El WC NUNCA toca la BD: llama al SDK
// (erplora.query / erplora.command / erplora.on). Es la `ui.entry` del módulo.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface Agent {
  id: string;
  code: string;
  name: string;
  agent_type: string;
  max_iterations: number;
  is_active: number;
  total_runs: number;
  total_cost_eur: string;
}

const AGENT_TYPES = ['assistant', 'automation', 'monitor', 'analyzer'];

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-ai-agents-agents',
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
export class ErpAiAgentsAgents {
  @State() agents: Agent[] = [];
  @State() loading = true;
  @State() error = '';
  @State() saving = false;
  @State() newCode = '';
  @State() newName = '';
  @State() newType = 'assistant';

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'code', header: 'Código' },
    { key: 'name', header: 'Nombre' },
    { key: 'agent_type', header: 'Tipo' },
    { key: 'max_iterations', header: 'Máx. iter.', align: 'right' },
    { key: 'total_runs', header: 'Runs', align: 'right' },
    { key: 'total_cost_eur', header: 'Coste €', align: 'right', format: (r) => Number(r.total_cost_eur).toFixed(2) },
    { key: 'is_active', header: 'Activo', format: (r) => (Number(r.is_active) ? 'Sí' : 'No') },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('ai_agents.agent.created', () => this.refresh());
      const off2 = erplora().on('ai_agents.agent.updated', () => this.refresh());
      const off3 = erplora().on('ai_agents.agent.deactivated', () => this.refresh());
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
      const agents = await erplora().query<Agent[]>('ai_agents.agents.list', {
        active_only: 0,
        agent_type: '',
      });
      this.agents = agents ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando agentes';
    } finally {
      this.loading = false;
    }
  }

  private async createAgent(ev: Event) {
    ev.preventDefault();
    if (!this.newCode.trim() || !this.newName.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('ai_agents.agents.create', {
        code: this.newCode.trim(),
        name: this.newName.trim(),
        agent_type: this.newType,
        description: '',
        system_prompt: '',
        tools: [],
        max_iterations: 10,
        model_preference: '',
      });
      this.newCode = '';
      this.newName = '';
      this.newType = 'assistant';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear el agente';
    } finally {
      this.saving = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Agentes</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createAgent(e)}>
          <ion-input
            placeholder="Código (support-bot)"
            value={this.newCode}
            onIonInput={(e: any) => (this.newCode = e.target.value)}
          />
          <ion-input
            placeholder="Nombre"
            value={this.newName}
            onIonInput={(e: any) => (this.newName = e.target.value)}
          />
          <ion-select
            placeholder="Tipo…"
            value={this.newType}
            onIonChange={(e: any) => (this.newType = e.target.value)}
          >
            {AGENT_TYPES.map((t) => (
              <ion-select-option value={t} key={t}>
                {t}
              </ion-select-option>
            ))}
          </ion-select>
          <ion-button type="submit" size="small" disabled={this.saving || !this.newCode || !this.newName}>
            {this.saving ? 'Guardando…' : 'Crear'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.agents as unknown as Record<string, unknown>[]}
          searchKeys={['code', 'name', 'agent_type']}
          searchPlaceholder="Buscar agente…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin agentes.'}
        />
      </div>
    );
  }
}
