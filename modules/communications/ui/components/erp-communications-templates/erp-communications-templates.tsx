import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn, DataTableAction } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `communications` (Stencil). Mini-app: gestión de
// plantillas de email reutilizables (listado + alta rápida + borrado lógico).
// Portado de TemplateService. El WC NUNCA toca la BD: usa erplora.query/command.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface Template {
  id: string;
  name: string;
  subject: string;
  variables: string;
  is_active: number;
  updated_at: string | null;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-communications-templates',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .form { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; }
    .form ion-input { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:10rem; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpCommunicationsTemplates {
  @State() templates: Template[] = [];
  @State() loading = true;
  @State() error = '';
  @State() newName = '';
  @State() newSubject = '';
  @State() saving = false;
  @State() busyId = '';

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'name', header: 'Nombre' },
    { key: 'subject', header: 'Asunto', format: (r) => (r.subject as string) || '—' },
    { key: 'is_active', header: 'Activa', align: 'center', format: (r) => (r.is_active ? 'Sí' : 'No') },
    { key: 'updated_at', header: 'Actualizada', format: (r) => (r.updated_at ? String(r.updated_at).slice(0, 16) : '—') },
  ];

  private actions: DataTableAction[] = [{ id: 'delete', label: 'Eliminar', icon: 'trash-outline', color: 'danger' }];

  private onRowAction = (ev: CustomEvent<{ actionId: string; row: Record<string, unknown> }>) => {
    if (ev.detail.actionId === 'delete') this.remove(ev.detail.row);
  };

  async componentWillLoad() {
    await this.refresh();
    try {
      const off = erplora().on('communications.template.created', () => this.refresh());
      this.unsub = () => off();
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
      const tpls = await erplora().query<Template[]>('communications.templates.list', { active_only: 0 });
      this.templates = tpls ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando plantillas';
    } finally {
      this.loading = false;
    }
  }

  private async create(ev: Event) {
    ev.preventDefault();
    if (!this.newName.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('communications.templates.create', {
        name: this.newName.trim(),
        subject: this.newSubject.trim(),
        body_html: '',
        body_text: '',
        variables: '[]',
      });
      this.newName = '';
      this.newSubject = '';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear la plantilla';
    } finally {
      this.saving = false;
    }
  }

  private async remove(row: Record<string, unknown>) {
    const id = row.id as string;
    if (!id) return;
    this.busyId = id;
    this.error = '';
    try {
      await erplora().command('communications.templates.delete', { id });
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo eliminar la plantilla';
    } finally {
      this.busyId = '';
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Plantillas de email</h2>
        </header>

        <form class="form" onSubmit={(e) => this.create(e)}>
          <ion-input
            placeholder="Nombre de la plantilla"
            value={this.newName}
            onIonInput={(e: any) => (this.newName = e.target.value)}
          />
          <ion-input
            placeholder="Asunto (opcional)"
            value={this.newSubject}
            onIonInput={(e: any) => (this.newSubject = e.target.value)}
          />
          <ion-button type="submit" size="small" disabled={this.saving || !this.newName}>
            {this.saving ? 'Guardando…' : 'Añadir'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.templates as unknown as Record<string, unknown>[]}
          searchKeys={['name', 'subject']}
          searchPlaceholder="Buscar plantilla…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin plantillas.'}
          actions={this.actions}
          onRowAction={this.onRowAction}
        />
      </div>
    );
  }
}
