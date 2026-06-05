import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `ai_reports` (Stencil). Mini-app: registro de peticiones
// de informe AI + alta rápida (encolar una petición). Es una de las piezas que el
// shell carga vía `ui.entry` (modules/ai_reports/dist/ai_reports.esm.js).
//
// La lógica vive en el runtime/WASM: este componente NO toca la BD; llama al SDK
// (erplora.query/command/on). El listado usa el DataTable compartido + Ionic.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface AIReportRequest {
  id: string;
  request_number: string;
  template_id: string | null;
  user_query: string;
  tokens_used: number;
  cost_eur: string;
  status: string;
  requested_by_ref: string;
  created_at: string;
}

interface AIReportTemplate {
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
  tag: 'erp-ai-reports-requests',
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
export class ErpAiReportsRequests {
  @State() requests: AIReportRequest[] = [];
  @State() templates: AIReportTemplate[] = [];
  @State() loading = true;
  @State() error = '';
  @State() statusFilter = '';
  @State() newQuery = '';
  @State() newTemplate = '';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'request_number', header: 'Nº' },
    { key: 'status', header: 'Estado' },
    { key: 'user_query', header: 'Consulta' },
    { key: 'tokens_used', header: 'Tokens', align: 'right' },
    { key: 'cost_eur', header: 'Coste €', align: 'right', format: (r) => Number(r.cost_eur).toFixed(4) },
    { key: 'requested_by_ref', header: 'Solicitado por' },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('ai_reports.request.created', () => this.refresh());
      const off2 = erplora().on('ai_reports.request.completed', () => this.refresh());
      const off3 = erplora().on('ai_reports.request.cancelled', () => this.refresh());
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
      const [reqs, tpls] = await Promise.all([
        erplora().query<AIReportRequest[]>('ai_reports.requests.list', {
          status: this.statusFilter,
          requested_by: '',
          limit: 50,
        }),
        erplora().query<AIReportTemplate[]>('ai_reports.templates.list', { active_only: '1' }),
      ]);
      this.requests = reqs ?? [];
      this.templates = tpls ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando peticiones';
    } finally {
      this.loading = false;
    }
  }

  private async createRequest(ev: Event) {
    ev.preventDefault();
    if (!this.newQuery.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('ai_reports.requests.create', {
        user_query: this.newQuery.trim(),
        template_id: this.newTemplate || null,
        data_context: '{}',
      });
      this.newQuery = '';
      this.newTemplate = '';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo encolar la petición';
    } finally {
      this.saving = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Peticiones de informe AI</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createRequest(e)}>
          <ion-input
            placeholder="Consulta en lenguaje natural…"
            value={this.newQuery}
            onIonInput={(e: any) => (this.newQuery = e.target.value)}
          />
          <ion-select
            placeholder="Plantilla (opcional)…"
            value={this.newTemplate}
            onIonChange={(e: any) => (this.newTemplate = e.target.value)}
          >
            <ion-select-option value="">— Sin plantilla —</ion-select-option>
            {this.templates.map((t) => (
              <ion-select-option value={t.id} key={t.id}>
                {t.code}
              </ion-select-option>
            ))}
          </ion-select>
          <ion-button type="submit" size="small" disabled={this.saving || !this.newQuery}>
            {this.saving ? 'Encolando…' : 'Encolar'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.requests as unknown as Record<string, unknown>[]}
          searchKeys={['request_number', 'user_query', 'requested_by_ref']}
          searchPlaceholder="Buscar nº, consulta o usuario…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin peticiones de informe.'}
        />
      </div>
    );
  }
}
