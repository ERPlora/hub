import { LitElement, html, css } from 'lit';
import { property, state } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// Recurso (fila del timeline): un empleado, sala, máquina, etc.
// Lo aporta el consumidor vía la prop `.resources`.
export interface OkSchedulerResource {
  /** Identificador único del recurso (clave para asociar eventos). */
  id: string;
  /** Texto visible del recurso (columna izquierda sticky). */
  label: string;
  /** URL opcional de avatar/imagen mostrada antes del label. */
  avatar?: string;
}

// Evento/turno posicionado sobre la franja horaria de un recurso.
// Lo aporta el consumidor vía la prop `.events`.
export interface OkSchedulerEvent {
  /** Identificador único del evento. */
  id: string;
  /** Id del recurso (fila) al que pertenece el evento. */
  resourceId: string;
  /** Hora de inicio: ISO (`...THH:MM`) o `HH:MM`. Se usa solo la hora local. */
  start: string;
  /** Hora de fin: ISO o `HH:MM`. */
  end: string;
  /** Texto visible dentro del bloque. */
  title: string;
  /** Color del bloque; cadena CSS (hex, var, etc.). Por defecto, el primario. */
  color?: string;
}

// Textos humanos del scheduler (i18n). Default INGLÉS; el consumidor sobreescribe claves
// sueltas vía la prop `labels`.
export interface OkSchedulerLabels {
  /** aria-label del botón "día anterior". */
  prevDay: string;
  /** aria-label del botón "día siguiente". */
  nextDay: string;
  /** Texto cuando no hay recursos que mostrar. */
  empty: string;
}

const DEFAULT_LABELS: OkSchedulerLabels = {
  prevDay: 'Previous day',
  nextDay: 'Next day',
  empty: 'No resources to display.',
};

// ok-scheduler — agenda de recursos/turnos en TIMELINE, algo que Ionic NO ofrece. Por DATOS
// (`resources` + `events`). AUTOCONTENIDO: CSS propio en el shadow, sin librerías de fechas (solo
// `Date` nativo → CSP-safe). Usa `ion-icon`/`ion-button` internos (los registra el host).
//   • prop `.resources` → Array<OkSchedulerResource> (filas)
//   • prop `.events`    → Array<OkSchedulerEvent> (bloques posicionados por hora)
//   • prop `date`       → día mostrado (`YYYY-MM-DD`)
//   • prop `start-hour` → primera hora visible (def 8)
//   • prop `end-hour`   → última hora visible (def 20)
//   • prop `slot`       → minutos por celda/columna (def 60)
// Layout: cabecera con la franja horaria + navegación de día (‹ fecha ›); una FILA por recurso con
// su label sticky a la izquierda; los eventos se posicionan por hora (left/width). Scroll horizontal
// si la franja es ancha; la columna de recurso queda fija (sticky).
// Eventos (bubbles + composed):
//   • `ok-event-click`  detail { id, event }
//   • `ok-slot-click`   detail { resourceId, time }   (time = `HH:MM`)
//   • `ok-nav`          detail { date }                (`YYYY-MM-DD`, al cambiar de día)
export class OkScheduler extends LitElement {
  static styles = css`
    :host {
      /* Vars overridable (estilo Ionic), default = cadena --ok-* → --ion-* → hex */
      --color: var(--ok-text, var(--ion-text-color, #1c1b17));
      --color-muted: var(--ok-text-muted, rgba(var(--ion-text-color-rgb, 28, 27, 23), 0.55));
      --background: var(--ok-surface, var(--ion-background-color, #ffffff));
      --primary-color: var(--ok-primary, var(--ion-color-primary, #3880ff));
      --primary-contrast: var(--ok-primary-contrast, var(--ion-color-primary-contrast, #ffffff));
      --hover-bg: var(--ok-hover, rgba(var(--ion-text-color-rgb, 28, 27, 23), 0.06));
      --border-color: var(--ok-border-soft, rgba(var(--ion-text-color-rgb, 28, 27, 23), 0.12));
      --border-radius: var(--ok-radius, 8px);
      --resource-width: var(--ok-scheduler-resource-width, 11rem);
      --hour-width: var(--ok-scheduler-hour-width, 6rem);
      --row-height: var(--ok-scheduler-row-height, 3.5rem);
      --font: var(--ok-font, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif);

      /* Por defecto ocupa el ancho del contenedor y es responsive. */
      display: block;
      width: 100%;
      color: var(--color);
      font-family: var(--font);
      font-size: 0.95rem;
      box-sizing: border-box;
    }
    * {
      box-sizing: border-box;
    }

    /* ── Cabecera de navegación de día ──────────────────────────── */
    .toolbar {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 0.25rem;
      margin-bottom: 0.6rem;
    }
    .toolbar .title {
      min-width: 12rem;
      text-align: center;
      font-weight: 600;
      font-size: 1.05rem;
      text-transform: capitalize;
    }

    /* ── Contenedor con scroll horizontal ───────────────────────── */
    .scroll {
      width: 100%;
      overflow-x: auto;
      overflow-y: hidden;
      border: 1px solid var(--border-color);
      border-radius: var(--border-radius);
      -webkit-overflow-scrolling: touch;
    }
    /* El grid interior tiene ancho intrínseco = columna recurso + franja horaria. */
    .grid {
      display: inline-block;
      min-width: 100%;
    }

    /* ── Cabecera horaria ───────────────────────────────────────── */
    .head-row {
      display: flex;
      position: sticky;
      top: 0;
      z-index: 3;
    }
    .corner {
      flex: 0 0 var(--resource-width);
      width: var(--resource-width);
      position: sticky;
      left: 0;
      z-index: 4;
      background: var(--background);
      border-right: 1px solid var(--border-color);
      border-bottom: 1px solid var(--border-color);
    }
    .timeline {
      display: flex;
      flex: 1 1 auto;
    }
    .hour {
      flex: 0 0 var(--hour-width);
      width: var(--hour-width);
      padding: 0.4rem 0.5rem;
      font-size: 0.78rem;
      font-weight: 600;
      color: var(--color-muted);
      text-align: left;
      background: var(--background);
      border-bottom: 1px solid var(--border-color);
      border-right: 1px solid var(--border-color);
      font-variant-numeric: tabular-nums;
    }
    .hour:last-child {
      border-right: 0;
    }

    /* ── Filas de recurso ───────────────────────────────────────── */
    .row {
      display: flex;
      border-top: 1px solid var(--border-color);
    }
    .row:first-of-type {
      border-top: 0;
    }
    .resource {
      flex: 0 0 var(--resource-width);
      width: var(--resource-width);
      min-height: var(--row-height);
      position: sticky;
      left: 0;
      z-index: 2;
      display: flex;
      align-items: center;
      gap: 0.5rem;
      padding: 0.4rem 0.6rem;
      background: var(--background);
      border-right: 1px solid var(--border-color);
    }
    .avatar {
      flex: 0 0 auto;
      width: 2rem;
      height: 2rem;
      border-radius: 999px;
      object-fit: cover;
      background: var(--hover-bg);
    }
    .avatar-fallback {
      flex: 0 0 auto;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 2rem;
      height: 2rem;
      border-radius: 999px;
      background: var(--hover-bg);
      color: var(--color-muted);
      font-size: 0.85rem;
      font-weight: 600;
      text-transform: uppercase;
    }
    .resource-label {
      flex: 1 1 auto;
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      font-weight: 500;
    }

    /* ── Pista de eventos (lane) de un recurso ──────────────────── */
    .lane {
      position: relative;
      flex: 1 1 auto;
      min-height: var(--row-height);
      background: var(--background);
    }
    /* Celdas-slot clicables de fondo (para crear turnos). */
    .slot {
      position: absolute;
      top: 0;
      bottom: 0;
      border-right: 1px solid var(--border-color);
      cursor: pointer;
      transition: background-color var(--ok-transition, 150ms ease),
        color var(--ok-transition, 150ms ease), border-color var(--ok-transition, 150ms ease),
        box-shadow var(--ok-transition, 150ms ease), transform 120ms ease;
    }
    @media (hover: hover) {
      .slot:hover {
        background: var(--hover-bg);
      }
    }
    .slot:active {
      transform: scale(var(--ok-press-scale, 0.97));
    }
    .slot:last-child {
      border-right: 0;
    }

    /* ── Bloque de evento ───────────────────────────────────────── */
    .event {
      position: absolute;
      top: 0.25rem;
      bottom: 0.25rem;
      display: flex;
      flex-direction: column;
      justify-content: center;
      padding: 0.2rem 0.45rem;
      border-radius: 6px;
      color: var(--primary-contrast);
      cursor: pointer;
      overflow: hidden;
      z-index: 1;
      box-shadow: 0 1px 2px rgba(0, 0, 0, 0.18);
      transition: background-color var(--ok-transition, 150ms ease),
        color var(--ok-transition, 150ms ease), border-color var(--ok-transition, 150ms ease),
        box-shadow var(--ok-transition, 150ms ease), transform 120ms ease, filter 0.12s ease;
    }
    @media (hover: hover) {
      .event:hover {
        filter: brightness(1.05);
        box-shadow: 0 2px 6px rgba(0, 0, 0, 0.22);
      }
    }
    .event:active {
      transform: scale(var(--ok-press-scale, 0.97));
    }
    .event-title {
      font-size: 0.78rem;
      font-weight: 600;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .event-time {
      font-size: 0.68rem;
      opacity: 0.9;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      font-variant-numeric: tabular-nums;
    }

    /* ── Estado vacío ───────────────────────────────────────────── */
    .empty {
      padding: 1.5rem;
      text-align: center;
      color: var(--color-muted);
    }

    @media (prefers-reduced-motion: reduce) {
      .slot:active,
      .event:active {
        transform: none;
      }
    }

    /* ── Responsive (móvil): franja más estrecha, recurso visible ── */
    @media (max-width: 540px) {
      :host {
        --resource-width: 7rem;
        --hour-width: 3.5rem;
      }
      .hour {
        font-size: 0.7rem;
        padding: 0.35rem 0.3rem;
      }
      .avatar,
      .avatar-fallback {
        width: 1.6rem;
        height: 1.6rem;
        font-size: 0.7rem;
      }
      .event-time {
        display: none;
      }
    }
  `;

  /** Recursos (filas); el consumidor los pasa por propiedad. */
  @property({ attribute: false }) resources: OkSchedulerResource[] = [];
  /** Eventos/turnos; el consumidor los pasa por propiedad. */
  @property({ attribute: false }) events: OkSchedulerEvent[] = [];
  /** Día mostrado (`YYYY-MM-DD`). Vacío = hoy. */
  @property() date = '';
  /** Primera hora visible de la franja (0–23). */
  @property({ type: Number, attribute: 'start-hour' }) startHour = 8;
  /** Última hora visible de la franja (1–24). */
  @property({ type: Number, attribute: 'end-hour' }) endHour = 20;
  /** Minutos por celda/columna. (attr `slot-minutes`: `slot` colisiona con HTMLElement.slot.) */
  @property({ type: Number, attribute: 'slot-minutes' }) slotMin = 60;
  /** Locale BCP-47 para formatear la fecha del día (Intl). Default 'en-US'. */
  @property() locale = 'en-US';
  /** Textos humanos sobreescribibles (i18n). Default INGLÉS. */
  @property({ attribute: false }) labels: Partial<OkSchedulerLabels> = {};

  /** Textos efectivos: defaults INGLÉS mezclados con los del consumidor. */
  private get t(): OkSchedulerLabels {
    return { ...DEFAULT_LABELS, ...this.labels };
  }

  // Cursor de día (estado interno de navegación). Se siembra desde `date` una sola vez.
  @state() private cursor = new Date();
  private seeded = false;

  // ── Helpers de fecha ──────────────────────────────────────────

  // Convierte una `Date` a clave local `YYYY-MM-DD`.
  private dayKey(d: Date): string {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
  }

  // Parsea `YYYY-MM-DD` (parte de fecha) a `Date` local; fallback defensivo a hoy.
  private parseDay(s: string): Date {
    const [y, m, d] = s.slice(0, 10).split('-').map(Number);
    if (y && m && d) return new Date(y, m - 1, d);
    return new Date();
  }

  // Extrae los minutos desde medianoche de una hora `HH:MM` o ISO (`...THH:MM`).
  private minutesOf(time: string): number {
    // Si es ISO con 'T', tomamos la parte de hora; si es `HH:MM`, la usamos tal cual.
    const t = time.includes('T') ? time.split('T')[1] : time;
    const [h, m] = (t || '').split(':').map(Number);
    if (Number.isFinite(h)) return h * 60 + (Number.isFinite(m) ? m : 0);
    return 0;
  }

  // Formatea minutos-desde-medianoche a `HH:MM`.
  private fmtTime(mins: number): string {
    const h = Math.floor(mins / 60);
    const m = mins % 60;
    return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
  }

  // ── Geometría de la franja ────────────────────────────────────

  // Rango total de la franja en minutos (defensivo: end > start).
  private get rangeMinutes(): number {
    const span = (this.endHour - this.startHour) * 60;
    return span > 0 ? span : 60;
  }

  // Número de celdas-slot de fondo según `slot`.
  private get slotCount(): number {
    const step = this.slotMin > 0 ? this.slotMin : 60;
    return Math.max(1, Math.ceil(this.rangeMinutes / step));
  }

  // ── Navegación / eventos ──────────────────────────────────────

  // Cambia el día visible (delta en días) y emite `ok-nav`.
  private navDay(delta: number): void {
    const next = new Date(
      this.cursor.getFullYear(),
      this.cursor.getMonth(),
      this.cursor.getDate() + delta,
    );
    this.cursor = next;
    this.dispatchEvent(
      new CustomEvent('ok-nav', {
        detail: { date: this.dayKey(next) },
        bubbles: true,
        composed: true,
      }),
    );
  }

  // Emite el click sobre un evento (sin propagar al slot de fondo).
  private clickEvent(ev: OkSchedulerEvent, e: Event): void {
    e.stopPropagation();
    this.dispatchEvent(
      new CustomEvent('ok-event-click', {
        detail: { id: ev.id, event: ev },
        bubbles: true,
        composed: true,
      }),
    );
  }

  // Emite el click sobre una celda-slot vacía de un recurso.
  private clickSlot(resourceId: string, mins: number): void {
    this.dispatchEvent(
      new CustomEvent('ok-slot-click', {
        detail: { resourceId, time: this.fmtTime(mins) },
        bubbles: true,
        composed: true,
      }),
    );
  }

  // ── Etiquetas ─────────────────────────────────────────────────

  // Etiqueta del día del cursor (capitalizada vía CSS).
  private dayLabel(): string {
    return this.cursor.toLocaleDateString(this.locale, {
      weekday: 'long',
      day: 'numeric',
      month: 'long',
      year: 'numeric',
    });
  }

  // Iniciales para el avatar de respaldo (sin imagen).
  private initials(label: string): string {
    const parts = label.trim().split(/\s+/).filter(Boolean);
    if (parts.length === 0) return '?';
    if (parts.length === 1) return parts[0].slice(0, 2);
    return parts[0][0] + parts[parts.length - 1][0];
  }

  // ── Render parcial ────────────────────────────────────────────

  // Cabecera horaria: una columna por hora del rango.
  private renderTimelineHead(): unknown {
    const hours: number[] = [];
    for (let h = this.startHour; h < this.endHour; h++) hours.push(h);
    return html`<div class="timeline">
      ${hours.map(
        (h) => html`<div class="hour">${String(h).padStart(2, '0')}:00</div>`,
      )}
    </div>`;
  }

  // Lane (pista) de un recurso: celdas-slot de fondo + bloques de evento posicionados.
  private renderLane(resource: OkSchedulerResource): unknown {
    const total = this.rangeMinutes;
    const startMin = this.startHour * 60;
    const step = this.slotMin > 0 ? this.slotMin : 60;
    const count = this.slotCount;

    // Celdas-slot de fondo (clicables para crear turnos).
    const slots = [];
    for (let i = 0; i < count; i++) {
      const slotStart = startMin + i * step;
      const left = ((slotStart - startMin) / total) * 100;
      const width = (step / total) * 100;
      slots.push(
        html`<div
          class="slot"
          style=${`left:${left}%;width:${width}%`}
          @click=${() => this.clickSlot(resource.id, slotStart)}
        ></div>`,
      );
    }

    // Bloques de evento del recurso, recortados al rango visible.
    const blocks = this.events
      .filter((ev) => ev.resourceId === resource.id)
      .map((ev) => {
        const s = Math.max(this.minutesOf(ev.start), startMin);
        const e = Math.min(this.minutesOf(ev.end), startMin + total);
        if (e <= s) return ''; // fuera de rango o duración nula
        const left = ((s - startMin) / total) * 100;
        const width = ((e - s) / total) * 100;
        return html`<div
          class="event"
          style=${`left:${left}%;width:${width}%;background:${ev.color || 'var(--primary-color)'}`}
          title=${ev.title}
          @click=${(domEv: Event) => this.clickEvent(ev, domEv)}
        >
          <span class="event-title">${ev.title}</span>
          <span class="event-time"
            >${this.fmtTime(this.minutesOf(ev.start))} – ${this.fmtTime(this.minutesOf(ev.end))}</span
          >
        </div>`;
      });

    return html`<div class="lane">${slots}${blocks}</div>`;
  }

  // Fila completa de un recurso: label sticky + lane.
  private renderRow(resource: OkSchedulerResource): unknown {
    return html`<div class="row">
      <div class="resource">
        ${resource.avatar
          ? html`<img class="avatar" src=${resource.avatar} alt="" loading="lazy" />`
          : html`<span class="avatar-fallback">${this.initials(resource.label)}</span>`}
        <span class="resource-label">${resource.label}</span>
      </div>
      ${this.renderLane(resource)}
    </div>`;
  }

  render(): unknown {
    // Siembra perezosa del cursor a partir de `date` (una sola vez).
    if (!this.seeded) {
      if (this.date) this.cursor = this.parseDay(this.date);
      this.seeded = true;
    }

    // Ancho intrínseco de la franja = nº de horas × ancho de hora (para el scroll horizontal).
    const hourCount = Math.max(1, this.endHour - this.startHour);
    const timelineWidth = `calc(${hourCount} * var(--hour-width))`;
    const gridStyle = `width:calc(var(--resource-width) + ${timelineWidth})`;

    return html`<div class="toolbar">
        <ion-button
          fill="clear"
          size="small"
          aria-label=${this.t.prevDay}
          @click=${() => this.navDay(-1)}
        >
          <ion-icon slot="icon-only" name="chevron-back-outline"></ion-icon>
        </ion-button>
        <span class="title">${this.dayLabel()}</span>
        <ion-button
          fill="clear"
          size="small"
          aria-label=${this.t.nextDay}
          @click=${() => this.navDay(1)}
        >
          <ion-icon slot="icon-only" name="chevron-forward-outline"></ion-icon>
        </ion-button>
      </div>
      <div class="scroll">
        <div class="grid" style=${gridStyle}>
          <div class="head-row">
            <div class="corner"></div>
            ${this.renderTimelineHead()}
          </div>
          ${this.resources.length
            ? this.resources.map((r) => this.renderRow(r))
            : html`<div class="empty">${this.t.empty}</div>`}
        </div>
      </div>`;
  }
}

define('ok-scheduler', OkScheduler);

declare global {
  interface HTMLElementTagNameMap {
    'ok-scheduler': OkScheduler;
  }
}
