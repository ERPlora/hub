import { Component, State, h } from '@stencil/core';
// Importa el DataTable compartido (Stencil) para que se auto-registre y esbuild
// lo empaquete dentro del bundle del módulo. El shell provee los `ion-*`.
import '../../../../_shared/ui/components/data-table/data-table';
import type { DataTableColumn } from '../../../../_shared/ui/components/data-table/data-table';

// Web Component del módulo `assistant` (Stencil): mini-app de chat con la IA.
// Muestra el historial de la conversación activa en un <data-table> y envía
// mensajes vía el SDK (erplora.command). El WC NUNCA toca la BD: el bucle
// agéntico, el proxy LLM y el streaming SSE los resuelve el runtime/Cloud
// (command `assistant.chat.send` → handler WASM). Aquí sólo persistimos el
// turno del usuario y refrescamos el historial al recibir la respuesta.

interface ErploraClientLike {
  query<T = unknown>(name: string, params?: Record<string, unknown>): Promise<T>;
  command<T = unknown>(name: string, payload?: Record<string, unknown>): Promise<T>;
  on(event: string, cb: (payload: unknown) => void): () => void;
}

interface Conversation {
  id: string;
  context: string;
  updated_at: string;
}

interface Message {
  id: string;
  conversation_id: string;
  role: string;
  content: string;
  created_at: string;
}

function erplora(): ErploraClientLike {
  const c = (globalThis as { erplora?: ErploraClientLike }).erplora;
  if (!c) throw new Error('erplora SDK no inicializado por el shell');
  return c;
}

@Component({
  tag: 'erp-assistant-chat',
  shadow: true,
  styles: `
    :host { display:block; font-family: system-ui, sans-serif; color: var(--ink, #1c1b18); }
    header { display:flex; gap:.5rem; align-items:center; margin-bottom:.75rem; }
    h2 { margin:0; font-size:1.15rem; flex:1; }
    .form { display:flex; gap:.5rem; align-items:end; margin:.75rem 0 1rem; }
    .form ion-textarea { flex:1; --background:var(--surface-2,#f7f4ec); border:1px solid var(--line,#e7e2d6); border-radius:8px; }
    .err { color:#d9480f; font-weight:600; }
  `,
})
export class ErpAssistantChat {
  @State() conversations: Conversation[] = [];
  @State() messages: Message[] = [];
  @State() conversationId = '';
  @State() loading = true;
  @State() error = '';
  @State() draft = '';
  @State() sending = false;

  private unsub?: () => void;

  private columns: DataTableColumn[] = [
    { key: 'role', header: 'Rol' },
    { key: 'content', header: 'Mensaje' },
    { key: 'created_at', header: 'Fecha' },
  ];

  async componentWillLoad() {
    await this.loadConversations();
    await this.refreshMessages();
    try {
      const off1 = erplora().on('assistant.message.appended', () => this.refreshMessages());
      const off2 = erplora().on('assistant.conversation.created', () => this.loadConversations());
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

  private async loadConversations() {
    try {
      const convs = await erplora().query<Conversation[]>('assistant.conversations.list', {
        context: '',
      });
      this.conversations = convs ?? [];
      if (!this.conversationId && this.conversations.length) {
        this.conversationId = this.conversations[0].id;
      }
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando conversaciones';
    }
  }

  private async refreshMessages() {
    if (!this.conversationId) {
      this.messages = [];
      this.loading = false;
      return;
    }
    this.loading = true;
    this.error = '';
    try {
      const msgs = await erplora().query<Message[]>('assistant.messages.list', {
        conversation_id: this.conversationId,
      });
      this.messages = msgs ?? [];
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'Error cargando mensajes';
    } finally {
      this.loading = false;
    }
  }

  private async ensureConversation(): Promise<string> {
    if (this.conversationId) return this.conversationId;
    const res = await erplora().command<{ id: string }>('assistant.conversations.create', {
      context: 'general',
    });
    this.conversationId = res?.id ?? '';
    await this.loadConversations();
    return this.conversationId;
  }

  private async send(ev: Event) {
    ev.preventDefault();
    const text = this.draft.trim();
    if (!text) return;
    this.sending = true;
    this.error = '';
    try {
      const convId = await this.ensureConversation();
      // El handler WASM `chat_send` ejecuta el bucle agéntico (proxy LLM + tools)
      // y persiste tanto el turno del usuario como la respuesta del asistente.
      await erplora().command('assistant.chat.send', {
        conversation_id: convId,
        content: text,
        context: 'general',
      });
      this.draft = '';
      await this.refreshMessages();
    } catch (e) {
      this.error = e instanceof Error ? e.message : 'No se pudo enviar el mensaje';
    } finally {
      this.sending = false;
    }
  }

  render() {
    return (
      <div>
        <header>
          <h2>Asistente IA</h2>
        </header>

        {this.error && <p class="err">{this.error}</p>}

        <data-table
          columns={this.columns}
          rows={this.messages as unknown as Record<string, unknown>[]}
          searchKeys={['role', 'content']}
          searchPlaceholder="Buscar en la conversación…"
          emptyMessage={this.loading ? 'Cargando…' : 'Sin mensajes todavía.'}
        />

        <form class="form" onSubmit={(e) => this.send(e)}>
          <ion-textarea
            placeholder="Escribe tu mensaje…"
            value={this.draft}
            autoGrow={true}
            onIonInput={(e: any) => (this.draft = e.target.value)}
          />
          <ion-button type="submit" size="small" disabled={this.sending || !this.draft.trim()}>
            {this.sending ? 'Enviando…' : 'Enviar'}
          </ion-button>
        </form>
      </div>
    );
  }
}
