import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `gantt` (Stencil). Vista timeline: elige un proyecto y
// muestra sus tareas (cronología) en el DataTable compartido + alta rápida de tarea.
//
// La duración se deriva en WASM (Tier 2) a partir de start/end; este componente NO
// toca la BD: llama al SDK (erplora.query/command/on).

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface GanttProject {
  id: string;
  name: string;
}

interface GanttTask {
  id: string;
  project_id: string;
  name: string;
  start_date: string | null;
  end_date: string | null;
  duration_days: number;
  progress_pct: number;
  is_milestone: number;
  parent_task_id: string | null;
  order: number;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-gantt-timeline',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .form { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; }
    .form ion-input { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:8rem; }
    .picker { margin-bottom:.75rem; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpGanttTimeline {
  @State() projects: GanttProject[] = [];
  @State() tasks: GanttTask[] = [];
  @State() projectId = '';
  @State() loading = true;
  @State() error = '';
  @State() newName = '';
  @State() newStart = '';
  @State() newEnd = '';
  @State() newMilestone = false;
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'name', header: 'Tarea' },
    { key: 'is_milestone', header: 'Hito', format: (r) => (Number(r.is_milestone) ? 'Sí' : '—') },
    { key: 'start_date', header: 'Inicio' },
    { key: 'end_date', header: 'Fin' },
    { key: 'duration_days', header: 'Días', align: 'right', format: (r) => String(Number(r.duration_days) || 0) },
    { key: 'progress_pct', header: '% avance', align: 'right', format: (r) => `${Number(r.progress_pct) || 0}%` },
  ];

  async componentWillLoad() {
    await this.loadProjects();
    try {
      const off1 = erplora().on('gantt.task.created', () => this.refreshTasks());
      const off2 = erplora().on('gantt.task.shifted', () => this.refreshTasks());
      const off3 = erplora().on('gantt.task.progress_updated', () => this.refreshTasks());
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

  private async loadProjects() {
    this.loading = true;
    this.error = '';
    try {
      this.projects = (await erplora().query<GanttProject[]>('gantt.projects.list', { status: '' })) ?? [];
      if (!this.projectId && this.projects.length) {
        this.projectId = this.projects[0].id;
        await this.refreshTasks();
      }
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando proyectos';
    } finally {
      this.loading = false;
    }
  }

  private async refreshTasks() {
    if (!this.projectId) {
      this.tasks = [];
      return;
    }
    this.loading = true;
    this.error = '';
    try {
      this.tasks =
        (await erplora().query<GanttTask[]>('gantt.projects.tasks', { project_id: this.projectId })) ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando tareas';
    } finally {
      this.loading = false;
    }
  }

  private async addTask(ev: Event) {
    ev.preventDefault();
    if (!this.projectId || !this.newName.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('gantt.tasks.add', {
        project_id: this.projectId,
        name: this.newName.trim(),
        start_date: this.newStart || null,
        end_date: this.newEnd || null,
        assigned_to_ref: null,
        parent_task_id: null,
        is_milestone: this.newMilestone,
        order: 0,
      });
      this.newName = '';
      this.newStart = '';
      this.newEnd = '';
      this.newMilestone = false;
      await this.refreshTasks();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear la tarea';
    } finally {
      this.saving = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Cronología</h2>
        </header>

        <div class="picker">
          <ion-select
            placeholder="Elegir proyecto…"
            value={this.projectId}
            onIonChange={(e: any) => {
              this.projectId = e.target.value;
              this.refreshTasks();
            }}
          >
            {this.projects.map((p) => (
              <ion-select-option value={p.id} key={p.id}>
                {p.name}
              </ion-select-option>
            ))}
          </ion-select>
        </div>

        <form class="form" onSubmit={(e) => this.addTask(e)}>
          <ion-input
            placeholder="Nombre de tarea"
            value={this.newName}
            onIonInput={(e: any) => (this.newName = e.target.value)}
          />
          <ion-input
            type="date"
            value={this.newStart}
            onIonInput={(e: any) => (this.newStart = e.target.value)}
          />
          <ion-input
            type="date"
            value={this.newEnd}
            onIonInput={(e: any) => (this.newEnd = e.target.value)}
          />
          <ion-checkbox
            checked={this.newMilestone}
            onIonChange={(e: any) => (this.newMilestone = e.target.checked)}
          >
            Hito
          </ion-checkbox>
          <ion-button type="submit" size="small" disabled={this.saving || !this.projectId || !this.newName}>
            {this.saving ? 'Guardando…' : 'Añadir tarea'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.tasks as unknown as Record<string, unknown>[]}
          searchKeys={['name']}
          searchPlaceholder="Buscar tarea…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin tareas en este proyecto.'}
        />
      </div>
    );
  }
}
