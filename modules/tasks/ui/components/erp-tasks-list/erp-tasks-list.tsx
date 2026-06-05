import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `tasks` (Stencil): lista de tareas con filtros + alta rápida.
// Es la pieza `ui.entry` que el shell carga en runtime (modules/tasks/dist/tasks.esm.js).
//
// El componente NO toca la BD: lee vía erplora.query y crea/completa vía erplora.command.
// El cálculo del task_number y los sellados de estado viven en el handler WASM (runtime).

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface Task {
  id: string;
  task_number: string;
  title: string;
  status: string;
  priority: string;
  assigned_to_ref: string | null;
  due_date: string | null;
}

const STATUS_LABELS: Record<string, string> = {
  todo: 'To Do',
  in_progress: 'In Progress',
  blocked: 'Blocked',
  done: 'Done',
  cancelled: 'Cancelled',
};

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-tasks-list',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .form { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; }
    .form ion-input, .form ion-select { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:8rem; }
    .filters { display:flex; gap:.5rem; flex-wrap:wrap; margin:.25rem 0 1rem; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpTasksList {
  @State() tasks: Task[] = [];
  @State() loading = true;
  @State() error = '';
  @State() statusFilter = '';
  @State() priorityFilter = '';
  @State() newTitle = '';
  @State() newPriority = 'medium';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'task_number', header: 'Nº' },
    { key: 'title', header: 'Título' },
    { key: 'status', header: 'Estado', format: (r) => STATUS_LABELS[r.status as string] ?? (r.status as string) },
    { key: 'priority', header: 'Prioridad' },
    { key: 'due_date', header: 'Vence', format: (r) => (r.due_date ? String(r.due_date).slice(0, 10) : '—') },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('tasks.task.created', () => this.refresh());
      const off2 = erplora().on('tasks.task.status_changed', () => this.refresh());
      const off3 = erplora().on('tasks.task.completed', () => this.refresh());
      const off4 = erplora().on('tasks.task.assigned', () => this.refresh());
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
      const tasks = await erplora().query<Task[]>('tasks.tasks.list', {
        status: this.statusFilter,
        priority: this.priorityFilter,
        assigned_to: '',
        project_id: '',
        limit: 100,
      });
      this.tasks = tasks ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando tareas';
    } finally {
      this.loading = false;
    }
  }

  private async createTask(ev: Event) {
    ev.preventDefault();
    if (!this.newTitle.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('tasks.tasks.create', {
        title: this.newTitle.trim(),
        description: '',
        project_id: null,
        assigned_to_ref: null,
        due_date: null,
        priority: this.newPriority,
        parent_task_id: null,
        created_by_ref: null,
        tags: [],
      });
      this.newTitle = '';
      this.newPriority = 'medium';
      await this.refresh();
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
          <h2>Tareas</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createTask(e)}>
          <ion-input
            placeholder="Nueva tarea…"
            value={this.newTitle}
            onIonInput={(e: any) => (this.newTitle = e.target.value)}
          />
          <ion-select
            placeholder="Prioridad…"
            value={this.newPriority}
            onIonChange={(e: any) => (this.newPriority = e.target.value)}
          >
            <ion-select-option value="low">Low</ion-select-option>
            <ion-select-option value="medium">Medium</ion-select-option>
            <ion-select-option value="high">High</ion-select-option>
            <ion-select-option value="urgent">Urgent</ion-select-option>
          </ion-select>
          <ion-button type="submit" size="small" disabled={this.saving || !this.newTitle}>
            {this.saving ? 'Guardando…' : 'Añadir'}
          </ion-button>
        </form>

        <div class="filters">
          <ion-select
            placeholder="Estado…"
            value={this.statusFilter}
            onIonChange={(e: any) => {
              this.statusFilter = e.target.value;
              this.refresh();
            }}
          >
            <ion-select-option value="">Todos</ion-select-option>
            <ion-select-option value="todo">To Do</ion-select-option>
            <ion-select-option value="in_progress">In Progress</ion-select-option>
            <ion-select-option value="blocked">Blocked</ion-select-option>
            <ion-select-option value="done">Done</ion-select-option>
            <ion-select-option value="cancelled">Cancelled</ion-select-option>
          </ion-select>
          <ion-select
            placeholder="Prioridad…"
            value={this.priorityFilter}
            onIonChange={(e: any) => {
              this.priorityFilter = e.target.value;
              this.refresh();
            }}
          >
            <ion-select-option value="">Todas</ion-select-option>
            <ion-select-option value="low">Low</ion-select-option>
            <ion-select-option value="medium">Medium</ion-select-option>
            <ion-select-option value="high">High</ion-select-option>
            <ion-select-option value="urgent">Urgent</ion-select-option>
          </ion-select>
        </div>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.tasks as unknown as Record<string, unknown>[]}
          searchKeys={['task_number', 'title']}
          searchPlaceholder="Buscar nº o título…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin tareas.'}
        />
      </div>
    );
  }
}
