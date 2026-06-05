import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `messaging` (Stencil). Mini-app: automatizaciones CRM
// (welcome, birthday, post_sale…) + alta. La evaluación de triggers contra eventos
// la hace el runtime/WASM. El componente NO toca la BD: llama al SDK.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface Automation {
  id: string;
  name: string;
  trigger: string;
  channel: string;
  template_id: string | null;
  delay_hours: number;
  is_active: number;
  total_sent: number;
}

interface Template {
  id: string;
  name: string;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

const TRIGGERS = [
  'welcome', 'birthday', 'anniversary', 'post_sale', 'post_appointment',
  'inactivity', 'loyalty_tier_change', 'lead_stage_change', 'ticket_resolved',
  'booking_confirmed', 'booking_reminder', 'custom',
];

@Component({
  tag: 'erp-messaging-automations',
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
export class ErpMessagingAutomations {
  @State() automations: Automation[] = [];
  @State() templates: Template[] = [];
  @State() loading = true;
  @State() error = '';
  @State() newName = '';
  @State() newTrigger = 'welcome';
  @State() newChannel = 'email';
  @State() newTemplate = '';
  @State() newDelay = '0';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'name', header: 'Nombre' },
    { key: 'trigger', header: 'Disparador' },
    { key: 'channel', header: 'Canal' },
    { key: 'delay_hours', header: 'Retardo (h)', align: 'right' },
    { key: 'total_sent', header: 'Enviados', align: 'right' },
    { key: 'is_active', header: 'Activa', format: (r) => (Number(r.is_active) ? 'Sí' : 'No') },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('messaging.automation.created', () => this.refresh());
      const off2 = erplora().on('messaging.automation.updated', () => this.refresh());
      const off3 = erplora().on('messaging.automation.deleted', () => this.refresh());
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
      const [autos, tpls] = await Promise.all([
        erplora().query<Automation[]>('messaging.automations.list', { is_active: -1 }),
        erplora().query<Template[]>('messaging.templates.list', { channel: '', is_active: 1 }),
      ]);
      this.automations = autos ?? [];
      this.templates = tpls ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando automatizaciones';
    } finally {
      this.loading = false;
    }
  }

  private async createAutomation(ev: Event) {
    ev.preventDefault();
    if (!this.newName.trim() || !this.newTemplate) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('messaging.automations.create', {
        name: this.newName.trim(),
        description: '',
        trigger: this.newTrigger,
        channel: this.newChannel,
        template_id: this.newTemplate,
        delay_hours: Number(this.newDelay) || 0,
        conditions: '{}',
      });
      this.newName = '';
      this.newDelay = '0';
      this.newTemplate = '';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear la automatización';
    } finally {
      this.saving = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Automatizaciones</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createAutomation(e)}>
          <ion-input
            placeholder="Nombre"
            value={this.newName}
            onIonInput={(e: any) => (this.newName = e.target.value)}
          />
          <ion-select
            placeholder="Disparador…"
            value={this.newTrigger}
            onIonChange={(e: any) => (this.newTrigger = e.target.value)}
          >
            {TRIGGERS.map((t) => (
              <ion-select-option value={t} key={t}>
                {t}
              </ion-select-option>
            ))}
          </ion-select>
          <ion-select
            placeholder="Canal…"
            value={this.newChannel}
            onIonChange={(e: any) => (this.newChannel = e.target.value)}
          >
            <ion-select-option value="email">Email</ion-select-option>
            <ion-select-option value="sms">SMS</ion-select-option>
            <ion-select-option value="whatsapp">WhatsApp</ion-select-option>
            <ion-select-option value="all">Todos</ion-select-option>
          </ion-select>
          <ion-select
            placeholder="Plantilla…"
            value={this.newTemplate}
            onIonChange={(e: any) => (this.newTemplate = e.target.value)}
          >
            {this.templates.map((t) => (
              <ion-select-option value={t.id} key={t.id}>
                {t.name}
              </ion-select-option>
            ))}
          </ion-select>
          <ion-input
            type="number"
            min="0"
            placeholder="Retardo (h)"
            value={this.newDelay}
            onIonInput={(e: any) => (this.newDelay = e.target.value)}
          />
          <ion-button type="submit" size="small" disabled={this.saving || !this.newName || !this.newTemplate}>
            {this.saving ? 'Guardando…' : 'Añadir'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.automations as unknown as Record<string, unknown>[]}
          searchKeys={['name', 'trigger', 'channel']}
          searchPlaceholder="Buscar automatización…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin automatizaciones.'}
        />
      </div>
    );
  }
}
