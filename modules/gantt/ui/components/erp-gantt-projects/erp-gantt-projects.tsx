import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `gantt` (Stencil). Mini-app: lista de proyectos de
// planificación + alta rápida. Es una de las dos piezas de la `ui.entry` que el
// shell carga en runtime (modules/gantt/dist/gantt.esm.js).
//
// La lógica de cálculo (duración, camino crítico, propagación de fechas, progreso
// agregado) vive en WASM (Tier 2). Este componente NO toca la BD: llama al SDK
// (erplora.query/command/on). El listado usa el DataTable compartido + Ionic.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface GanttProject {
  id: string;
  name: string;
  description: string;
  start_date: string | null;
  end_date: string | null;
  status: string;
  color: string;
  owner_ref: string | null;
  progress_pct: number;
}

const STATUSES = ['planning', 'active', 'on_hold', 'completed', 'cancelled'];

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-gantt-projects',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .form { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; }
    .form ion-input, .form ion-select { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:8rem; }
    .err { color:#d9480f; font-weight:600; }
    .filter { display:flex; gap:.5rem; align-items:center; margin-bottom:.5rem; }
  `,
})
export class ErpGanttProjects {
  @State() projects: GanttProject[] = [];
  @State() loading = true;
  @State() error = '';
  @State() statusFilter = '';
  @State() newName = '';
  @State() newStatus = 'planning';
  @State() newStart = '';
  @State() newEnd = '';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'name', header: 'Proyecto' },
    { key: 'status', header: 'Estado' },
    { key: 'start_date', header: 'Inicio' },
    { key: 'end_date', header: 'Fin' },
    { key: 'progress_pct', header: '% avance', align: 'right', format: (r) => `${Number(r.progress_pct) || 0}%` },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('gantt.project.created', () => this.refresh());
      const off2 = erplora().on('gantt.task.progress_updated', () => this.refresh());
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
      this.projects =
        (await erplora().query<GanttProject[]>('gantt.projects.list', { status: this.statusFilter })) ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando proyectos';
    } finally {
      this.loading = false;
    }
  }

  private async createProject(ev: Event) {
    ev.preventDefault();
    if (!this.newName.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('gantt.projects.create', {
        name: this.newName.trim(),
        description: '',
        status: this.newStatus,
        color: '#3b82f6',
        start_date: this.newStart || null,
        end_date: this.newEnd || null,
        owner_ref: null,
      });
      this.newName = '';
      this.newStart = '';
      this.newEnd = '';
      this.newStatus = 'planning';
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
            placeholder="Nombre del proyecto"
            value={this.newName}
            onIonInput={(e: any) => (this.newName = e.target.value)}
          />
          <ion-input
            type="date"
            placeholder="Inicio"
            value={this.newStart}
            onIonInput={(e: any) => (this.newStart = e.target.value)}
          />
          <ion-input
            type="date"
            placeholder="Fin"
            value={this.newEnd}
            onIonInput={(e: any) => (this.newEnd = e.target.value)}
          />
          <ion-select
            placeholder="Estado…"
            value={this.newStatus}
            onIonChange={(e: any) => (this.newStatus = e.target.value)}
          >
            {STATUSES.map((s) => (
              <ion-select-option value={s} key={s}>
                {s}
              </ion-select-option>
            ))}
          </ion-select>
          <ion-button type="submit" size="small" disabled={this.saving || !this.newName}>
            {this.saving ? 'Guardando…' : 'Crear proyecto'}
          </ion-button>
        </form>

        <div class="filter">
          <ion-select
            placeholder="Filtrar estado…"
            value={this.statusFilter}
            onIonChange={(e: any) => {
              this.statusFilter = e.target.value;
              this.refresh();
            }}
          >
            <ion-select-option value="">Todos</ion-select-option>
            {STATUSES.map((s) => (
              <ion-select-option value={s} key={s}>
                {s}
              </ion-select-option>
            ))}
          </ion-select>
        </div>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.projects as unknown as Record<string, unknown>[]}
          searchKeys={['name', 'status']}
          searchPlaceholder="Buscar proyecto…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin proyectos.'}
        />
      </div>
    );
  }
}
