import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `messaging` (Stencil). Mini-app: campañas de envío masivo
// + alta. El envío masivo (resolver destinatarios + encolar) lo hace el handler WASM.
// El componente NO toca la BD: llama al SDK (erplora.query/command/on).

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface Campaign {
  id: string;
  name: string;
  channel: string;
  status: string;
  total_recipients: number;
  sent_count: number;
  delivered_count: number;
  failed_count: number;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-messaging-campaigns',
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
export class ErpMessagingCampaigns {
  @State() campaigns: Campaign[] = [];
  @State() loading = true;
  @State() error = '';
  @State() newName = '';
  @State() newChannel = 'email';
  @State() newDescription = '';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'name', header: 'Nombre' },
    { key: 'channel', header: 'Canal' },
    { key: 'status', header: 'Estado' },
    { key: 'total_recipients', header: 'Destinatarios', align: 'right' },
    { key: 'sent_count', header: 'Enviados', align: 'right' },
    { key: 'delivered_count', header: 'Entregados', align: 'right' },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('messaging.campaign.created', () => this.refresh());
      const off2 = erplora().on('messaging.campaign.cancelled', () => this.refresh());
      const off3 = erplora().on('messaging.campaign.completed', () => this.refresh());
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
      const rows = await erplora().query<Campaign[]>('messaging.campaigns.list', { status: '' });
      this.campaigns = rows ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando campañas';
    } finally {
      this.loading = false;
    }
  }

  private async createCampaign(ev: Event) {
    ev.preventDefault();
    if (!this.newName.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('messaging.campaigns.create', {
        name: this.newName.trim(),
        description: this.newDescription.trim(),
        channel: this.newChannel,
        template_id: null,
        scheduled_at: null,
        target_filter: '{}',
      });
      this.newName = '';
      this.newDescription = '';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear la campaña';
    } finally {
      this.saving = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Campañas</h2>
        </header>

        <form class="form" onSubmit={(e) => this.createCampaign(e)}>
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
            <ion-select-option value="email">Email</ion-select-option>
            <ion-select-option value="sms">SMS</ion-select-option>
            <ion-select-option value="whatsapp">WhatsApp</ion-select-option>
          </ion-select>
          <ion-input
            placeholder="Descripción"
            value={this.newDescription}
            onIonInput={(e: any) => (this.newDescription = e.target.value)}
          />
          <ion-button type="submit" size="small" disabled={this.saving || !this.newName}>
            {this.saving ? 'Guardando…' : 'Nueva campaña'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.campaigns as unknown as Record<string, unknown>[]}
          searchKeys={['name', 'channel', 'status']}
          searchPlaceholder="Buscar campaña…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin campañas.'}
        />
      </div>
    );
  }
}
