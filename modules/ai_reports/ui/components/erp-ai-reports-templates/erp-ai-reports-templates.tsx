import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `ai_reports` (Stencil). Mini-app: plantillas de prompt
// reutilizables + alta rápida. Es una de las piezas que el shell carga vía `ui.entry`.
//
// La lógica vive en el runtime: este componente NO toca la BD; llama al SDK
// (erplora.query/command/on). El listado usa el DataTable compartido + Ionic.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface AIReportTemplate {
  id: string;
  code: string;
  name: string;
  description: string;
  prompt_template: string;
  default_data_sources: string;
  output_format: string;
  is_active: number;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-ai-reports-templates',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .form { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; }
    .form ion-input, .form ion-select, .form ion-textarea { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:8rem; }
    .form ion-textarea { flex:1 1 100%; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpAiReportsTemplates {
  @State() templates: AIReportTemplate[] = [];
  @State() loading = true;
  @State() error = '';
  @State() newCode = '';
  @State() newName = '';
  @State() newPrompt = '';
  @State() newFormat = 'markdown';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'code', header: 'Código' },
    { key: 'name', header: 'Nombre' },
    { key: 'output_format', header: 'Formato' },
    { key: 'is_active', header: 'Activa', format: (r) => (Number(r.is_active) ? 'Sí' : 'No') },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('ai_reports.template.created', () => this.refresh());
      const off2 = erplora().on('ai_reports.template.updated', () => this.refresh());
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
      const tpls = await erplora().query<AIReportTemplate[]>('ai_reports.templates.list', {
        active_only: '',
      });
      this.templates = tpls ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando plantillas';
    } finally {
      this.loading = false;
    }
  }

  private async createTemplate(ev: Event) {
    ev.preventDefault();
    if (!this.newCode.trim() || !this.newName.trim() || !this.newPrompt.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('ai_reports.templates.create', {
        code: this.newCode.trim(),
        name: this.newName.trim(),
        prompt_template: this.newPrompt.trim(),
        description: '',
        default_data_sources: '[]',
        output_format: this.newFormat || 'markdown',
      });
      this.newCode = '';
      this.newName = '';
      this.newPrompt = '';
      this.newFormat = 'markdown';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear la plantilla';
    } finally {
      this.saving = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Plantillas de prompt</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createTemplate(e)}>
          <ion-input
            placeholder="Código (sales-summary)"
            value={this.newCode}
            onIonInput={(e: any) => (this.newCode = e.target.value)}
          />
          <ion-input
            placeholder="Nombre"
            value={this.newName}
            onIonInput={(e: any) => (this.newName = e.target.value)}
          />
          <ion-select
            placeholder="Formato…"
            value={this.newFormat}
            onIonChange={(e: any) => (this.newFormat = e.target.value)}
          >
            <ion-select-option value="markdown">markdown</ion-select-option>
            <ion-select-option value="html">html</ion-select-option>
            <ion-select-option value="text">text</ion-select-option>
          </ion-select>
          <ion-textarea
            placeholder="Plantilla de prompt…"
            autoGrow
            value={this.newPrompt}
            onIonInput={(e: any) => (this.newPrompt = e.target.value)}
          />
          <ion-button
            type="submit"
            size="small"
            disabled={this.saving || !this.newCode || !this.newName || !this.newPrompt}
          >
            {this.saving ? 'Guardando…' : 'Crear'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.templates as unknown as Record<string, unknown>[]}
          searchKeys={['code', 'name']}
          searchPlaceholder="Buscar código o nombre…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin plantillas.'}
        />
      </div>
    );
  }
}
