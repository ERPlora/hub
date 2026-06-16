import { LitElement, html, css } from 'lit';
import { property, state } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// Evento de calendario. Lo aporta el consumidor vía la prop `.events`.
export interface OkCalendarEvent {
  /** Identificador único del evento. */
  id: string;
  /** Fecha del evento en `YYYY-MM-DD` o ISO (se normaliza al día local). */
  date: string;
  /** Texto visible del evento (chip / fila de agenda). */
  title: string;
  /** Color del chip; cadena CSS (hex, var, etc.). Por defecto, el primario. */
  color?: string;
}

// Vista del calendario.
export type OkCalendarView = 'month' | 'agenda';

// Textos humanos del calendario (i18n). Default INGLÉS; el consumidor puede sobreescribir
// claves sueltas vía la prop `labels`. Variables con token `{n}` (p.ej. `more`).
export interface OkCalendarLabels {
  /** Etiqueta del botón de vista Mes. */
  month: string;
  /** Etiqueta del botón de vista Agenda. */
  agenda: string;
  /** Indicador de eventos extra por día; `{n}` = cantidad. */
  more: string;
  /** Texto cuando la agenda no tiene próximos eventos. */
  agendaEmpty: string;
  /** aria-label del botón "mes anterior". */
  prevMonth: string;
  /** aria-label del botón "mes siguiente". */
  nextMonth: string;
}

const DEFAULT_LABELS: OkCalendarLabels = {
  month: 'Month',
  agenda: 'Agenda',
  more: '+{n} more',
  agendaEmpty: 'No upcoming events.',
  prevMonth: 'Previous month',
  nextMonth: 'Next month',
};

// Nombres de los días de la semana (Lun–Dom) según el locale, vía Intl.
const WEEKDAY_REF = new Date(2021, 1, 1); // 2021-02-01 es lunes

// ok-calendar — calendario por DATOS (`events`), algo que Ionic NO ofrece: `ion-datetime` es solo
// un picker de fechas, no una rejilla con eventos. AUTOCONTENIDO: CSS propio en el shadow, sin
// librerías de fechas (solo `Date` nativo → CSP-safe). Usa `ion-icon`/`ion-button` internos (los
// registra el host).
//   • prop `.events` → Array<OkCalendarEvent>
//   • prop `value`   → día seleccionado (`YYYY-MM-DD`)
//   • prop `view`    → 'month' | 'agenda' (def 'month')
// Vista MES: cabecera ‹ mes/año › + toggle Mes/Agenda; rejilla 7 columnas (Lun–Dom); hoy resaltado;
//   cada día muestra hasta N eventos como chips y "+X más".
// Vista AGENDA: próximos eventos agrupados por día (útil en móvil).
// Eventos (bubbles + composed):
//   • `ok-date-select`  detail { date }
//   • `ok-event-click`  detail { id, event }
//   • `ok-view-change`  detail { view }
//   • `ok-nav`          detail { year, month }   (month: 1–12, al cambiar de mes)
export class OkCalendar extends LitElement {
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
      --today-bg: var(--ok-today-bg, rgba(var(--ion-color-primary-rgb, 56, 128, 255), 0.1));
      --border-radius: var(--ok-radius, 8px);
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

    /* ── Cabecera ───────────────────────────────────────────────── */
    .header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 0.5rem;
      margin-bottom: 0.75rem;
      flex-wrap: wrap;
    }
    .nav {
      display: flex;
      align-items: center;
      gap: 0.25rem;
    }
    .title {
      min-width: 9rem;
      text-align: center;
      font-weight: 600;
      font-size: 1.05rem;
      text-transform: capitalize;
    }
    .toggle {
      display: inline-flex;
      border: 1px solid var(--border-color);
      border-radius: var(--border-radius);
      overflow: hidden;
    }
    .toggle button {
      border: 0;
      background: none;
      color: var(--color-muted);
      font: inherit;
      font-size: 0.85rem;
      padding: 0.35rem 0.75rem;
      cursor: pointer;
      transition: background-color var(--ok-transition, 150ms ease),
        color var(--ok-transition, 150ms ease), border-color var(--ok-transition, 150ms ease),
        box-shadow var(--ok-transition, 150ms ease), transform 120ms ease;
    }
    @media (hover: hover) {
      .toggle button:not(.active):hover {
        background: var(--hover-bg);
        color: var(--color);
      }
    }
    .toggle button:active {
      transform: scale(var(--ok-press-scale, 0.97));
    }
    .toggle button.active {
      background: var(--primary-color);
      color: var(--primary-contrast);
    }

    /* ── Vista MES ──────────────────────────────────────────────── */
    .grid {
      display: grid;
      grid-template-columns: repeat(7, minmax(0, 1fr));
      gap: 1px;
      background: var(--border-color);
      border: 1px solid var(--border-color);
      border-radius: var(--border-radius);
      overflow: hidden;
    }
    .weekday {
      background: var(--background);
      padding: 0.4rem 0.25rem;
      text-align: center;
      font-size: 0.75rem;
      font-weight: 600;
      color: var(--color-muted);
      text-transform: uppercase;
    }
    .day {
      background: var(--background);
      min-height: 5.5rem;
      padding: 0.3rem;
      display: flex;
      flex-direction: column;
      gap: 0.2rem;
      cursor: pointer;
      transition: background-color var(--ok-transition, 150ms ease),
        color var(--ok-transition, 150ms ease), border-color var(--ok-transition, 150ms ease),
        box-shadow var(--ok-transition, 150ms ease), transform 120ms ease;
      overflow: hidden;
    }
    @media (hover: hover) {
      .day:hover {
        background: var(--hover-bg);
      }
    }
    .day:active {
      transform: scale(var(--ok-press-scale, 0.97));
    }
    .day.other-month {
      opacity: 0.4;
    }
    .day.today .daynum {
      background: var(--primary-color);
      color: var(--primary-contrast);
    }
    .day.selected {
      box-shadow: inset 0 0 0 2px var(--primary-color);
    }
    .daynum {
      align-self: flex-end;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 1.5rem;
      height: 1.5rem;
      padding: 0 0.35rem;
      border-radius: 999px;
      font-size: 0.8rem;
      font-variant-numeric: tabular-nums;
    }
    .chips {
      display: flex;
      flex-direction: column;
      gap: 0.15rem;
      min-width: 0;
    }
    .chip {
      display: flex;
      align-items: center;
      gap: 0.3rem;
      padding: 0.1rem 0.3rem;
      border-radius: 4px;
      font-size: 0.72rem;
      line-height: 1.3;
      color: var(--primary-contrast);
      cursor: pointer;
      overflow: hidden;
      white-space: nowrap;
      text-overflow: ellipsis;
      transition: background-color var(--ok-transition, 150ms ease),
        color var(--ok-transition, 150ms ease), border-color var(--ok-transition, 150ms ease),
        box-shadow var(--ok-transition, 150ms ease), transform 120ms ease;
    }
    @media (hover: hover) {
      .chip:hover {
        filter: brightness(1.05);
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.18);
      }
    }
    .chip:active {
      transform: scale(var(--ok-press-scale, 0.97));
    }
    .chip .chip-title {
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .more {
      font-size: 0.7rem;
      color: var(--color-muted);
      padding: 0 0.3rem;
      cursor: pointer;
    }

    /* ── Vista AGENDA ───────────────────────────────────────────── */
    .agenda {
      display: flex;
      flex-direction: column;
      gap: 1rem;
    }
    .agenda-empty {
      color: var(--color-muted);
      padding: 1rem;
      text-align: center;
    }
    .agenda-group {
      display: flex;
      flex-direction: column;
      gap: 0.35rem;
    }
    .agenda-date {
      font-size: 0.8rem;
      font-weight: 600;
      color: var(--color-muted);
      text-transform: capitalize;
      border-bottom: 1px solid var(--border-color);
      padding-bottom: 0.25rem;
    }
    .agenda-item {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      padding: 0.4rem 0.3rem;
      border-radius: var(--border-radius);
      cursor: pointer;
      transition: background-color var(--ok-transition, 150ms ease),
        color var(--ok-transition, 150ms ease), border-color var(--ok-transition, 150ms ease),
        box-shadow var(--ok-transition, 150ms ease), transform 120ms ease;
    }
    @media (hover: hover) {
      .agenda-item:hover {
        background: var(--hover-bg);
      }
    }
    .agenda-item:active {
      transform: scale(var(--ok-press-scale, 0.97));
    }
    .dot {
      flex: 0 0 auto;
      width: 0.6rem;
      height: 0.6rem;
      border-radius: 999px;
    }
    .agenda-title {
      flex: 1 1 auto;
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    @media (prefers-reduced-motion: reduce) {
      .toggle button:active,
      .day:active,
      .chip:active,
      .agenda-item:active {
        transform: none;
      }
    }

    /* ── Responsive (móvil) ─────────────────────────────────────── */
    @media (max-width: 540px) {
      .day {
        min-height: 3.5rem;
        padding: 0.2rem;
      }
      .weekday {
        font-size: 0.65rem;
        padding: 0.3rem 0.1rem;
      }
      .chip-title {
        display: none;
      }
      .chip {
        height: 0.5rem;
        padding: 0;
      }
    }
  `;

  /** Eventos a mostrar; el consumidor los pasa por propiedad. */
  @property({ attribute: false }) events: OkCalendarEvent[] = [];
  /** Día seleccionado (`YYYY-MM-DD`). */
  @property() value = '';
  /** Vista actual: 'month' | 'agenda'. */
  @property() view: OkCalendarView = 'month';
  /** Máximo de chips de evento por celda antes de mostrar "+X más". */
  @property({ type: Number, attribute: 'max-per-day' }) maxPerDay = 3;
  /** Locale BCP-47 para formatear meses/días/fechas (Intl). Default 'en-US'. */
  @property() locale = 'en-US';
  /** Textos humanos sobreescribibles (i18n). Default INGLÉS. */
  @property({ attribute: false }) labels: Partial<OkCalendarLabels> = {};

  /** Textos efectivos: defaults INGLÉS mezclados con los del consumidor. */
  private get t(): OkCalendarLabels {
    return { ...DEFAULT_LABELS, ...this.labels };
  }

  // Mes/año visibles en la vista de mes (estado interno de navegación).
  @state() private cursor = new Date();
  // Marca para sembrar el cursor desde `value` una sola vez.
  private seeded = false;

  // Nombres cortos de los días (Lun–Dom) según el locale actual.
  private weekdays(): string[] {
    const fmt = new Intl.DateTimeFormat(this.locale, { weekday: 'short' });
    return Array.from({ length: 7 }, (_, i) =>
      fmt.format(new Date(WEEKDAY_REF.getFullYear(), WEEKDAY_REF.getMonth(), 1 + i)),
    );
  }

  // Normaliza una fecha (`YYYY-MM-DD` o ISO) a clave local `YYYY-MM-DD`.
  private dayKey(d: Date): string {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
  }

  // Parsea una cadena de fecha del consumidor a `Date` local (ignora la hora si es ISO).
  private parseDate(s: string): Date {
    // Tomamos solo la parte de fecha para evitar saltos de día por zona horaria.
    const datePart = s.slice(0, 10);
    const [y, m, d] = datePart.split('-').map(Number);
    if (y && m && d) return new Date(y, m - 1, d);
    // Fallback defensivo: deja que Date intente parsear el ISO completo.
    const parsed = new Date(s);
    return isNaN(parsed.getTime()) ? new Date() : parsed;
  }

  // Índice eventos por día (`YYYY-MM-DD` → eventos), ordenados por título para estabilidad.
  private indexEvents(): Map<string, OkCalendarEvent[]> {
    const map = new Map<string, OkCalendarEvent[]>();
    for (const ev of this.events) {
      const key = this.dayKey(this.parseDate(ev.date));
      const arr = map.get(key);
      if (arr) arr.push(ev);
      else map.set(key, [ev]);
    }
    return map;
  }

  // Cambia el mes visible (delta en meses) y emite `ok-nav`.
  private navMonth(delta: number): void {
    const next = new Date(this.cursor.getFullYear(), this.cursor.getMonth() + delta, 1);
    this.cursor = next;
    this.dispatchEvent(
      new CustomEvent('ok-nav', {
        detail: { year: next.getFullYear(), month: next.getMonth() + 1 },
        bubbles: true,
        composed: true,
      }),
    );
  }

  // Cambia de vista y emite `ok-view-change`.
  private setView(view: OkCalendarView): void {
    if (view === this.view) return;
    this.view = view;
    this.dispatchEvent(
      new CustomEvent('ok-view-change', {
        detail: { view },
        bubbles: true,
        composed: true,
      }),
    );
  }

  // Selecciona un día y emite `ok-date-select`.
  private selectDay(key: string): void {
    this.value = key;
    this.dispatchEvent(
      new CustomEvent('ok-date-select', {
        detail: { date: key },
        bubbles: true,
        composed: true,
      }),
    );
  }

  // Emite el click sobre un evento (sin propagar al día contenedor).
  private clickEvent(ev: OkCalendarEvent, e: Event): void {
    e.stopPropagation();
    this.dispatchEvent(
      new CustomEvent('ok-event-click', {
        detail: { id: ev.id, event: ev },
        bubbles: true,
        composed: true,
      }),
    );
  }

  // Etiqueta de mes/año del cursor (capitalizada vía CSS).
  private monthLabel(): string {
    return this.cursor.toLocaleDateString(this.locale, { month: 'long', year: 'numeric' });
  }

  // Construye la matriz de días visibles (semanas que empiezan en lunes).
  private buildDays(): Date[] {
    const year = this.cursor.getFullYear();
    const month = this.cursor.getMonth();
    const first = new Date(year, month, 1);
    // getDay(): 0=Dom..6=Sáb → desplazamos para que lunes sea el primer día.
    const offset = (first.getDay() + 6) % 7;
    const start = new Date(year, month, 1 - offset);
    const days: Date[] = [];
    // 6 semanas × 7 días = rejilla estable de 42 celdas.
    for (let i = 0; i < 42; i++) {
      days.push(new Date(start.getFullYear(), start.getMonth(), start.getDate() + i));
    }
    return days;
  }

  // Render de la vista MES.
  private renderMonth(byDay: Map<string, OkCalendarEvent[]>): unknown {
    const todayKey = this.dayKey(new Date());
    const month = this.cursor.getMonth();
    const days = this.buildDays();

    return html`<div class="grid">
      ${this.weekdays().map((w) => html`<div class="weekday">${w}</div>`)}
      ${days.map((d) => {
        const key = this.dayKey(d);
        const dayEvents = byDay.get(key) ?? [];
        const visible = dayEvents.slice(0, this.maxPerDay);
        const extra = dayEvents.length - visible.length;
        const classes = [
          'day',
          d.getMonth() !== month ? 'other-month' : '',
          key === todayKey ? 'today' : '',
          key === this.value ? 'selected' : '',
        ]
          .filter(Boolean)
          .join(' ');

        return html`<div class=${classes} @click=${() => this.selectDay(key)}>
          <span class="daynum">${d.getDate()}</span>
          <div class="chips">
            ${visible.map(
              (ev) => html`<span
                class="chip"
                style=${`background:${ev.color || 'var(--primary-color)'}`}
                title=${ev.title}
                @click=${(e: Event) => this.clickEvent(ev, e)}
              >
                <span class="chip-title">${ev.title}</span>
              </span>`,
            )}
            ${extra > 0
              ? html`<span class="more">${this.t.more.replace('{n}', String(extra))}</span>`
              : ''}
          </div>
        </div>`;
      })}
    </div>`;
  }

  // Render de la vista AGENDA: próximos eventos (hoy en adelante) agrupados por día.
  private renderAgenda(byDay: Map<string, OkCalendarEvent[]>): unknown {
    const todayKey = this.dayKey(new Date());
    // Solo días con eventos, de hoy en adelante, ordenados ascendentemente.
    const keys = [...byDay.keys()].filter((k) => k >= todayKey).sort();

    if (keys.length === 0) {
      return html`<div class="agenda-empty">${this.t.agendaEmpty}</div>`;
    }

    return html`<div class="agenda">
      ${keys.map((key) => {
        const d = this.parseDate(key);
        const label = d.toLocaleDateString(this.locale, {
          weekday: 'long',
          day: 'numeric',
          month: 'long',
        });
        return html`<div class="agenda-group">
          <div class="agenda-date">${label}</div>
          ${byDay.get(key)!.map(
            (ev) => html`<div class="agenda-item" @click=${(e: Event) => this.clickEvent(ev, e)}>
              <span class="dot" style=${`background:${ev.color || 'var(--primary-color)'}`}></span>
              <span class="agenda-title">${ev.title}</span>
              <ion-icon name="chevron-forward-outline"></ion-icon>
            </div>`,
          )}
        </div>`;
      })}
    </div>`;
  }

  render(): unknown {
    // Siembra perezosa del cursor a partir de `value` (una sola vez).
    if (!this.seeded) {
      if (this.value) this.cursor = this.parseDate(this.value);
      this.seeded = true;
    }

    const byDay = this.indexEvents();

    return html`<div class="header">
        <div class="nav">
          <ion-button
            fill="clear"
            size="small"
            aria-label=${this.t.prevMonth}
            @click=${() => this.navMonth(-1)}
          >
            <ion-icon slot="icon-only" name="chevron-back-outline"></ion-icon>
          </ion-button>
          <span class="title">${this.monthLabel()}</span>
          <ion-button
            fill="clear"
            size="small"
            aria-label=${this.t.nextMonth}
            @click=${() => this.navMonth(1)}
          >
            <ion-icon slot="icon-only" name="chevron-forward-outline"></ion-icon>
          </ion-button>
        </div>
        <div class="toggle" role="tablist">
          <button
            type="button"
            class=${this.view === 'month' ? 'active' : ''}
            @click=${() => this.setView('month')}
          >
            ${this.t.month}
          </button>
          <button
            type="button"
            class=${this.view === 'agenda' ? 'active' : ''}
            @click=${() => this.setView('agenda')}
          >
            ${this.t.agenda}
          </button>
        </div>
      </div>
      ${this.view === 'agenda' ? this.renderAgenda(byDay) : this.renderMonth(byDay)}`;
  }
}

define('ok-calendar', OkCalendar);

declare global {
  interface HTMLElementTagNameMap {
    'ok-calendar': OkCalendar;
  }
}
