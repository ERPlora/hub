import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `messaging` (Stencil). Mini-app: log de mensajes enviados
// + envío rápido. El envío real (dispatch por canal) lo ejecuta el handler WASM en Rust.
// El componente NO toca la BD: llama al SDK (erplora.query/command/on).

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface Msg {
  id: string;
  channel: string;
  recipient_name: string;
  recipient_contact: string;
  subject: string;
  status: string;
  sent_at: string | null;
  created_at: string;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-messaging-messages',
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
export class ErpMessagingMessages {
  @State() messages: Msg[] = [];
  @State() loading = true;
  @State() error = '';
  @State() status = '';
  @State() newChannel = 'email';
  @State() newContact = '';
  @State() newSubject = '';
  @State() newBody = '';
  @State() saving = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'created_at', header: 'Fecha' },
    { key: 'channel', header: 'Canal' },
    { key: 'recipient_name', header: 'Destinatario', format: (r) => (r.recipient_name as string) || (r.recipient_contact as string) },
    { key: 'subject', header: 'Asunto' },
    { key: 'status', header: 'Estado' },
  ];

  async componentWillLoad() {
    await this.refresh();
    try {
      const off = erplora().on('messaging.message.sent', () => this.refresh());
      this.unsub = off;
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
      const rows = await erplora().query<Msg[]>('messaging.messages.list', {
        channel: '',
        status: this.status,
        limit: 50,
      });
      this.messages = rows ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando mensajes';
    } finally {
      this.loading = false;
    }
  }

  private async sendMessage(ev: Event) {
    ev.preventDefault();
    if (!this.newContact.trim() || !this.newBody.trim()) return;
    this.saving = true;
    this.error = '';
    try {
      await erplora().command('messaging.messages.send', {
        channel: this.newChannel,
        recipient_contact: this.newContact.trim(),
        recipient_name: '',
        subject: this.newSubject.trim(),
        body: this.newBody,
        template_id: null,
        customer_id: null,
        extra_metadata: {},
      });
      this.newContact = '';
      this.newSubject = '';
      this.newBody = '';
      await this.refresh();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo enviar el mensaje';
    } finally {
      this.saving = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Mensajes</h2>
        </header>

        <form class="form" onSubmit={(e) => this.sendMessage(e)}>
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
            placeholder="Destinatario (tel/email)"
            value={this.newContact}
            onIonInput={(e: any) => (this.newContact = e.target.value)}
          />
          <ion-input
            placeholder="Asunto (email)"
            value={this.newSubject}
            onIonInput={(e: any) => (this.newSubject = e.target.value)}
          />
          <ion-textarea
            placeholder="Mensaje"
            value={this.newBody}
            onIonInput={(e: any) => (this.newBody = e.target.value)}
          />
          <ion-button type="submit" size="small" disabled={this.saving || !this.newContact || !this.newBody}>
            {this.saving ? 'Enviando…' : 'Enviar'}
          </ion-button>
        </form>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.messages as unknown as Record<string, unknown>[]}
          searchKeys={['recipient_name', 'recipient_contact', 'subject']}
          searchPlaceholder="Buscar mensaje…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin mensajes.'}
        />
      </div>
    );
  }
}
