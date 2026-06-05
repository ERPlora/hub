import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `email_marketing` (Stencil). Vista de campañas: lista de
// blasts de email con sus métricas + alta rápida de campaña (draft). Es la pieza
// `ui.entry` del shell. NO toca la BD: todo va por el SDK (erplora.query/command/on).
// La máquina de estados (schedule/send) y los contadores viven en WASM.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface EmailCampaign {
  id: string;
  name: string;
  subject: string;
  sender_email: string;
  list_id: string;
  status: string;
  total_sent: number;
  total_opens: number;
  total_clicks: number;
  total_bounces: number;
}

interface EmailList {
  id: string;
  name: string;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-email-marketing-campaigns',
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
export class ErpEmailMarketingCampaigns {
  @State() campaigns: EmailCampaign[] = [];
  @State() lists: EmailList[] = [];
  @State() loading = true;
  @State() error = '';
  @State() newName = '';
  @State() newSubject = '';
  @State() newSender = '';
  @State() newList = '';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'name', header: 'Nombre' },
    { key: 'subject', header: 'Asunto' },
    { key: 'list_id', header: 'Lista', format: (r) => this.listName(r.list_id as string) },
    { key: 'status', header: 'Estado' },
    { key: 'total_sent', header: 'Enviados', align: 'right' },
    { key: 'total_opens', header: 'Aperturas', align: 'right' },
    { key: 'total_clicks', header: 'Clicks', align: 'right' },
    { key: 'total_bounces', header: 'Rebotes', align: 'right' },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off1 = erplora().on('email_marketing.campaign.created', () => this.refresh());
      const off2 = erplora().on('email_marketing.campaign.scheduled', () => this.refresh());
      const off3 = erplora().on('email_marketing.campaign.sent', () => this.refresh());
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
      const [campaigns, lists] = await Promise.all([
        erplora().query<EmailCampaign[]>('email_marketing.campaigns.list', {
          status: '',
          list_id: '',
          limit: 50,
        }),
        erplora().query<EmailList[]>('email_marketing.lists.list', { active_only: 1 }),
      ]);
      this.campaigns = campaigns ?? [];
      this.lists = lists ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando campañas';
    } finally {
      this.loading = false;
    }
  }

  private async createCampaign(ev: Event) {
    ev.preventDefault();
    if (!this.newName.trim() || !this.newSubject.trim() || !this.newSender.trim() || !this.newList) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('email_marketing.campaigns.create', {
        name: this.newName.trim(),
        subject: this.newSubject.trim(),
        list_id: this.newList,
        html_content: '',
        plain_content: '',
        sender_email: this.newSender.trim(),
        sender_name: 'ERPlora',
      });
      this.newName = '';
      this.newSubject = '';
      this.newSender = '';
      this.newList = '';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo crear la campaña';
    } finally {
      this.saving = false;
    }
  }

  private listName(id: string): string {
    return this.lists.find((l) => l.id === id)?.name ?? '—';
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
          <ion-input
            placeholder="Asunto"
            value={this.newSubject}
            onIonInput={(e: any) => (this.newSubject = e.target.value)}
          />
          <ion-input
            type="email"
            placeholder="Remitente (email)"
            value={this.newSender}
            onIonInput={(e: any) => (this.newSender = e.target.value)}
          />
          <ion-select
            placeholder="Lista…"
            value={this.newList}
            onIonChange={(e: any) => (this.newList = e.target.value)}
          >
            {this.lists.map((l) => (
              <ion-select-option value={l.id} key={l.id}>
                {l.name}
              </ion-select-option>
            ))}
          </ion-select>
          <ion-button
            type="submit"
            size="small"
            disabled={this.saving || !this.newName || !this.newSubject || !this.newSender || !this.newList}
          >
            {this.saving ? 'Guardando…' : 'Crear borrador'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.campaigns as unknown as Record<string, unknown>[]}
          searchKeys={['name', 'subject', 'status']}
          searchPlaceholder="Buscar campaña…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin campañas.'}
        />
      </div>
    );
  }
}
