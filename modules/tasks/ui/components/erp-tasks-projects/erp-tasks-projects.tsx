import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `tasks` (Stencil): lista de proyectos de tareas + alta rápida.
// El componente NO toca la BD: lee vía erplora.query y crea vía erplora.command.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface TaskProject {
  id: string;
  code: string;
  name: string;
  color: string;
  is_active: number;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-tasks-projects',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .form { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; }
    .form ion-input { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:8rem; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpTasksProjects {
  @State() projects: TaskProject[] = [];
  @State() loading = true;
  @State() error = '';
  @State() newCode = '';
  @State() newName = '';
  @State() newColor = '';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'code', header: 'Código' },
    { key: 'name', header: 'Nombre' },
    { key: 'color', header: 'Color', format: (r) => (r.color as string) || '—' },
    { key: 'is_active', header: 'Activo', format: (r) => (r.is_active ? 'Sí' : 'No') },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off = erplora().on('tasks.project.created', () => this.refresh());
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
      const projects = await erplora().query<TaskProject[]>('tasks.projects.list', { active_only: 1 });
      this.projects = projects ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando proyectos';
    } finally {
      this.loading = false;
    }
  }

  private async createProject(ev: Event) {
    ev.preventDefault();
    if (!this.newCode.trim() || !this.newName.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('tasks.projects.create', {
        code: this.newCode.trim(),
        name: this.newName.trim(),
        color: this.newColor.trim(),
        owner_ref: null,
      });
      this.newCode = '';
      this.newName = '';
      this.newColor = '';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear el proyecto';
    } finally {
      this.saving = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Proyectos</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createProject(e)}>
          <ion-input
            placeholder="Código (q3-audit)"
            value={this.newCode}
            onIonInput={(e: any) => (this.newCode = e.target.value)}
          />
          <ion-input
            placeholder="Nombre"
            value={this.newName}
            onIonInput={(e: any) => (this.newName = e.target.value)}
          />
          <ion-input
            placeholder="Color (opcional)"
            value={this.newColor}
            onIonInput={(e: any) => (this.newColor = e.target.value)}
          />
          <ion-button type="submit" size="small" disabled={this.saving || !this.newCode || !this.newName}>
            {this.saving ? 'Guardando…' : 'Añadir'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.projects as unknown as Record<string, unknown>[]}
          searchKeys={['code', 'name']}
          searchPlaceholder="Buscar código o nombre…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin proyectos.'}
        />
      </div>
    );
  }
}
