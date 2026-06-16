import { LitElement, html, css } from 'lit';
import { property } from 'lit/decorators.js';
import { define } from '../../base/define.js';

/** Color de acento de la tarjeta de evento. */
export type OkEventCardColor = 'brand' | 'leaf' | 'warn' | 'danger' | 'info';

/** Tamaño de la tarjeta de evento. */
export type OkEventCardSize = 'sm' | 'md' | 'lg';

/** Asistente para la pila de avatares solapados. */
export interface OkEventAttendee {
  /** Nombre completo (se usa para iniciales y title). */
  name?: string;
  /** URL de imagen; si falta se muestran iniciales. */
  avatar?: string;
  /** Iniciales explícitas (si no, se derivan del nombre). */
  initials?: string;
}

// ok-event-card — tarjeta de evento de calendario con bloque de fecha.
// Rejilla: bloque de fecha a la izquierda (día grande + mes, fondo accent-soft) +
// cuerpo (título, hora/lugar con iconos inline, pila de avatares solapados con +N).
// Estado is-now: pulso animado en el borde izquierdo (color de acento).
// Porta el diseño de .ux-event-card (commerce.css) a Shadow DOM con tokens --ok-*/--ion-*.
export class OkEventCard extends LitElement {
  static styles = css`
    :host {
      display: block;
      width: 100%;
      box-sizing: border-box;

      /* Tokens propios estilo Ionic (overridables): --ok-* → --ion-* → hex. */
      --accent: var(--ok-color-primary, var(--ion-color-primary, #3880ff));
      --accent-soft: var(--ok-color-primary-soft, color-mix(in srgb, var(--accent) 12%, transparent));
      --bg: var(--ok-surface, var(--ion-card-background, var(--ion-background-color, #ffffff)));
      --line: var(--ok-border-color, var(--ion-border-color, #e0e0e0));
      --line-strong: var(--ok-border-color-strong, color-mix(in srgb, var(--line) 70%, var(--ink)));
      --ink: var(--ok-text-color, var(--ion-text-color, #1f2933));
      --ink-2: var(--ok-text-color-2, color-mix(in srgb, var(--ink) 80%, transparent));
      --ink-3: var(--ok-color-medium, var(--ion-color-medium, #6b7280));
      --avatar-bg: var(--ok-color-light, var(--ion-color-light, #f1f2f4));
      --radius: var(--ok-radius-lg, 14px);
      --radius-inner: var(--ok-radius-md, 10px);
      --shadow: var(--ok-shadow-sm, 0 1px 2px rgba(0, 0, 0, 0.06), 0 2px 8px rgba(0, 0, 0, 0.04));
    }

    /* Variantes de color: redefinen accent + accent-soft. */
    :host([color='brand']) {
      --accent: var(--ok-color-primary, var(--ion-color-primary, #3880ff));
    }
    :host([color='leaf']) {
      --accent: var(--ok-color-success, var(--ion-color-success, #2dd36f));
    }
    :host([color='warn']) {
      --accent: var(--ok-color-warning, var(--ion-color-warning, #ffc409));
    }
    :host([color='danger']) {
      --accent: var(--ok-color-danger, var(--ion-color-danger, #eb445a));
    }
    :host([color='info']) {
      --accent: var(--ok-color-tertiary, var(--ion-color-tertiary, #5260ff));
    }
    /* accent-soft se recalcula siempre a partir del accent actual. */
    :host([color]) {
      --accent-soft: color-mix(in srgb, var(--accent) 12%, transparent);
    }

    .card {
      display: grid;
      grid-template-columns: auto 1fr;
      gap: 1rem;
      align-items: stretch;
      box-sizing: border-box;
      width: 100%;
      background: var(--bg);
      border: 1px solid var(--line);
      border-left: 3px solid var(--accent);
      border-radius: var(--radius);
      padding: 1rem;
      transition: transform 0.15s ease-out, border-color 0.15s, box-shadow 0.15s;
    }
    .card:hover {
      transform: translateY(-1px);
      border-color: var(--line-strong);
      border-left-color: var(--accent);
      box-shadow: var(--shadow);
    }

    /* Bloque de fecha */
    .date-block {
      display: grid;
      place-content: center;
      text-align: center;
      background: var(--accent-soft);
      color: var(--accent);
      border-radius: var(--radius-inner);
      padding: 0.375rem 0.625rem;
      min-width: 64px;
    }
    .day {
      font-size: 1.75rem;
      font-weight: 700;
      letter-spacing: -0.02em;
      line-height: 1;
      font-variant-numeric: tabular-nums;
    }
    .month {
      font-size: 0.625rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.12em;
      margin-top: 2px;
    }

    /* Cuerpo */
    .body {
      display: flex;
      flex-direction: column;
      gap: 0.25rem;
      min-width: 0;
    }
    .title {
      margin: 0;
      font-size: 0.9375rem;
      font-weight: 600;
      letter-spacing: -0.01em;
      color: var(--ink);
      line-height: 1.35;
      text-overflow: ellipsis;
      overflow: hidden;
      white-space: nowrap;
    }
    .meta {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-size: 0.75rem;
      color: var(--ink-3);
      min-width: 0;
    }
    .meta span {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .meta svg {
      width: 12px;
      height: 12px;
      flex-shrink: 0;
    }

    /* Asistentes */
    .attendees {
      display: inline-flex;
      align-items: center;
      gap: 0.5rem;
      margin-top: 0.25rem;
      font-size: 0.75rem;
      color: var(--ink-3);
    }
    .avatars {
      display: inline-flex;
    }
    .avatars > * {
      width: 22px;
      height: 22px;
      border-radius: 50%;
      border: 2px solid var(--bg);
      background: var(--avatar-bg);
      margin-left: -6px;
      display: inline-grid;
      place-items: center;
      font-size: 9px;
      font-weight: 600;
      color: var(--ink-2);
      background-size: cover;
      background-position: center;
      box-sizing: border-box;
    }
    .avatars > *:first-child {
      margin-left: 0;
    }
    .avatars .more {
      background: var(--accent-soft);
      color: var(--accent);
    }

    /* Estado "ahora": pulso en el borde izquierdo. */
    :host([now]) .card {
      border-left-width: 4px;
      animation: ok-event-now 1.6s ease-in-out infinite;
    }
    @keyframes ok-event-now {
      0%,
      100% {
        box-shadow: 0 0 0 0 transparent;
      }
      50% {
        box-shadow: -4px 0 0 0 color-mix(in srgb, var(--accent) 35%, transparent);
      }
    }

    /* Tamaño sm: layout en fila más compacto. */
    :host([size='sm']) .card {
      padding: 0.375rem 0.625rem;
      gap: 0.75rem;
    }
    :host([size='sm']) .date-block {
      display: inline-flex;
      flex-direction: row;
      align-items: baseline;
      gap: 4px;
      min-width: 0;
      padding: 2px 0.5rem;
    }
    :host([size='sm']) .day {
      font-size: 1.125rem;
    }
    :host([size='sm']) .month {
      font-size: 0.625rem;
      margin-top: 0;
    }
    :host([size='sm']) .body {
      flex-direction: row;
      align-items: center;
      gap: 0.75rem;
    }
    :host([size='sm']) .attendees {
      margin-top: 0;
    }

    /* Tamaño lg: más aire y tipografía mayor. */
    :host([size='lg']) .card {
      padding: 1.25rem;
      gap: 1.25rem;
    }
    :host([size='lg']) .day {
      font-size: 2.25rem;
    }
    :host([size='lg']) .title {
      font-size: 1.0625rem;
    }

    @media (prefers-reduced-motion: reduce) {
      :host([now]) .card {
        animation: none;
      }
      .card {
        transition: none;
      }
    }
  `;

  /** Título del evento. */
  @property() title = '';

  /**
   * Fecha del evento. Acepta un string ISO (YYYY-MM-DD…) o cualquier valor
   * parseable por Date; de ahí se derivan el día y el mes del bloque de fecha.
   * Si no se parsea, se usan `day`/`month` explícitos.
   */
  @property() date?: string;

  /** Día explícito (sobrescribe el derivado de `date`). */
  @property() day?: string;

  /** Mes explícito en texto corto (sobrescribe el derivado de `date`). */
  @property() month?: string;

  /** Hora o rango horario (texto libre, p.ej. "09:30 – 10:15"). */
  @property() time?: string;

  /** Ubicación (texto libre). */
  @property() location?: string;

  /** Color de acento. */
  @property({ reflect: true }) color: OkEventCardColor = 'brand';

  /** Tamaño de la tarjeta. */
  @property({ reflect: true }) size: OkEventCardSize = 'md';

  /** Marca el evento como "en curso" (pulso animado). */
  @property({ type: Boolean, reflect: true }) now = false;

  /** Locale para formatear el mes derivado de `date` (por defecto el del navegador). */
  @property() locale?: string;

  /** Máximo de avatares visibles antes de colapsar en "+N". */
  @property({ type: Number, attribute: 'max-avatars' }) maxAvatars = 4;

  /** Asistentes para la pila de avatares solapados. */
  @property({ attribute: false }) attendees: OkEventAttendee[] = [];

  /** Devuelve {day, month} a mostrar, derivando de `date` si hace falta. */
  private resolveDate(): { day: string; month: string } {
    if (this.day != null || this.month != null) {
      return { day: this.day ?? '', month: this.month ?? '' };
    }
    if (this.date) {
      const d = new Date(this.date);
      if (!Number.isNaN(d.getTime())) {
        const month = d
          .toLocaleString(this.locale || undefined, { month: 'short' })
          .replace('.', '');
        return { day: String(d.getDate()), month };
      }
    }
    return { day: '', month: '' };
  }

  /** Iniciales (máx. 2) a partir del nombre. */
  private initialsOf(a: OkEventAttendee): string {
    if (a.initials) return a.initials.slice(0, 2).toUpperCase();
    const parts = (a.name ?? '').trim().split(/\s+/).filter(Boolean);
    if (parts.length === 0) return '';
    const chars = parts.length === 1 ? parts[0].slice(0, 2) : parts[0][0] + parts[parts.length - 1][0];
    return chars.toUpperCase();
  }

  private renderAvatars(): unknown {
    const list = this.attendees ?? [];
    if (list.length === 0) return null;
    const max = Math.max(1, this.maxAvatars);
    const shown = list.slice(0, max);
    const extra = list.length - shown.length;
    return html`
      <div class="attendees">
        <div class="avatars" role="list" aria-label="Asistentes">
          ${shown.map((a) =>
            a.avatar
              ? html`<span
                  role="listitem"
                  title=${a.name ?? ''}
                  style=${`background-image:url("${a.avatar}")`}
                ></span>`
              : html`<span role="listitem" title=${a.name ?? ''}>${this.initialsOf(a)}</span>`,
          )}
          ${extra > 0
            ? html`<span class="more" title=${`+${extra} más`} aria-label=${`${extra} más`}
                >+${extra}</span
              >`
            : null}
        </div>
      </div>
    `;
  }

  render(): unknown {
    const { day, month } = this.resolveDate();
    return html`
      <article
        class="card"
        role="group"
        aria-label=${this.title || 'Evento'}
        aria-current=${this.now ? 'true' : 'false'}
      >
        <div class="date-block" aria-hidden=${day || month ? 'false' : 'true'}>
          ${day ? html`<span class="day">${day}</span>` : null}
          ${month ? html`<span class="month">${month}</span>` : null}
        </div>
        <div class="body">
          ${this.title ? html`<h3 class="title" title=${this.title}>${this.title}</h3>` : null}
          ${this.time
            ? html`<span class="meta">
                <!-- icono reloj inline (sin dependencias) -->
                <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
                  <circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="2" />
                  <path
                    d="M12 7v5l3 2"
                    stroke="currentColor"
                    stroke-width="2"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  />
                </svg>
                <span>${this.time}</span>
              </span>`
            : null}
          ${this.location
            ? html`<span class="meta">
                <!-- icono pin inline -->
                <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
                  <path
                    d="M12 21s7-5.686 7-11a7 7 0 1 0-14 0c0 5.314 7 11 7 11Z"
                    stroke="currentColor"
                    stroke-width="2"
                    stroke-linejoin="round"
                  />
                  <circle cx="12" cy="10" r="2.5" stroke="currentColor" stroke-width="2" />
                </svg>
                <span>${this.location}</span>
              </span>`
            : null}
          ${this.renderAvatars()}
        </div>
      </article>
    `;
  }
}

define('ok-event-card', OkEventCard);

declare global {
  interface HTMLElementTagNameMap {
    'ok-event-card': OkEventCard;
  }
}
