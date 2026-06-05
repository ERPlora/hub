import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `rules_triggers` (vista Triggers). Mini-app: lista de
// triggers (fuentes de evento) + alta rápida + activar/desactivar. Es una de las
// dos piezas que el shell carga desde modules/rules_triggers/dist/rules_triggers.esm.js.
//
// La lógica real vive en Rust: este componente NO toca la BD; llama al SDK
// (erplora.query/command/on). El listado usa el DataTable compartido + Ionic.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface Trigger {
  id: string;
  code: string;
  name: string;
  event_type: string;
  entity_filter: string;
  is_active: number;
  last_fired_at: string | null;
  fire_count: number;
}

const EVENT_TYPES = ['entity_created', 'entity_updated', 'entity_deleted', 'scheduled', 'webhook'];

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-rules-triggers-triggers',
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
export class ErpRulesTriggersTriggers {
  @State() triggers: Trigger[] = [];
  @State() loading = true;
  @State() error = '';
  @State() newCode = '';
  @State() newName = '';
  @State() newEvent = 'entity_created';
  @State() newFilter = '';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'code', header: 'Código' },
    { key: 'name', header: 'Nombre' },
    { key: 'event_type', header: 'Evento' },
    { key: 'entity_filter', header: 'Filtro', format: (r) => (r.entity_filter as string) || '—' },
    { key: 'fire_count', header: 'Disparos', align: 'right' },
    { key: 'is_active', header: 'Activo', format: (r) => (r.is_active ? 'sí' : 'no') },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('rules_triggers.trigger.created', () => this.refresh());
      const off2 = erplora().on('rules_triggers.trigger.activated', () => this.refresh());
      const off3 = erplora().on('rules_triggers.trigger.deactivated', () => this.refresh());
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
      const triggers = await erplora().query<Trigger[]>('rules_triggers.triggers.list', { event_type: '' });
      this.triggers = triggers ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando triggers';
    } finally {
      this.loading = false;
    }
  }

  private async createTrigger(ev: Event) {
    ev.preventDefault();
    if (!this.newCode.trim() || !this.newName.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('rules_triggers.triggers.create', {
        code: this.newCode.trim(),
        name: this.newName.trim(),
        event_type: this.newEvent,
        entity_filter: this.newFilter.trim(),
      });
      this.newCode = '';
      this.newName = '';
      this.newEvent = 'entity_created';
      this.newFilter = '';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear el trigger';
    } finally {
      this.saving = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Triggers</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createTrigger(e)}>
          <ion-input
            placeholder="Código (on_sale)"
            value={this.newCode}
            onIonInput={(e: any) => (this.newCode = e.target.value)}
          />
          <ion-input
            placeholder="Nombre"
            value={this.newName}
            onIonInput={(e: any) => (this.newName = e.target.value)}
          />
          <ion-select
            placeholder="Evento…"
            value={this.newEvent}
            onIonChange={(e: any) => (this.newEvent = e.target.value)}
          >
            {EVENT_TYPES.map((t) => (
              <ion-select-option value={t} key={t}>
                {t}
              </ion-select-option>
            ))}
          </ion-select>
          <ion-input
            placeholder="Filtro (customers.customer)"
            value={this.newFilter}
            onIonInput={(e: any) => (this.newFilter = e.target.value)}
          />
          <ion-button type="submit" size="small" disabled={this.saving || !this.newCode || !this.newName}>
            {this.saving ? 'Guardando…' : 'Añadir'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.triggers as unknown as Record<string, unknown>[]}
          searchKeys={['code', 'name', 'event_type']}
          searchPlaceholder="Buscar trigger…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin triggers.'}
        />
      </div>
    );
  }
}
