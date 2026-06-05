import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `activities` (Stencil). Mini-app: timeline de actividades
// CRM (call/email/meeting/task/note/sms) + alta rápida. Es la pieza `ui.entry` que el
// shell carga en runtime (modules/activities/dist/activities.esm.js).
//
// El componente NUNCA toca la BD: llama al SDK (erplora.query/command/on). La lógica de
// transición de estado (completar/cancelar) y las estadísticas viven en Rust/WASM.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface Activity {
  id: string;
  activity_type: string;
  subject: string;
  description: string;
  related_entity_type: string;
  related_entity_ref: string;
  scheduled_for: string | null;
  completed_at: string | null;
  duration_minutes: number | null;
  assigned_to_ref: string;
  status: string;
  priority: string;
  created_at: string | null;
}

const ACTIVITY_TYPES = ['call', 'email', 'meeting', 'task', 'note', 'sms'];
const PRIORITIES = ['low', 'medium', 'high'];

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-activities-timeline',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .form { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; }
    .form ion-input, .form ion-select { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:8rem; }
    .filters { display:flex; gap:.5rem; flex-wrap:wrap; margin-bottom:.75rem; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpActivitiesTimeline {
  @State() activities: Activity[] = [];
  @State() loading = true;
  @State() error = '';
  @State() saving = false;

  // Filtros
  @State() filterType = '';
  @State() filterStatus = '';

  // Formulario de alta
  @State() newType = 'task';
  @State() newSubject = '';
  @State() newPriority = 'medium';

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'activity_type', header: 'Tipo' },
    { key: 'subject', header: 'Asunto' },
    { key: 'status', header: 'Estado' },
    { key: 'priority', header: 'Prioridad' },
    {
      key: 'scheduled_for',
      header: 'Programada',
      format: (r) => (r.scheduled_for ? String(r.scheduled_for).slice(0, 16).replace('T', ' ') : '—'),
    },
    { key: 'assigned_to_ref', header: 'Asignada a', format: (r) => (r.assigned_to_ref as string) || '—' },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const offs = [
        erplora().on('activities.activity.created', () => this.refresh()),
        erplora().on('activities.activity.completed', () => this.refresh()),
        erplora().on('activities.activity.cancelled', () => this.refresh()),
        erplora().on('activities.activity.reassigned', () => this.refresh()),
      ];
      this.unsub = () => offs.forEach((off) => off());
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
      this.activities = (await erplora().query<Activity[]>('activities.activities.list', {
        activity_type: this.filterType,
        status: this.filterStatus,
        related_entity_type: '',
        related_entity_ref: '',
        assigned_to: '',
        limit: 100,
      })) ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando actividades';
    } finally {
      this.loading = false;
    }
  }

  private async createActivity(ev: Event) {
    ev.preventDefault();
    if (!this.newSubject.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('activities.activities.create', {
        activity_type: this.newType,
        subject: this.newSubject.trim(),
        description: '',
        related_entity_type: '',
        related_entity_ref: '',
        scheduled_for: null,
        priority: this.newPriority,
        assigned_to_ref: '',
        created_by_ref: '',
      });
      this.newSubject = '';
      this.newType = 'task';
      this.newPriority = 'medium';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear la actividad';
    } finally {
      this.saving = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Actividades</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createActivity(e)}>
          <ion-select
            placeholder="Tipo…"
            value={this.newType}
            onIonChange={(e: any) => (this.newType = e.target.value)}
          >
            {ACTIVITY_TYPES.map((t) => (
              <ion-select-option value={t} key={t}>
                {t}
              </ion-select-option>
            ))}
          </ion-select>
          <ion-input
            placeholder="Asunto"
            value={this.newSubject}
            onIonInput={(e: any) => (this.newSubject = e.target.value)}
          />
          <ion-select
            placeholder="Prioridad…"
            value={this.newPriority}
            onIonChange={(e: any) => (this.newPriority = e.target.value)}
          >
            {PRIORITIES.map((p) => (
              <ion-select-option value={p} key={p}>
                {p}
              </ion-select-option>
            ))}
          </ion-select>
          <ion-button type="submit" size="small" disabled={this.saving || !this.newSubject}>
            {this.saving ? 'Guardando…' : 'Añadir'}
          </ion-button>
        </form>

        <div class="filters">
          <ion-select
            placeholder="Todos los tipos"
            value={this.filterType}
            onIonChange={(e: any) => {
              this.filterType = e.target.value;
              this.refresh();
            }}
          >
            <ion-select-option value="">Todos los tipos</ion-select-option>
            {ACTIVITY_TYPES.map((t) => (
              <ion-select-option value={t} key={t}>
                {t}
              </ion-select-option>
            ))}
          </ion-select>
          <ion-select
            placeholder="Todos los estados"
            value={this.filterStatus}
            onIonChange={(e: any) => {
              this.filterStatus = e.target.value;
              this.refresh();
            }}
          >
            <ion-select-option value="">Todos los estados</ion-select-option>
            <ion-select-option value="pending">pending</ion-select-option>
            <ion-select-option value="completed">completed</ion-select-option>
            <ion-select-option value="cancelled">cancelled</ion-select-option>
          </ion-select>
        </div>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.activities as unknown as Record<string, unknown>[]}
          searchKeys={['subject', 'activity_type', 'assigned_to_ref']}
          searchPlaceholder="Buscar asunto o tipo…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin actividades.'}
        />
      </div>
    );
  }
}
