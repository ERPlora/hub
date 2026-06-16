import { LitElement, html, css, nothing } from 'lit';
import { property, state } from 'lit/decorators.js';
import { repeat } from 'lit/directives/repeat.js';
import { define } from '../../base/define.js';
// Internamente usa ion-button / ion-icon / ion-searchbar / ion-avatar / ion-badge NATIVOS (los
// registra el HOST). Para los estados vacíos REUSA <ok-empty-state> del catálogo. OutfitKit
// construye SOBRE Ionic; no envolvemos lo que Ionic (o el propio core) ya da.

// ok-mail — cliente de correo moderno y mobile-first, SOLO email (sin calendario/contactos).
// Layout en columna: cabecera superior (Redactar + buscador) + barra de TABS de carpetas con
// scroll horizontal; debajo, dos paneles (lista de mensajes + lectura) lado a lado en desktop.
// En móvil (<=760px) las tabs siguen arriba y se ve UN panel a la vez: lista → (al seleccionar)
// lectura a pantalla completa con botón atrás. Componente compuesto: CSS propio autocontenido con
// tokens --ok-* → --ion-* → hex. El WC nunca toca la red.

/** Carpeta del buzón (Bandeja, Enviados, Borradores…). */
export interface OkMailFolder {
  /** Id estable de la carpeta. */
  id: string;
  /** Etiqueta visible. */
  label: string;
  /** Nombre de un ion-icon opcional. */
  icon?: string;
  /** Nº de mensajes no leídos (badge). */
  count?: number;
}

/** Mensaje de correo. */
export interface OkMailMessage {
  /** Id estable del mensaje. */
  id: string;
  /** Id de la carpeta a la que pertenece. */
  folderId: string;
  /** Remitente. */
  from: { name: string; email: string };
  /** Destinatarios (correos). */
  to?: string[];
  /** Asunto. */
  subject: string;
  /** Vista previa (1 línea, atenuada). */
  preview?: string;
  /** Cuerpo completo (texto). */
  body?: string;
  /** Fecha ISO. */
  date: string;
  /** ¿Leído? (si no, se resalta). */
  read?: boolean;
  /** ¿Destacado con estrella? */
  starred?: boolean;
  /** Adjuntos. */
  attachments?: Array<{ name: string; size?: number }>;
}

/** Textos humanos de ok-mail (i18n; default inglés, override vía prop `labels`). */
export interface OkMailLabels {
  /** Botón "Redactar". */
  compose: string;
  /** Placeholder del buscador. */
  searchPlaceholder: string;
  /** aria-label del punto de no leído. */
  unread: string;
  /** aria-label para destacar un mensaje. */
  star: string;
  /** aria-label para quitar el destacado de un mensaje. */
  unstar: string;
  /** Estado vacío: lista sin mensajes. */
  noMessages: string;
  /** Estado vacío: ningún mensaje seleccionado. */
  selectMessage: string;
  /** aria-label del botón atrás (móvil). */
  back: string;
  /** aria-label de Responder. */
  reply: string;
  /** aria-label de Reenviar. */
  forward: string;
  /** aria-label de Archivar. */
  archive: string;
  /** aria-label de Eliminar. */
  delete: string;
  /** Etiqueta "Para:" en la cabecera de lectura. */
  to: string;
}

const DEFAULT_LABELS: OkMailLabels = {
  compose: 'Compose',
  searchPlaceholder: 'Search mail…',
  unread: 'Unread',
  star: 'Star',
  unstar: 'Remove star',
  noMessages: 'No messages',
  selectMessage: 'Select a message',
  back: 'Back to list',
  reply: 'Reply',
  forward: 'Forward',
  archive: 'Archive',
  delete: 'Delete',
  to: 'To:',
};

export class OkMail extends LitElement {
  static styles = css`
    :host {
      /* Tokens overridables (estilo Ionic): default = cadena --ok-* → --ion-* → hex. */
      --background: var(--ok-surface, var(--ion-background-color, #ffffff));
      --surface-2: var(--ok-surface-2, var(--ion-color-step-50, rgba(var(--ion-text-color-rgb, 24, 24, 27), 0.04)));
      --color: var(--ok-text, var(--ion-text-color, #1c1b17));
      --color-muted: var(--ok-muted, var(--ion-color-medium, rgba(var(--ion-text-color-rgb, 24, 24, 27), 0.55)));
      --border-color: var(--ok-border, var(--ion-color-step-150, rgba(var(--ion-text-color-rgb, 24, 24, 27), 0.12)));
      --border-color-soft: var(--ok-border-soft, var(--ion-color-step-100, rgba(var(--ion-text-color-rgb, 24, 24, 27), 0.07)));
      --row-hover: var(--ok-row-hover, var(--ion-color-step-50, rgba(var(--ion-text-color-rgb, 24, 24, 27), 0.03)));
      --primary: var(--ok-primary, var(--ion-color-primary, #3880ff));
      --primary-contrast: var(--ok-primary-contrast, var(--ion-color-primary-contrast, #ffffff));
      --warning: var(--ok-warning, var(--ion-color-warning, #ffc409));
      --font: var(--ok-font, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif);
      --list-width: 360px;
      --press-scale: var(--ok-press-scale, 0.98);

      display: flex;
      flex-direction: column;
      height: 100%;
      width: 100%;
      min-height: 0;
      color: var(--color);
      font-family: var(--font);
      background: var(--background);
    }
    * { box-sizing: border-box; }

    /* ── Cabecera superior: Redactar + buscador ──────────────────────────────────────────── */
    .topbar {
      flex: 0 0 auto;
      display: flex;
      align-items: center;
      gap: 0.5rem;
      padding: 0.6rem 0.75rem;
      border-bottom: 1px solid var(--border-color-soft);
    }
    .topbar ion-button { --box-shadow: none; margin: 0; flex: 0 0 auto; }
    .topbar ion-searchbar {
      --background: var(--surface-2);
      --border-radius: 12px;
      --box-shadow: none;
      padding: 0;
      flex: 1 1 auto;
      min-height: 40px;
    }
    .topbar ion-searchbar::part(native) { border: none; }

    /* ── Barra de TABS de carpetas (scroll horizontal) ───────────────────────────────────── */
    .tabs {
      flex: 0 0 auto;
      display: flex;
      align-items: stretch;
      gap: 0.35rem;
      padding: 0.4rem 0.6rem 0;
      overflow-x: auto;
      overflow-y: hidden;
      border-bottom: 1px solid var(--border-color);
      scrollbar-width: none;
      -ms-overflow-style: none;
      scroll-snap-type: x proximity;
    }
    .tabs::-webkit-scrollbar { display: none; }
    .tab {
      display: inline-flex;
      align-items: center;
      gap: 0.45rem;
      flex: 0 0 auto;
      padding: 0.55rem 0.85rem;
      border: 0;
      border-bottom: 2px solid transparent;
      border-radius: 10px 10px 0 0;
      background: none;
      color: var(--color-muted);
      font: inherit;
      font-size: 14px;
      font-weight: 600;
      white-space: nowrap;
      cursor: pointer;
      scroll-snap-align: start;
      transition: color 150ms ease, background-color 150ms ease, border-color 150ms ease;
    }
    .tab ion-icon { font-size: 17px; flex: 0 0 auto; }
    .tab ion-badge { --background: var(--surface-2); --color: var(--color-muted); font-size: 11px; min-width: 18px; }
    .tab.active { color: var(--primary); border-bottom-color: var(--primary); }
    .tab.active ion-badge { --background: var(--primary); --color: var(--primary-contrast); }
    @media (hover: hover) {
      .tab:hover { color: var(--color); background: var(--row-hover); }
      .tab.active:hover { color: var(--primary); }
    }
    .tab:active { transform: scale(var(--press-scale)); }

    /* ── Cuerpo: dos paneles (lista + lectura) ───────────────────────────────────────────── */
    .body {
      flex: 1 1 auto;
      display: flex;
      min-height: 0;
    }

    /* ── Panel Lista de mensajes ─────────────────────────────────────────────────────────── */
    .list {
      flex: 0 0 var(--list-width);
      width: var(--list-width);
      display: flex;
      flex-direction: column;
      min-height: 0;
      border-right: 1px solid var(--border-color);
    }
    .msg-list {
      flex: 1 1 auto;
      min-height: 0;
      overflow: auto;
    }
    .msg {
      display: grid;
      grid-template-columns: auto 1fr auto;
      grid-template-rows: auto auto;
      gap: 0.1rem 0.6rem;
      padding: 0.65rem 0.75rem;
      border-bottom: 1px solid var(--border-color-soft);
      cursor: pointer;
      transition: background-color 150ms ease;
    }
    .msg .avatar {
      grid-row: 1 / span 2;
      align-self: start;
    }
    .msg ion-avatar {
      width: 36px;
      height: 36px;
      display: grid;
      place-items: center;
      background: color-mix(in srgb, var(--primary) 16%, transparent);
      color: var(--primary);
      font-size: 13px;
      font-weight: 600;
    }
    .msg .top { display: flex; align-items: baseline; gap: 0.4rem; min-width: 0; }
    .msg .from { flex: 1 1 auto; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 14px; }
    .msg .date { flex: 0 0 auto; font-size: 11.5px; color: var(--color-muted); }
    .msg .subject { font-size: 13.5px; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .msg .preview { grid-column: 2 / span 2; font-size: 12.5px; color: var(--color-muted); min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .msg .star {
      grid-row: 1 / span 2;
      align-self: start;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      border: 0;
      background: none;
      padding: 0.15rem;
      cursor: pointer;
      color: var(--color-muted);
      transition: color 150ms ease, transform 120ms ease;
    }
    .msg .star ion-icon { font-size: 17px; }
    .msg .star.on { color: var(--warning); }
    .msg .star:active { transform: scale(var(--press-scale)); }
    /* Punto de NO LEÍDO + negrita en remitente/asunto. */
    .msg.unread .from,
    .msg.unread .subject { font-weight: 700; }
    .msg.unread .dot {
      grid-row: 1 / span 2;
      align-self: center;
      width: 8px;
      height: 8px;
      border-radius: 999px;
      background: var(--primary);
    }
    .msg.active { background: color-mix(in srgb, var(--primary) 10%, transparent); }
    @media (hover: hover) {
      .msg:hover { background: var(--row-hover); }
      .msg.active:hover { background: color-mix(in srgb, var(--primary) 14%, transparent); }
    }
    .msg:active { transform: scale(0.998); }

    /* ── Panel Lectura (derecha) ─────────────────────────────────────────────────────────── */
    .reader {
      flex: 1 1 auto;
      display: flex;
      flex-direction: column;
      min-width: 0;
      min-height: 0;
    }
    .reader-actions {
      flex: 0 0 auto;
      display: flex;
      align-items: center;
      gap: 0.2rem;
      padding: 0.4rem 0.6rem;
      border-bottom: 1px solid var(--border-color);
      background: var(--surface-2);
    }
    .reader-actions ion-button { --box-shadow: none; margin: 0; }
    .reader-body {
      flex: 1 1 auto;
      min-height: 0;
      overflow: auto;
      padding: 1.25rem 1.5rem;
    }
    .reader-subject { margin: 0 0 0.85rem; font-size: 1.4rem; font-weight: 600; line-height: 1.25; }
    .reader-meta {
      display: flex;
      align-items: center;
      gap: 0.6rem;
      padding-bottom: 0.85rem;
      margin-bottom: 1rem;
      border-bottom: 1px solid var(--border-color-soft);
    }
    .reader-meta ion-avatar {
      width: 40px;
      height: 40px;
      flex: 0 0 auto;
      display: grid;
      place-items: center;
      background: color-mix(in srgb, var(--primary) 16%, transparent);
      color: var(--primary);
      font-size: 14px;
      font-weight: 600;
    }
    .reader-meta .who { flex: 1 1 auto; min-width: 0; }
    .reader-meta .who .name { font-weight: 600; }
    .reader-meta .who .addr,
    .reader-meta .who .to { font-size: 12.5px; color: var(--color-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .reader-meta .when { flex: 0 0 auto; font-size: 12.5px; color: var(--color-muted); }
    .reader-text { white-space: pre-wrap; line-height: 1.55; font-size: 14.5px; }

    /* Adjuntos como chips. */
    .attachments { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 1.5rem; padding-top: 1rem; border-top: 1px solid var(--border-color-soft); }
    .att-chip {
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      padding: 0.4rem 0.7rem;
      border: 1px solid var(--border-color);
      border-radius: 10px;
      background: var(--surface-2);
      font-size: 12.5px;
    }
    .att-chip ion-icon { font-size: 16px; color: var(--color-muted); }
    .att-chip .att-size { color: var(--color-muted); }

    /* ── Estados vacíos (REUSO ok-empty-state) ──────────────────────────────────────────── */
    .empty-wrap { flex: 1 1 auto; display: flex; align-items: center; justify-content: center; min-height: 0; padding: 1rem; }

    /* ── Botón atrás (solo visible en vista móvil) ──────────────────────────────────────── */
    .back { display: none; }
    .back ion-button { --box-shadow: none; margin: 0; }

    /* ── Responsive (móvil): tabs siempre arriba, UN panel del cuerpo a la vez ──────────── */
    @media (max-width: 760px) {
      .body { position: relative; }
      .list,
      .reader {
        position: absolute;
        inset: 0;
        flex: none;
        width: 100%;
        border-right: 0;
        background: var(--background);
      }
      /* Solo el panel correspondiente a la vista móvil activa queda visible. */
      :host([data-mview='list']) .reader,
      :host([data-mview='message']) .list { display: none; }
      .back { display: flex; align-items: center; }
    }

    @media (prefers-reduced-motion: reduce) {
      .tab:active,
      .msg:active,
      .msg .star:active { transform: none; }
    }
  `;

  /** Carpetas del buzón. */
  @property({ attribute: false }) folders: OkMailFolder[] = [];
  /** Mensajes (de todas las carpetas; se filtran por `activeFolder`). */
  @property({ attribute: false }) messages: OkMailMessage[] = [];
  /** Id de la carpeta activa. */
  @property({ attribute: 'active-folder' }) activeFolder = '';
  /** Id del mensaje seleccionado (panel de lectura). */
  @property({ attribute: 'active-message' }) activeMessage = '';
  /** Muestra el buscador en la lista de mensajes. */
  @property({ type: Boolean }) searchable = true;
  /** Overrides de textos humanos (i18n). Se fusionan sobre los defaults en inglés. */
  @property({ attribute: false }) labels: Partial<OkMailLabels> = {};

  /** Textos efectivos (defaults inglés + overrides). */
  private get t(): OkMailLabels {
    return { ...DEFAULT_LABELS, ...this.labels };
  }

  // Texto del buscador (filtra preview/asunto/remitente en memoria).
  @state() private q = '';

  private emit<T>(type: string, detail: T): void {
    this.dispatchEvent(new CustomEvent<T>(type, { detail, bubbles: true, composed: true }));
  }

  /** Vista móvil derivada del estado activo: las tabs están siempre arriba, así que el cuerpo
   * solo alterna entre la lista y la lectura (message si hay mensaje seleccionado, si no list). */
  private get mobileView(): 'list' | 'message' {
    return this.activeMessage ? 'message' : 'list';
  }

  // Refleja la vista móvil en un atributo del host para que el CSS responsive muestre un panel.
  updated(): void {
    this.setAttribute('data-mview', this.mobileView);
  }

  /** Iniciales de un nombre para el avatar (p.ej. "Ana Pérez" → "AP"). */
  private initials(name: string): string {
    const parts = name.trim().split(/\s+/).filter(Boolean);
    if (parts.length === 0) return '?';
    const first = parts[0][0] ?? '';
    const last = parts.length > 1 ? parts[parts.length - 1][0] ?? '' : '';
    return (first + last).toUpperCase();
  }

  /** Fecha en formato corto con Intl (hora si es hoy, día/mes si es este año, si no fecha completa). */
  private fmtDate(iso: string): string {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return '';
    const now = new Date();
    const sameDay = d.toDateString() === now.toDateString();
    if (sameDay) return new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit' }).format(d);
    if (d.getFullYear() === now.getFullYear()) {
      return new Intl.DateTimeFormat(undefined, { day: '2-digit', month: 'short' }).format(d);
    }
    return new Intl.DateTimeFormat(undefined, { day: '2-digit', month: 'short', year: 'numeric' }).format(d);
  }

  /** Tamaño legible de un adjunto (B/KB/MB). */
  private fmtSize(bytes?: number): string {
    if (bytes == null) return '';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  /** Mensajes de la carpeta activa filtrados por el buscador (preview/asunto/remitente). */
  private get folderMessages(): OkMailMessage[] {
    let result = this.messages.filter((m) => m.folderId === this.activeFolder);
    const needle = this.q.trim().toLowerCase();
    if (needle) {
      result = result.filter((m) =>
        [m.subject, m.preview ?? '', m.from.name, m.from.email].some((s) => s.toLowerCase().includes(needle)),
      );
    }
    return result;
  }

  private onFolderSelect(id: string): void {
    this.activeFolder = id;
    this.activeMessage = ''; // al cambiar de carpeta se deselecciona el mensaje.
    this.emit('ok-folder-select', { id });
  }

  private onSearch = (ev: Event): void => {
    const value = (ev.target as HTMLInputElement).value ?? '';
    this.q = value;
    this.emit('ok-search', { query: value });
  };

  private onMessageSelect(message: OkMailMessage): void {
    this.activeMessage = message.id;
    this.emit('ok-message-select', { id: message.id, message });
  }

  private onStar(ev: Event, m: OkMailMessage): void {
    ev.stopPropagation(); // no abrir el mensaje al togglear la estrella.
    this.emit('ok-star', { id: m.id, starred: !m.starred });
  }

  // ── Render: Cabecera superior (Redactar + buscador) ───────────────────────────────────────
  private renderTopbar(): unknown {
    return html`
      <div class="topbar">
        <ion-button @click=${() => this.emit('ok-compose', {})}>
          <ion-icon slot="start" name="create-outline"></ion-icon>
          ${this.t.compose}
        </ion-button>
        ${this.searchable
          ? html`<ion-searchbar
              .value=${this.q}
              placeholder=${this.t.searchPlaceholder}
              debounce="200"
              @ionInput=${this.onSearch}
            ></ion-searchbar>`
          : nothing}
      </div>
    `;
  }

  // ── Render: Barra de TABS de carpetas (scroll horizontal) ─────────────────────────────────
  private renderTabs(): unknown {
    return html`
      <nav class="tabs" role="tablist">
        ${repeat(
          this.folders,
          (f) => f.id,
          (f) => html`
            <button
              class=${`tab${f.id === this.activeFolder ? ' active' : ''}`}
              role="tab"
              aria-selected=${f.id === this.activeFolder ? 'true' : 'false'}
              @click=${() => this.onFolderSelect(f.id)}
            >
              ${f.icon ? html`<ion-icon name=${f.icon}></ion-icon>` : nothing}
              <span class="tlabel">${f.label}</span>
              ${f.count ? html`<ion-badge>${f.count}</ion-badge>` : nothing}
            </button>
          `,
        )}
      </nav>
    `;
  }

  // ── Render: Panel Lista de mensajes ──────────────────────────────────────────────────────────
  private renderList(): unknown {
    const msgs = this.folderMessages;
    return html`
      <section class="list">
        <div class="msg-list">
          ${msgs.length === 0
            ? html`<div class="empty-wrap"><ok-empty-state icon="mail-outline" heading=${this.t.noMessages}></ok-empty-state></div>`
            : repeat(
                msgs,
                (m) => m.id,
                (m) => {
                  const unread = m.read === false;
                  return html`
                    <article
                      class=${`msg${unread ? ' unread' : ''}${m.id === this.activeMessage ? ' active' : ''}`}
                      @click=${() => this.onMessageSelect(m)}
                    >
                      ${unread ? html`<span class="dot" aria-label=${this.t.unread}></span>` : nothing}
                      <span class="avatar"><ion-avatar>${this.initials(m.from.name)}</ion-avatar></span>
                      <div class="top">
                        <span class="from">${m.from.name}</span>
                        <span class="date">${this.fmtDate(m.date)}</span>
                      </div>
                      <span class="subject">${m.subject}</span>
                      ${m.preview ? html`<span class="preview">${m.preview}</span>` : nothing}
                      <button
                        class=${`star${m.starred ? ' on' : ''}`}
                        aria-label=${m.starred ? this.t.unstar : this.t.star}
                        @click=${(e: Event) => this.onStar(e, m)}
                      >
                        <ion-icon name=${m.starred ? 'star' : 'star-outline'}></ion-icon>
                      </button>
                    </article>
                  `;
                },
              )}
        </div>
      </section>
    `;
  }

  // ── Render: Panel Lectura ─────────────────────────────────────────────────────────────────────
  private renderReader(): unknown {
    const m = this.messages.find((x) => x.id === this.activeMessage);
    if (!m) {
      return html`
        <section class="reader">
          <div class="empty-wrap">
            <ok-empty-state icon="mail-open-outline" heading=${this.t.selectMessage}></ok-empty-state>
          </div>
        </section>
      `;
    }
    return html`
      <section class="reader">
        <div class="reader-actions">
          <span class="back">
            <ion-button fill="clear" size="small" aria-label=${this.t.back} @click=${() => { this.activeMessage = ''; }}>
              <ion-icon slot="icon-only" name="chevron-back"></ion-icon>
            </ion-button>
          </span>
          <ion-button fill="clear" size="small" aria-label=${this.t.reply} @click=${() => this.emit('ok-reply', { id: m.id })}>
            <ion-icon slot="icon-only" name="arrow-undo-outline"></ion-icon>
          </ion-button>
          <ion-button fill="clear" size="small" aria-label=${this.t.forward} @click=${() => this.emit('ok-forward', { id: m.id })}>
            <ion-icon slot="icon-only" name="arrow-redo-outline"></ion-icon>
          </ion-button>
          <ion-button fill="clear" size="small" aria-label=${this.t.archive} @click=${() => this.emit('ok-archive', { id: m.id })}>
            <ion-icon slot="icon-only" name="archive-outline"></ion-icon>
          </ion-button>
          <ion-button fill="clear" size="small" color="danger" aria-label=${this.t.delete} @click=${() => this.emit('ok-delete', { id: m.id })}>
            <ion-icon slot="icon-only" name="trash-outline"></ion-icon>
          </ion-button>
        </div>
        <div class="reader-body">
          <h1 class="reader-subject">${m.subject}</h1>
          <header class="reader-meta">
            <ion-avatar>${this.initials(m.from.name)}</ion-avatar>
            <div class="who">
              <div class="name">${m.from.name}</div>
              <div class="addr">${m.from.email}</div>
              ${m.to && m.to.length ? html`<div class="to">${this.t.to} ${m.to.join(', ')}</div>` : nothing}
            </div>
            <span class="when">${this.fmtDate(m.date)}</span>
          </header>
          <div class="reader-text">${m.body ?? m.preview ?? ''}</div>
          ${m.attachments && m.attachments.length
            ? html`
                <div class="attachments">
                  ${m.attachments.map(
                    (a) => html`
                      <span class="att-chip">
                        <ion-icon name="document-attach-outline"></ion-icon>
                        <span>${a.name}</span>
                        ${a.size != null ? html`<span class="att-size">${this.fmtSize(a.size)}</span>` : nothing}
                      </span>
                    `,
                  )}
                </div>
              `
            : nothing}
        </div>
      </section>
    `;
  }

  render(): unknown {
    return html`
      ${this.renderTopbar()}
      ${this.renderTabs()}
      <div class="body">${this.renderList()}${this.renderReader()}</div>
    `;
  }
}

define('ok-mail', OkMail);

declare global {
  interface HTMLElementTagNameMap {
    'ok-mail': OkMail;
  }
}
