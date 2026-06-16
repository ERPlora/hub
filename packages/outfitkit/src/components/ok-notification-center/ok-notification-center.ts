import { LitElement, html, css, nothing } from 'lit';
import { property } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// ok-notification-center — bandeja de notificaciones estilo drawer lateral derecho. Ionic NO lo
// trae: es el panel de "inbox" típico de un ERP (campana → panel deslizante a la derecha con lista
// de avisos status-tintados, chips de filtro, contador de no-leídas y pie "marcar todas leídas").
// AUTOCONTENIDO: scrim + panel propios (CSS en el shadow). Solo usa `ion-icon` (lo registra el host)
// para iconos por nombre; las notificaciones pueden traer su propio SVG inline en `icon`.
// Se compone como ok-drawer (lado 'end', columna header · filtros · lista scrollable · footer).
//
// Props:
//   • `.items`   → Array<OkNotification> (datos declarativos, no demo hardcodeada).
//   • `.filters` → Array<OkNotifFilter> (chips); el activo = prop `active`.
//   • `active`   → id del filtro activo (reflejado).
//   • `open`     → abierto/cerrado (reflejado, modo controlado por el padre).
//   • `title`    → título de la cabecera (default "Notifications").
//   • `.labels`  → textos traducibles (default inglés).
// El contador de no-leídas se DERIVA de items (unread === true).
//
// Eventos (bubbles + composed):
//   • `ok-read`     detail { id }      al clicar una notificación no leída
//   • `ok-read-all` detail { }          al pulsar el footer "marcar todas leídas"
//   • `ok-filter`   detail { id }      al elegir un chip de filtro
//   • `ok-close`    detail { reason }  cancelable, en cada gesto de cierre (scrim/esc/X)
//   • `ok-open`     detail { open: true }
//
// El filtrado VISIBLE lo decide el consumidor (re-pasa `items` ya filtradas al cambiar `active`),
// como un data-table controlado; el componente solo emite `ok-filter` y resalta el chip activo.

/** Variante de color del icono redondo (tinte de estado). */
export type OkNotifVariant = 'leaf' | 'warn' | 'info' | 'brand';

/** Una notificación de la bandeja. */
export interface OkNotification {
  /** Identificador único (clave de lectura/selección). */
  id: string;
  /**
   * Icono del avatar redondo. Dos formas:
   *   • NOMBRE de ionicon (p. ej. `checkmark-outline`) → `ion-icon name`;
   *   • SVG ya resuelto (`<svg…>` o `data:` URI) → `ion-icon icon` (hosts offline/horneados).
   * Si se omite se usa un icono de campana por defecto.
   */
  icon?: string;
  /** Tinte de estado del avatar (default neutro). */
  variant?: OkNotifVariant;
  /** Texto principal. Puede traer HTML simple (<b>…</b>) → se pinta con unsafeHTML controlado. */
  text: string;
  /** Línea secundaria mono (contexto, cita, referencia). */
  meta?: string;
  /** Marca de tiempo relativa ya formateada por el consumidor (p. ej. "12:42", "ayer"). */
  time?: string;
  /** Si es no-leída: marca el punto lateral y cuenta en el badge. */
  unread?: boolean;
}

/** Chip de filtro de la cabecera. */
export interface OkNotifFilter {
  /** Identificador del filtro (se emite en `ok-filter`). */
  id: string;
  /** Texto visible del chip. */
  label: string;
}

/** Textos humanos (i18n; default inglés, override vía prop `labels`). */
export interface OkNotifLabels {
  /** Texto del footer (marcar todas como leídas). */
  markAllRead: string;
  /** aria-label del botón de cerrar (X). */
  close: string;
  /** Título del estado vacío. */
  emptyTitle: string;
  /** Texto del estado vacío. */
  emptyText: string;
}

const DEFAULT_LABELS: OkNotifLabels = {
  markAllRead: 'Mark all read',
  close: 'Close',
  emptyTitle: 'All caught up',
  emptyText: 'No notifications to show.',
};

// SVG de campana por defecto cuando una notificación no trae icono propio.
const BELL_SVG =
  '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
  'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
  '<path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"/>' +
  '<path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>';

export class OkNotificationCenter extends LitElement {
  static styles = css`
    :host {
      /* Vars overridable (estilo Ionic), default = cadena --ok-* → --ion-* → hex */
      --color: var(--ok-text, var(--ion-text-color, #1c1b17));
      --color-muted: var(--ok-text-muted, rgba(var(--ion-text-color-rgb, 28, 27, 23), 0.62));
      --color-faint: var(--ok-text-faint, rgba(var(--ion-text-color-rgb, 28, 27, 23), 0.45));
      --panel-bg: var(--ok-surface, var(--ion-card-background, var(--ion-background-color, #ffffff)));
      --head-bg: var(--ok-surface-2, rgba(var(--ion-text-color-rgb, 28, 27, 23), 0.025));
      --hover-bg: var(--ok-hover, rgba(var(--ion-text-color-rgb, 28, 27, 23), 0.05));
      --chip-active-bg: var(--ok-chip-active, rgba(var(--ion-text-color-rgb, 28, 27, 23), 0.09));
      --border-soft: var(--ok-border-soft, rgba(var(--ion-text-color-rgb, 28, 27, 23), 0.1));
      --scrim-bg: var(--ok-scrim, rgba(0, 0, 0, 0.4));
      --shadow: var(--ok-shadow-md, 0 10px 40px rgba(0, 0, 0, 0.22));
      --radius: var(--ok-radius, 12px);
      --font: var(--ok-font, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif);
      --font-mono: var(--ok-font-mono, ui-monospace, 'SF Mono', 'Roboto Mono', monospace);
      --brand: var(--ok-primary, var(--ion-color-primary, #3880ff));
      --brand-contrast: var(--ok-primary-contrast, var(--ion-color-primary-contrast, #ffffff));
      /* Tintes de estado de los avatares. */
      --c-leaf: var(--ok-success, var(--ion-color-success, #2dd36f));
      --c-warn: var(--ok-warning, var(--ion-color-warning, #ffc409));
      --c-info: var(--ok-info, var(--ion-color-tertiary, #6a64ff));

      /* El host no ocupa caja: scrim y panel van a position:fixed sobre todo. */
      display: contents;
    }

    /* Scrim a pantalla completa. */
    .scrim {
      position: fixed;
      inset: 0;
      z-index: 2000;
      background: var(--scrim-bg);
      animation: fade-in 180ms ease;
    }

    /* Panel lateral derecho: columna header · filtros · lista (scroll) · footer. */
    .panel {
      position: fixed;
      top: 0;
      bottom: 0;
      inset-inline-end: 0;
      z-index: 2001;
      width: var(--ok-notif-width, 380px);
      max-width: 100vw;
      display: flex;
      flex-direction: column;
      box-sizing: border-box;
      background: var(--panel-bg);
      color: var(--color);
      font-family: var(--font);
      box-shadow: var(--shadow);
      border-inline-start: 1px solid var(--border-soft);
      animation: slide-in 220ms cubic-bezier(0.32, 0.72, 0, 1);
    }

    @keyframes fade-in {
      from { opacity: 0; }
      to { opacity: 1; }
    }
    @keyframes slide-in {
      from { transform: translateX(100%); }
      to { transform: translateX(0); }
    }
    @media (prefers-reduced-motion: reduce) {
      .scrim,
      .panel {
        animation: none;
      }
    }

    /* Cabecera: título + badge de no-leídas + botón cerrar. */
    .head {
      flex: 0 0 auto;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 0.5rem;
      padding: 0.85rem 1rem;
      border-bottom: 1px solid var(--border-soft);
    }
    .title {
      display: inline-flex;
      align-items: center;
      margin: 0;
      font-size: 0.95rem;
      font-weight: 600;
      color: var(--color);
    }
    .badge {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 18px;
      height: 18px;
      padding: 0 5px;
      margin-inline-start: 8px;
      border-radius: 999px;
      background: var(--brand);
      color: var(--brand-contrast);
      font-family: var(--font-mono);
      font-size: 0.625rem;
      font-weight: 600;
      line-height: 1;
    }
    .close-btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 34px;
      height: 34px;
      padding: 0;
      border: 0;
      background: none;
      color: var(--color-muted);
      cursor: pointer;
      border-radius: 50%;
      transition: background-color 150ms ease;
    }
    @media (hover: hover) {
      .close-btn:hover {
        background: var(--hover-bg);
      }
    }
    .close-btn ion-icon {
      font-size: 1.25rem;
    }

    /* Fila de chips de filtro. */
    .filters {
      flex: 0 0 auto;
      display: flex;
      flex-wrap: wrap;
      gap: 4px;
      padding: 0.5rem 0.65rem;
      background: var(--head-bg);
      border-bottom: 1px solid var(--border-soft);
    }
    .chip {
      padding: 4px 10px;
      border: 0;
      background: transparent;
      border-radius: 8px;
      color: var(--color-muted);
      font: inherit;
      font-size: 0.72rem;
      cursor: pointer;
      transition: background-color 150ms ease, color 150ms ease;
    }
    @media (hover: hover) {
      .chip:hover {
        background: var(--hover-bg);
      }
    }
    .chip[aria-pressed='true'] {
      background: var(--chip-active-bg);
      color: var(--color);
      font-weight: 600;
    }

    /* Lista scrollable. */
    .list {
      flex: 1 1 auto;
      min-height: 0;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
    }

    /* Fila de notificación: avatar · cuerpo · hora. */
    .item {
      position: relative;
      display: grid;
      grid-template-columns: 32px 1fr auto;
      gap: 10px;
      width: 100%;
      box-sizing: border-box;
      padding: 0.75rem 1rem;
      border: 0;
      border-bottom: 1px solid var(--border-soft);
      background: none;
      color: inherit;
      font: inherit;
      text-align: start;
      cursor: pointer;
      transition: background-color 150ms ease;
    }
    @media (hover: hover) {
      .item:hover {
        background: var(--hover-bg);
      }
    }
    .item:last-child {
      border-bottom: 0;
    }
    /* Punto de no-leída a la izquierda. */
    .item.unread::before {
      content: '';
      position: absolute;
      left: 5px;
      top: 1.05rem;
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: var(--brand);
    }

    /* Avatar redondo status-tintado. */
    .avatar {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 32px;
      height: 32px;
      border-radius: 50%;
      background: var(--hover-bg);
      color: var(--color-muted);
    }
    .avatar.leaf {
      background: color-mix(in srgb, var(--c-leaf) 18%, transparent);
      color: var(--c-leaf);
    }
    .avatar.warn {
      background: color-mix(in srgb, var(--c-warn) 20%, transparent);
      color: var(--c-warn);
    }
    .avatar.info {
      background: color-mix(in srgb, var(--c-info) 18%, transparent);
      color: var(--c-info);
    }
    .avatar.brand {
      background: color-mix(in srgb, var(--brand) 18%, transparent);
      color: var(--brand);
    }
    .avatar ion-icon {
      font-size: 1rem;
    }
    .avatar svg {
      display: block;
    }

    .body {
      min-width: 0;
    }
    .text {
      font-size: 0.8125rem;
      line-height: 1.45;
      color: var(--color);
      overflow-wrap: anywhere;
    }
    .text b {
      font-weight: 600;
    }
    .meta {
      margin-top: 2px;
      font-family: var(--font-mono);
      font-size: 0.6875rem;
      color: var(--color-faint);
      overflow-wrap: anywhere;
    }
    .time {
      font-family: var(--font-mono);
      font-size: 0.6875rem;
      color: var(--color-faint);
      white-space: nowrap;
    }

    /* Estado vacío. */
    .empty {
      flex: 1 1 auto;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 8px;
      padding: 2rem 1.25rem;
      text-align: center;
    }
    .empty .ic {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 52px;
      height: 52px;
      border-radius: 50%;
      background: var(--hover-bg);
      color: var(--color-faint);
      margin-bottom: 4px;
    }
    .empty .ic ion-icon {
      font-size: 1.5rem;
    }
    .empty .e-title {
      font-size: 0.95rem;
      font-weight: 600;
      color: var(--color);
    }
    .empty .e-text {
      font-size: 0.8125rem;
      color: var(--color-faint);
      max-width: 30ch;
      line-height: 1.5;
    }

    /* Footer: marcar todas leídas. */
    .foot {
      flex: 0 0 auto;
      padding: 0.6rem 1rem calc(0.6rem + env(safe-area-inset-bottom, 0px));
      border-top: 1px solid var(--border-soft);
      text-align: center;
    }
    .foot button {
      border: 0;
      background: none;
      color: var(--brand);
      font: inherit;
      font-size: 0.8125rem;
      font-weight: 600;
      cursor: pointer;
      padding: 4px 8px;
      border-radius: 8px;
      transition: background-color 150ms ease;
    }
    @media (hover: hover) {
      .foot button:hover {
        background: var(--hover-bg);
      }
    }
    .foot button[disabled] {
      color: var(--color-faint);
      cursor: default;
    }

    /* Móvil: panel a pantalla completa. */
    @media (max-width: 480px) {
      .panel {
        width: 100vw;
        border-inline-start: 0;
      }
    }
  `;

  /** Notificaciones a mostrar (datos declarativos). */
  @property({ attribute: false }) items: OkNotification[] = [];

  /** Chips de filtro de la cabecera. */
  @property({ attribute: false }) filters: OkNotifFilter[] = [];

  /** Id del filtro activo. */
  @property({ reflect: true }) active?: string;

  /** Abierto/cerrado (modo controlado por el padre). */
  @property({ type: Boolean, reflect: true }) open = false;

  /** Título de la cabecera. */
  @property() title = 'Notifications';

  /** Textos traducibles (merge sobre los defaults en inglés). */
  @property({ attribute: false }) labels: Partial<OkNotifLabels> = {};

  // Textos efectivos.
  private get t(): OkNotifLabels {
    return { ...DEFAULT_LABELS, ...this.labels };
  }

  // Contador derivado de no-leídas.
  private get unreadCount(): number {
    return this.items.reduce((n, it) => n + (it.unread ? 1 : 0), 0);
  }

  // Handler de Esc (cierra).
  private readonly onKeydown = (e: KeyboardEvent): void => {
    if (e.key === 'Escape' && this.open) this.requestClose('esc');
  };

  connectedCallback(): void {
    super.connectedCallback();
    document.addEventListener('keydown', this.onKeydown);
  }

  disconnectedCallback(): void {
    super.disconnectedCallback();
    document.removeEventListener('keydown', this.onKeydown);
  }

  // Un icono es «SVG ya resuelto» si es un string `<svg…>` o un `data:` URI.
  private isResolvedSvg(icon: string): boolean {
    return /^\s*</.test(icon) || icon.startsWith('data:');
  }

  // Gesto de cierre: emite `ok-close` CANCELABLE; si nadie lo veta, cierra solo (fallback).
  private requestClose(reason: 'scrim' | 'esc' | 'button'): void {
    const ev = new CustomEvent('ok-close', {
      detail: { reason },
      bubbles: true,
      composed: true,
      cancelable: true,
    });
    this.dispatchEvent(ev);
    if (!ev.defaultPrevented) this.open = false;
  }

  private onItemClick(it: OkNotification): void {
    if (!it.unread) return;
    this.dispatchEvent(
      new CustomEvent('ok-read', { detail: { id: it.id }, bubbles: true, composed: true }),
    );
  }

  private onMarkAll(): void {
    if (this.unreadCount === 0) return;
    this.dispatchEvent(
      new CustomEvent('ok-read-all', { detail: {}, bubbles: true, composed: true }),
    );
  }

  private onFilter(f: OkNotifFilter): void {
    this.dispatchEvent(
      new CustomEvent('ok-filter', { detail: { id: f.id }, bubbles: true, composed: true }),
    );
  }

  // Emite ok-open al pasar a abierto (detecta el flanco en updated).
  protected updated(changed: Map<string, unknown>): void {
    if (changed.has('open') && this.open) {
      this.dispatchEvent(
        new CustomEvent('ok-open', { detail: { open: true }, bubbles: true, composed: true }),
      );
    }
  }

  private renderAvatar(it: OkNotification): unknown {
    const icon = it.icon ?? BELL_SVG;
    return html`<span class="avatar ${it.variant ?? ''}" aria-hidden="true">
      ${this.isResolvedSvg(icon)
        ? // SVG resuelto: lo pinta ion-icon vía prop `icon`.
          html`<ion-icon .icon=${icon}></ion-icon>`
        : html`<ion-icon .name=${icon}></ion-icon>`}
    </span>`;
  }

  // Pinta el texto principal interpretando SOLO <b>…</b> (sin HTML arbitrario, seguro para CSP).
  private renderText(text: string): unknown {
    const parts: unknown[] = [];
    const re = /<b>(.*?)<\/b>/gis;
    let last = 0;
    let m: RegExpExecArray | null;
    while ((m = re.exec(text)) !== null) {
      if (m.index > last) parts.push(text.slice(last, m.index));
      parts.push(html`<b>${m[1]}</b>`);
      last = m.index + m[0].length;
    }
    if (last < text.length) parts.push(text.slice(last));
    return parts.length ? parts : text;
  }

  private renderItem(it: OkNotification): unknown {
    return html`<button
      type="button"
      class="item ${it.unread ? 'unread' : ''}"
      @click=${() => this.onItemClick(it)}
    >
      ${this.renderAvatar(it)}
      <span class="body">
        <span class="text">${this.renderText(it.text)}</span>
        ${it.meta ? html`<span class="meta">${it.meta}</span>` : nothing}
      </span>
      ${it.time ? html`<span class="time">${it.time}</span>` : nothing}
    </button>`;
  }

  private renderEmpty(): unknown {
    return html`<div class="empty">
      <span class="ic" aria-hidden="true"><ion-icon name="notifications-off-outline"></ion-icon></span>
      <span class="e-title">${this.t.emptyTitle}</span>
      <span class="e-text">${this.t.emptyText}</span>
    </div>`;
  }

  render(): unknown {
    if (!this.open) return nothing;
    const count = this.unreadCount;
    return html`
      <div class="scrim" @click=${() => this.requestClose('scrim')}></div>
      <aside
        class="panel"
        role="dialog"
        aria-modal="true"
        aria-label=${this.title}
      >
        <header class="head">
          <h2 class="title">
            ${this.title}${count > 0
              ? html`<span class="badge" aria-label="${count} unread">${count}</span>`
              : nothing}
          </h2>
          <button
            type="button"
            class="close-btn"
            aria-label=${this.t.close}
            @click=${() => this.requestClose('button')}
          >
            <ion-icon name="close-outline"></ion-icon>
          </button>
        </header>

        ${this.filters.length
          ? html`<div class="filters" role="group" aria-label="Filters">
              ${this.filters.map(
                (f) => html`<button
                  type="button"
                  class="chip"
                  aria-pressed=${this.active === f.id ? 'true' : 'false'}
                  @click=${() => this.onFilter(f)}
                >
                  ${f.label}
                </button>`,
              )}
            </div>`
          : nothing}

        ${this.items.length
          ? html`<div class="list" role="list">${this.items.map((it) => this.renderItem(it))}</div>`
          : this.renderEmpty()}

        <footer class="foot">
          <button type="button" ?disabled=${count === 0} @click=${() => this.onMarkAll()}>
            ${this.t.markAllRead}
          </button>
        </footer>
      </aside>
    `;
  }
}

define('ok-notification-center', OkNotificationCenter);

declare global {
  interface HTMLElementTagNameMap {
    'ok-notification-center': OkNotificationCenter;
  }
}
