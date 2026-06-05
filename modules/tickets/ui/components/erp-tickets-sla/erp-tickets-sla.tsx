import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `tickets` (vista SLA). Lista los objetivos de nivel de
// servicio (tiempos de respuesta/resolución por prioridad) + alta rápida.
// NO toca la BD; solo SDK (erplora.query/command/on).

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface SLA {
  id: string;
  name: string;
  description: string;
  priority: string;
  response_time_hours: number;
  resolution_time_hours: number;
  is_active: number;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-tickets-sla',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .form { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; }
    .form ion-input, .form ion-select { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:7rem; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpTicketsSla {
  @State() slas: SLA[] = [];
  @State() loading = true;
  @State() error = '';
  @State() newName = '';
  @State() newPriority = 'medium';
  @State() newResponse = '24';
  @State() newResolution = '72';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'priority', header: 'Prioridad' },
    { key: 'name', header: 'Nombre' },
    { key: 'response_time_hours', header: 'Respuesta (h)', align: 'right' },
    { key: 'resolution_time_hours', header: 'Resolución (h)', align: 'right' },
    { key: 'is_active', header: 'Activo', format: (r) => (Number(r.is_active) ? 'Sí' : 'No') },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('tickets.sla.created', () => this.refresh());
      this.unsub = () => off1();
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
      const slas = await erplora().query<SLA[]>('tickets.slas.list', { active_only: '' });
      this.slas = slas ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando SLAs';
    } finally {
      this.loading = false;
    }
  }

  private async createSla(ev: Event) {
    ev.preventDefault();
    if (!this.newName.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('tickets.slas.create', {
        name: this.newName.trim(),
        description: '',
        priority: this.newPriority,
        response_time_hours: Number(this.newResponse) || 24,
        resolution_time_hours: Number(this.newResolution) || 72,
      });
      this.newName = '';
      this.newPriority = 'medium';
      this.newResponse = '24';
      this.newResolution = '72';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear el SLA';
    } finally {
      this.saving = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Objetivos SLA</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createSla(e)}>
          <ion-input
            placeholder="Nombre"
            value={this.newName}
            onIonInput={(e: any) => (this.newName = e.target.value)}
          />
          <ion-select
            value={this.newPriority}
            onIonChange={(e: any) => (this.newPriority = e.target.value)}
          >
            <ion-select-option value="low">Baja</ion-select-option>
            <ion-select-option value="medium">Media</ion-select-option>
            <ion-select-option value="high">Alta</ion-select-option>
            <ion-select-option value="urgent">Urgente</ion-select-option>
          </ion-select>
          <ion-input
            type="number"
            min="1"
            placeholder="Respuesta (h)"
            value={this.newResponse}
            onIonInput={(e: any) => (this.newResponse = e.target.value)}
          />
          <ion-input
            type="number"
            min="1"
            placeholder="Resolución (h)"
            value={this.newResolution}
            onIonInput={(e: any) => (this.newResolution = e.target.value)}
          />
          <ion-button type="submit" size="small" disabled={this.saving || !this.newName}>
            {this.saving ? 'Guardando…' : 'Añadir SLA'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.slas as unknown as Record<string, unknown>[]}
          searchKeys={['name', 'priority']}
          searchPlaceholder="Buscar nombre o prioridad…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin SLAs configurados.'}
        />
      </div>
    );
  }
}
