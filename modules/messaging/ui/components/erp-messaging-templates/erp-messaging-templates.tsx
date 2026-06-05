import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `messaging` (Stencil). Mini-app: lista de plantillas
// de mensaje + alta rápida. Pieza cargada por el shell vía ui.entry.
// El componente NO toca la BD: llama al SDK (erplora.query/command/on).

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface Template {
  id: string;
  name: string;
  channel: string;
  category: string;
  subject: string;
  body: string;
  is_active: number;
  is_system: number;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-messaging-templates',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .form { display:flex; gap:.5rem; flex-wrap:wrap; align-items:end; margin:.5rem 0 1rem; }
    .form ion-input, .form ion-select, .form ion-textarea { --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; min-width:8rem; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpMessagingTemplates {
  @State() templates: Template[] = [];
  @State() loading = true;
  @State() error = '';
  @State() channel = '';
  @State() newName = '';
  @State() newChannel = 'all';
  @State() newCategory = 'custom';
  @State() newSubject = '';
  @State() newBody = '';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'name', header: 'Nombre' },
    { key: 'channel', header: 'Canal' },
    { key: 'category', header: 'Categoría' },
    { key: 'subject', header: 'Asunto' },
    { key: 'is_active', header: 'Activa', format: (r) => (Number(r.is_active) ? 'Sí' : 'No') },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('messaging.template.created', () => this.refresh());
      const off2 = erplora().on('messaging.template.updated', () => this.refresh());
      const off3 = erplora().on('messaging.template.deleted', () => this.refresh());
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
      const rows = await erplora().query<Template[]>('messaging.templates.list', {
        channel: this.channel,
        is_active: -1,
      });
      this.templates = rows ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando plantillas';
    } finally {
      this.loading = false;
    }
  }

  private async createTemplate(ev: Event) {
    ev.preventDefault();
    if (!this.newName.trim() || !this.newBody.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('messaging.templates.create', {
        name: this.newName.trim(),
        channel: this.newChannel,
        category: this.newCategory,
        subject: this.newSubject.trim(),
        body: this.newBody,
      });
      this.newName = '';
      this.newSubject = '';
      this.newBody = '';
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
          <h2>Plantillas de mensaje</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createTemplate(e)}>
          <ion-input
            placeholder="Nombre"
            value={this.newName}
            onIonInput={(e: any) => (this.newName = e.target.value)}
          />
          <ion-select
            placeholder="Canal…"
            value={this.newChannel}
            onIonChange={(e: any) => (this.newChannel = e.target.value)}
          >
            <ion-select-option value="all">Todos</ion-select-option>
            <ion-select-option value="whatsapp">WhatsApp</ion-select-option>
            <ion-select-option value="sms">SMS</ion-select-option>
            <ion-select-option value="email">Email</ion-select-option>
          </ion-select>
          <ion-select
            placeholder="Categoría…"
            value={this.newCategory}
            onIonChange={(e: any) => (this.newCategory = e.target.value)}
          >
            <ion-select-option value="custom">Personalizada</ion-select-option>
            <ion-select-option value="appointment_reminder">Recordatorio cita</ion-select-option>
            <ion-select-option value="booking_confirmation">Confirmación reserva</ion-select-option>
            <ion-select-option value="receipt">Recibo</ion-select-option>
            <ion-select-option value="marketing">Marketing</ion-select-option>
          </ion-select>
          <ion-input
            placeholder="Asunto (email)"
            value={this.newSubject}
            onIonInput={(e: any) => (this.newSubject = e.target.value)}
          />
          <ion-textarea
            placeholder="Cuerpo con {{variables}}"
            value={this.newBody}
            onIonInput={(e: any) => (this.newBody = e.target.value)}
          />
          <ion-button type="submit" size="small" disabled={this.saving || !this.newName || !this.newBody}>
            {this.saving ? 'Guardando…' : 'Añadir'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.templates as unknown as Record<string, unknown>[]}
          searchKeys={['name', 'channel', 'category']}
          searchPlaceholder="Buscar plantilla…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin plantillas.'}
        />
      </div>
    );
  }
}
