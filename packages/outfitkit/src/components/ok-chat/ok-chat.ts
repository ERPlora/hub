import { LitElement, html, css } from 'lit';
import { property, query } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// Mensaje del hilo de chat. Lo aporta el consumidor vía la prop `.messages`.
export interface OkChatMessage {
  /** Identificador único del mensaje (clave de render). */
  id: string;
  /** Texto del mensaje. */
  text: string;
  /** Autor visible (solo se muestra en mensajes ajenos). */
  author?: string;
  /** Hora del mensaje (texto ya formateado, p.ej. '14:32'). */
  time?: string;
  /** Si es `true`, el mensaje es del usuario actual (alineado a la derecha). */
  self?: boolean;
  /** Avatar: URL de imagen o iniciales (texto corto). Solo en mensajes ajenos. */
  avatar?: string;
}

// ok-chat — hilo de mensajes (chat) por DATOS (`messages`), con compositor opcional.
// AUTOCONTENIDO: CSS propio en el shadow. Usa `ion-*` NATIVOS (icon/button/textarea) que registra
// el HOST. Rellena el alto/ancho de su contenedor (flex column). Burbujas: `self` a la derecha con
// fondo primario translúcido; ajenas a la izquierda con superficie + avatar. Agrupa mensajes
// consecutivos del mismo lado/autor. Auto-scroll al fondo cuando cambian los mensajes.
//   • prop `.messages`   → Array<OkChatMessage>
//   • prop `title`       → cabecera opcional
//   • prop `placeholder` → texto del compositor (def 'Escribe un mensaje…')
//   • prop `readonly`    → oculta el compositor
// Eventos (bubbles + composed):
//   • `ok-send`  detail { text }  → al enviar texto no vacío (el consumidor añade a `.messages`)
/** Textos humanos de ok-chat (i18n; default inglés, override vía prop `labels`). */
export interface OkChatLabels {
  /** Placeholder del compositor. */
  composerPlaceholder: string;
  /** aria-label del botón de enviar. */
  send: string;
}

const DEFAULT_LABELS: OkChatLabels = {
  composerPlaceholder: 'Type a message…',
  send: 'Send',
};

export class OkChat extends LitElement {
  static styles = css`
    :host {
      /* Vars overridable (estilo Ionic), default = cadena --ok-* → --ion-* → hex */
      --color: var(--ok-text, var(--ion-text-color, #1c1b17));
      --color-muted: var(--ok-text-muted, rgba(var(--ion-text-color-rgb, 28, 27, 23), 0.55));
      --surface: var(--ok-surface, var(--ion-color-step-50, #f5f5f4));
      --surface-2: var(--ok-surface-2, var(--ion-background-color, #ffffff));
      --border-soft: var(--ok-border-soft, rgba(var(--ion-text-color-rgb, 28, 27, 23), 0.12));
      --primary-color: var(--ok-primary, var(--ion-color-primary, #3880ff));
      --primary-rgb: var(--ok-primary-rgb, var(--ion-color-primary-rgb, 56, 128, 255));
      --primary-contrast: var(--ok-primary-contrast, var(--ion-color-primary-contrast, #ffffff));
      --bubble-self: rgba(var(--primary-rgb), 0.14);
      --border-radius: var(--ok-radius, 14px);
      --font: var(--ok-font, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif);

      /* Rellena el contenedor: columna flex de alto/ancho completo. */
      display: flex;
      flex-direction: column;
      height: 100%;
      width: 100%;
      min-height: 0;
      color: var(--color);
      font-family: var(--font);
      font-size: 0.95rem;
      background: var(--surface-2);
    }

    /* Cabecera opcional. */
    .header {
      flex: 0 0 auto;
      display: flex;
      align-items: center;
      padding: 0.7rem 1rem;
      font-weight: 600;
      border-bottom: 1px solid var(--border-soft);
    }

    /* Lista scrollable de burbujas. */
    .log {
      flex: 1 1 auto;
      min-height: 0;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      gap: 0.15rem;
      padding: 0.85rem 1rem;
      box-sizing: border-box;
    }

    /* Fila de un mensaje (avatar + burbuja). */
    .msg {
      display: flex;
      align-items: flex-end;
      gap: 0.5rem;
      max-width: 100%;
    }
    .msg.self {
      flex-direction: row-reverse;
    }
    /* Separación extra entre grupos (cambio de lado/autor). */
    .msg.group-start {
      margin-top: 0.6rem;
    }
    .msg.group-start:first-child {
      margin-top: 0;
    }

    /* Avatar (imagen o iniciales) — solo en mensajes ajenos. */
    .avatar {
      flex: 0 0 auto;
      width: 30px;
      height: 30px;
      border-radius: 50%;
      overflow: hidden;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      font-size: 0.72rem;
      font-weight: 600;
      background: var(--surface);
      color: var(--color-muted);
      border: 1px solid var(--border-soft);
    }
    .avatar img {
      width: 100%;
      height: 100%;
      object-fit: cover;
    }
    /* Hueco del avatar cuando no toca mostrarlo (mantiene alineación del grupo). */
    .avatar.spacer {
      visibility: hidden;
      border: 0;
      background: none;
    }

    /* Burbuja. */
    .bubble {
      max-width: min(78%, 560px);
      box-sizing: border-box;
      padding: 0.5rem 0.7rem;
      border-radius: var(--border-radius);
      background: var(--surface);
      border: 1px solid var(--border-soft);
      word-wrap: break-word;
      overflow-wrap: anywhere;
    }
    .msg.self .bubble {
      background: var(--bubble-self);
      border-color: transparent;
    }
    /* Esquinas: "pico" hacia su lado en el primer mensaje del grupo. */
    .msg.group-start:not(.self) .bubble {
      border-top-left-radius: 4px;
    }
    .msg.group-start.self .bubble {
      border-top-right-radius: 4px;
    }

    .author {
      display: block;
      font-size: 0.72rem;
      font-weight: 600;
      color: var(--primary-color);
      margin-bottom: 0.15rem;
    }
    .text {
      white-space: pre-wrap;
      line-height: 1.35;
    }
    .time {
      display: block;
      margin-top: 0.2rem;
      font-size: 0.66rem;
      color: var(--color-muted);
      text-align: right;
    }

    /* Compositor abajo. */
    .composer {
      flex: 0 0 auto;
      display: flex;
      align-items: flex-end;
      gap: 0.4rem;
      padding: 0.55rem 0.7rem;
      border-top: 1px solid var(--border-soft);
      background: var(--surface-2);
    }
    .composer ion-textarea {
      flex: 1 1 auto;
      --background: var(--surface);
      --border-radius: var(--border-radius);
      --padding-start: 0.7rem;
      --padding-end: 0.7rem;
      --padding-top: 0.4rem;
      --padding-bottom: 0.4rem;
    }
    .composer ion-button {
      flex: 0 0 auto;
      margin: 0;
    }

    @media (max-width: 480px) {
      .bubble {
        max-width: 84%;
      }
      .log {
        padding: 0.7rem 0.7rem;
      }
    }
  `;

  /** Mensajes del hilo (orden cronológico ascendente). */
  @property({ attribute: false }) messages: OkChatMessage[] = [];
  /** Texto de la cabecera; si está vacío no se dibuja cabecera. */
  @property() title = '';
  /** Placeholder del compositor. Si vacío, se deriva de `labels.composerPlaceholder`. */
  @property() placeholder = '';
  /** Si está activo, oculta el compositor (chat de solo lectura). */
  @property({ type: Boolean }) readonly = false;
  /** Overrides de textos humanos (i18n). Se fusionan sobre los defaults en inglés. */
  @property({ attribute: false }) labels: Partial<OkChatLabels> = {};

  /** Textos efectivos (defaults inglés + overrides). */
  private get t(): OkChatLabels {
    return { ...DEFAULT_LABELS, ...this.labels };
  }

  /** Placeholder efectivo: prop explícita o el de labels. */
  private get effectivePlaceholder(): string {
    return this.placeholder || this.t.composerPlaceholder;
  }

  // Referencias a la lista (auto-scroll) y al textarea (envío/limpieza).
  @query('.log') private logEl?: HTMLElement;
  @query('ion-textarea') private textareaEl?: HTMLElement & { value?: string | null };

  // ¿El mensaje empieza un nuevo grupo? (cambia el lado o el autor respecto al anterior).
  private isGroupStart(index: number): boolean {
    if (index === 0) return true;
    const prev = this.messages[index - 1];
    const cur = this.messages[index];
    return !!prev.self !== !!cur.self || prev.author !== cur.author;
  }

  // ¿El mensaje termina un grupo? (el siguiente cambia de lado/autor o no hay siguiente).
  private isGroupEnd(index: number): boolean {
    if (index === this.messages.length - 1) return true;
    const next = this.messages[index + 1];
    const cur = this.messages[index];
    return !!next.self !== !!cur.self || next.author !== cur.author;
  }

  // Avatar de un mensaje ajeno: imagen si parece URL, iniciales en caso contrario.
  private renderAvatar(msg: OkChatMessage, show: boolean): unknown {
    if (msg.self) return '';
    if (!show) return html`<span class="avatar spacer"></span>`;
    const av = msg.avatar;
    const isUrl = !!av && /^(https?:|data:|\/|\.)/.test(av);
    return html`<span class="avatar">
      ${isUrl
        ? html`<img src=${av!} alt="" />`
        : html`<span>${(av || msg.author || '?').slice(0, 2).toUpperCase()}</span>`}
    </span>`;
  }

  // Render de un mensaje (fila avatar + burbuja).
  private renderMessage(msg: OkChatMessage, index: number): unknown {
    const start = this.isGroupStart(index);
    const end = this.isGroupEnd(index);
    const cls = ['msg', msg.self ? 'self' : '', start ? 'group-start' : ''].filter(Boolean).join(' ');
    // El autor solo en el primer mensaje del grupo y solo si es ajeno.
    const showAuthor = start && !msg.self && !!msg.author;
    // El avatar solo al cerrar el grupo (último mensaje ajeno consecutivo).
    return html`<div class=${cls}>
      ${this.renderAvatar(msg, end)}
      <div class="bubble">
        ${showAuthor ? html`<span class="author">${msg.author}</span>` : ''}
        <span class="text">${msg.text}</span>
        ${msg.time ? html`<span class="time">${msg.time}</span>` : ''}
      </div>
    </div>`;
  }

  // Envía el contenido del compositor si no está vacío y limpia el campo.
  private send(): void {
    const el = this.textareaEl;
    const text = (el?.value ?? '').trim();
    if (!text) return;
    this.dispatchEvent(
      new CustomEvent('ok-send', {
        detail: { text },
        bubbles: true,
        composed: true,
      }),
    );
    if (el) el.value = '';
  }

  // Enter envía; Shift+Enter inserta salto de línea (comportamiento por defecto del textarea).
  private onKeydown(e: KeyboardEvent): void {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      this.send();
    }
  }

  // Tras cada render, si han cambiado los mensajes hace auto-scroll al fondo.
  protected updated(changed: Map<string, unknown>): void {
    if (changed.has('messages') && this.logEl) {
      this.logEl.scrollTop = this.logEl.scrollHeight;
    }
  }

  render(): unknown {
    return html`
      ${this.title ? html`<div class="header">${this.title}</div>` : ''}
      <div class="log" role="log" aria-live="polite">
        ${this.messages.map((msg, i) => this.renderMessage(msg, i))}
      </div>
      ${this.readonly
        ? ''
        : html`<div class="composer">
            <ion-textarea
              auto-grow
              rows="1"
              placeholder=${this.effectivePlaceholder}
              @keydown=${(e: KeyboardEvent) => this.onKeydown(e)}
            ></ion-textarea>
            <ion-button
              fill="solid"
              aria-label=${this.t.send}
              @click=${() => this.send()}
            >
              <ion-icon slot="icon-only" name="send"></ion-icon>
            </ion-button>
          </div>`}
    `;
  }
}

define('ok-chat', OkChat);

declare global {
  interface HTMLElementTagNameMap {
    'ok-chat': OkChat;
  }
}
