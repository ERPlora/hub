import { LitElement, html, css, nothing } from 'lit';
import { property, state } from 'lit/decorators.js';
import { define } from '../../base/define.js';
import { computeAnchor } from '../../base/anchor.js';

// Modo del picker: una sola fecha o un rango (start..end).
export type OkDatePickerMode = 'single' | 'range';

// Valor de rango (fechas ISO `YYYY-MM-DD`; null mientras se elige).
export interface OkDateRange {
  start: string | null;
  end: string | null;
}

// Valor público del componente: ISO string (single) o rango (range).
export type OkDatePickerValue = string | OkDateRange | null;

// Atajo rápido (chip de preset). El consumidor puede sobreescribir la lista vía la prop `presets`.
export interface OkDatePreset {
  /** Clave estable del preset. */
  id: string;
  /** Texto visible en el chip. */
  label: string;
}

// Textos traducibles (default en español, idioma del proyecto).
export interface OkDatePickerLabels {
  /** aria-label del botón anterior. */
  prev: string;
  /** aria-label del botón siguiente. */
  next: string;
  /** aria-label del botón disparador cuando no hay valor. */
  open: string;
}

const DEFAULT_LABELS: OkDatePickerLabels = {
  prev: 'Mes anterior',
  next: 'Mes siguiente',
  open: 'Elegir fecha',
};

// Presets por defecto (los del spec). El id se usa para resolver el rango/fecha en runtime.
const DEFAULT_PRESETS: OkDatePreset[] = [
  { id: 'today', label: 'Hoy' },
  { id: '7d', label: '7d' },
  { id: 'week', label: 'Esta semana' },
  { id: 'month', label: 'Mes' },
  { id: 'quarter', label: 'Trimestre' },
  { id: 'ytd', label: 'YTD' },
];

// Cabeceras de día de la semana (lunes primero), mono uppercase.
const WEEKDAYS = ['L', 'M', 'X', 'J', 'V', 'S', 'D'];

// ok-date-picker — campo de fecha + popover calendario propio (distinto de ok-calendar, que es el
// calendario de eventos). Cubre lo que Ionic no trae de forma cómoda: selección single o range con
// chips de preset (Hoy / 7d / Esta semana / Mes / Trimestre / YTD), navegación de mes y estilado de
// rango (start / in-range / end con border-radius asimétrico tipo píldora).
//   • prop `mode`     → 'single' | 'range'
//   • prop `value`    → ISO `YYYY-MM-DD` (single) o {start,end} (range)
//   • prop `min/max`  → límites ISO (días fuera quedan deshabilitados)
//   • prop `presets`  → Array<OkDatePreset> (o false-y para ocultar la fila)
//   • prop `months`   → 1 | 2 (paneles lado a lado en pantalla ancha)
// El popover es position:absolute (anclado con computeAnchor; nunca fixed) para no romperse bajo
// ancestros con transform. Solo Date/Intl nativos; el icono de calendario es un ion-icon del host.
// Eventos (bubbles + composed):
//   • `ok-change` detail { value }  → ISO string (single) o {start,end} (range)
export class OkDatePicker extends LitElement {
  static styles = css`
    :host {
      /* Tokens propios estilo Ionic (overridables): --ok-* → --ion-* → hex. */
      --bg: var(--ok-surface, var(--ion-card-background, var(--ion-background-color, #ffffff)));
      --field-bg: var(--ok-field-bg, var(--ion-item-background, var(--ion-background-color, #ffffff)));
      --color: var(--ok-text-color, var(--ion-text-color, #1f2933));
      --color-muted: var(--ok-color-medium, var(--ion-color-medium, #92949c));
      --color-faint: var(--ok-color-faint, rgba(var(--ion-text-color-rgb, 31, 41, 51), 0.38));
      --border-color: var(--ok-border, rgba(var(--ion-text-color-rgb, 31, 41, 51), 0.14));
      --hover-bg: var(--ok-hover, rgba(var(--ion-text-color-rgb, 31, 41, 51), 0.06));
      --primary: var(--ok-primary, var(--ion-color-primary, #3880ff));
      --primary-contrast: var(--ok-primary-contrast, var(--ion-color-primary-contrast, #ffffff));
      --primary-soft: var(--ok-primary-soft, rgba(var(--ion-color-primary-rgb, 56, 128, 255), 0.16));
      --primary-strong: var(--ok-primary-shade, var(--ion-color-primary-shade, #3171e0));
      --radius: var(--ok-radius, 12px);
      --radius-sm: var(--ok-radius-sm, 8px);
      --shadow: var(--ok-shadow, 0 10px 32px rgba(0, 0, 0, 0.16));
      --font: var(--ok-font, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif);

      display: block;
      width: 100%;
      position: relative;
      color: var(--color);
      font-family: var(--font);
    }

    /* Campo disparador: icono de calendario + etiqueta tabular. */
    .field {
      display: inline-flex;
      align-items: center;
      gap: 0.5rem;
      width: 100%;
      box-sizing: border-box;
      padding: 0.5rem 0.75rem;
      min-height: 42px;
      border: 1px solid var(--border-color);
      border-radius: var(--radius-sm);
      background: var(--field-bg);
      color: inherit;
      font: inherit;
      cursor: pointer;
      text-align: left;
      transition: border-color 150ms ease, box-shadow 150ms ease;
    }
    .field:hover {
      border-color: var(--primary);
    }
    .field:focus-visible,
    .field.open {
      outline: none;
      border-color: var(--primary);
      box-shadow: 0 0 0 3px var(--primary-soft);
    }
    .field ion-icon {
      font-size: 1.15rem;
      color: var(--color-muted);
      flex-shrink: 0;
    }
    .field .label {
      flex: 1;
      font-variant-numeric: tabular-nums;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .field .label.placeholder {
      color: var(--color-muted);
    }

    /* Popover: position:absolute (nunca fixed), anclado al campo vía computeAnchor. */
    .popover {
      position: absolute;
      top: calc(100% + 6px);
      left: 0;
      z-index: 1000;
      background: var(--bg);
      border: 1px solid var(--border-color);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
      padding: 14px;
      user-select: none;
      box-sizing: border-box;
    }
    .popover.end {
      left: auto;
      right: 0;
    }
    .popover.above {
      top: auto;
      bottom: calc(100% + 6px);
    }

    /* Cuerpo: 1 o 2 meses lado a lado. */
    .months {
      display: grid;
      grid-template-columns: 1fr;
      gap: 22px;
    }
    .months.two {
      grid-template-columns: 1fr 1fr;
    }
    @media (max-width: 620px) {
      .months.two {
        grid-template-columns: 1fr;
      }
    }
    .month {
      width: 280px;
      max-width: 100%;
    }

    .head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 12px;
    }
    .title {
      font-size: 0.9rem;
      font-weight: 600;
      color: var(--color);
      text-transform: capitalize;
    }
    .nav {
      display: inline-flex;
      gap: 2px;
    }
    .nav-btn {
      width: 28px;
      height: 28px;
      border-radius: var(--radius-sm);
      background: transparent;
      border: 0;
      color: var(--color-muted);
      display: inline-grid;
      place-items: center;
      cursor: pointer;
      transition: background-color 150ms ease, color 150ms ease;
    }
    .nav-btn:hover {
      background: var(--hover-bg);
      color: var(--color);
    }
    .nav-btn ion-icon {
      font-size: 1.05rem;
    }

    /* Rejilla de 7 columnas: cabecera de día + días. */
    .grid {
      display: grid;
      grid-template-columns: repeat(7, 1fr);
      gap: 1px;
    }
    .dow {
      font-size: 0.625rem;
      color: var(--color-faint);
      text-align: center;
      padding: 4px 0;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      font-family: var(--ok-font-mono, ui-monospace, 'SF Mono', Menlo, monospace);
    }

    .day {
      height: 34px;
      border-radius: var(--radius-sm);
      background: transparent;
      border: 0;
      font-size: 0.8125rem;
      color: var(--color);
      display: grid;
      place-items: center;
      cursor: pointer;
      font-variant-numeric: tabular-nums;
      position: relative;
      transition: background-color 120ms ease, color 120ms ease;
    }
    .day:hover:not(:disabled):not(.selected) {
      background: var(--hover-bg);
    }
    .day.muted {
      color: var(--color-faint);
    }
    /* Hoy: anillo interior (inset ring), no relleno. */
    .day.today {
      color: var(--primary);
      font-weight: 600;
      box-shadow: inset 0 0 0 1.5px var(--primary);
    }
    .day.selected {
      background: var(--primary);
      color: var(--primary-contrast);
      font-weight: 600;
      box-shadow: none;
    }
    /* Rango: relleno suave para los días intermedios, esquinas rectas. */
    .day.in-range {
      background: var(--primary-soft);
      color: var(--primary-strong);
      border-radius: 0;
    }
    /* Extremos del rango: píldora con radio asimétrico (abierta hacia el interior). */
    .day.range-start {
      border-radius: var(--radius-sm) 0 0 var(--radius-sm);
    }
    .day.range-end {
      border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
    }
    .day.range-start.range-end {
      border-radius: var(--radius-sm);
    }
    .day:disabled {
      opacity: 0.3;
      cursor: not-allowed;
    }

    /* Chips de preset rápido. */
    .presets {
      display: flex;
      flex-wrap: wrap;
      gap: 4px;
      margin-top: 12px;
      padding-top: 12px;
      border-top: 1px solid var(--border-color);
    }
    .preset {
      font-size: 0.6875rem;
      padding: 4px 10px;
      background: var(--hover-bg);
      border: 1px solid var(--border-color);
      border-radius: 999px;
      color: var(--color-muted);
      cursor: pointer;
      transition: background-color 150ms ease, color 150ms ease, border-color 150ms ease;
    }
    .preset:hover {
      color: var(--color);
      border-color: var(--primary);
    }
    .preset.active {
      background: var(--primary-soft);
      color: var(--primary-strong);
      border-color: var(--primary);
      font-weight: 600;
    }

    @media (prefers-reduced-motion: reduce) {
      .field,
      .nav-btn,
      .day,
      .preset {
        transition: none;
      }
    }
  `;

  /** Modo: una fecha ('single') o un rango ('range'). */
  @property() mode: OkDatePickerMode = 'single';

  /** Valor actual: ISO `YYYY-MM-DD` (single) o {start,end} (range). */
  @property({ attribute: false }) value: OkDatePickerValue = null;

  /** Fecha mínima seleccionable (ISO `YYYY-MM-DD`). */
  @property() min?: string;

  /** Fecha máxima seleccionable (ISO `YYYY-MM-DD`). */
  @property() max?: string;

  /** Chips de preset; pasa `[]` para ocultar la fila. */
  @property({ attribute: false }) presets: OkDatePreset[] = DEFAULT_PRESETS;

  /** Locale para el nombre del mes (Intl). Default = es-ES. */
  @property() locale = 'es-ES';

  /** Texto del campo cuando no hay valor. */
  @property() placeholder = 'Seleccionar fecha';

  /** Número de meses visibles en el popover (1 o 2). */
  @property({ type: Number }) months: 1 | 2 = 1;

  /** Textos traducibles (merge sobre los defaults en español). */
  @property({ attribute: false }) labels: Partial<OkDatePickerLabels> = {};

  // Estado interno: popover abierto.
  @state() private open = false;
  // Lados resueltos por computeAnchor (alinear a la derecha / abrir hacia arriba).
  @state() private side = { end: false, above: false };
  // Primer día del mes mostrado en el panel izquierdo (se navega con las flechas).
  @state() private viewDate = startOfMonth(new Date());
  // Día sobre el que está el cursor mientras se elige el segundo extremo del rango (preview).
  @state() private hoverDate: Date | null = null;

  private get t(): OkDatePickerLabels {
    return { ...DEFAULT_LABELS, ...this.labels };
  }

  // Cierra al click fuera del componente.
  private readonly onDocPointer = (e: MouseEvent): void => {
    if (!this.open) return;
    if (e.composedPath().includes(this)) return;
    this.close();
  };

  private readonly onKeydown = (e: KeyboardEvent): void => {
    if (e.key === 'Escape' && this.open) {
      this.close();
      this.fieldEl?.focus();
    }
  };

  disconnectedCallback(): void {
    super.disconnectedCallback();
    this.unbind();
  }

  private get fieldEl(): HTMLElement | null {
    return this.renderRoot.querySelector('.field');
  }

  // Sincroniza el mes mostrado con el valor cuando se abre (para que el panel arranque donde toca).
  willUpdate(changed: Map<string, unknown>): void {
    if (changed.has('value') || (changed.has('open') && this.open)) {
      const anchor = this.anchorDateFromValue();
      if (anchor) this.viewDate = startOfMonth(anchor);
    }
  }

  private bind(): void {
    document.addEventListener('pointerdown', this.onDocPointer, true);
    document.addEventListener('keydown', this.onKeydown);
  }

  private unbind(): void {
    document.removeEventListener('pointerdown', this.onDocPointer, true);
    document.removeEventListener('keydown', this.onKeydown);
  }

  private toggle(): void {
    this.open ? this.close() : this.openPopover();
  }

  private openPopover(): void {
    if (this.open) return;
    this.open = true;
    this.bind();
    // Tras pintar el popover, calcular el lado con computeAnchor (anclaje absolute, no fixed).
    this.updateComplete.then(() => {
      const panel = this.renderRoot.querySelector('.popover') as HTMLElement | null;
      const field = this.fieldEl;
      if (panel && field) this.side = computeAnchor(field, panel, { gap: 6 });
    });
  }

  private close(): void {
    if (!this.open) return;
    this.open = false;
    this.hoverDate = null;
    this.unbind();
  }

  // ---- Helpers de valor ----------------------------------------------------

  private get rangeValue(): OkDateRange {
    const v = this.value;
    if (v && typeof v === 'object') return v;
    return { start: null, end: null };
  }

  private get singleValue(): string | null {
    return typeof this.value === 'string' ? this.value : null;
  }

  // Fecha de referencia para posicionar el mes inicial.
  private anchorDateFromValue(): Date | null {
    if (this.mode === 'range') {
      const r = this.rangeValue;
      return r.start ? parseISO(r.start) : r.end ? parseISO(r.end) : null;
    }
    return this.singleValue ? parseISO(this.singleValue) : null;
  }

  private get minDate(): Date | null {
    return this.min ? parseISO(this.min) : null;
  }
  private get maxDate(): Date | null {
    return this.max ? parseISO(this.max) : null;
  }

  private isDisabled(d: Date): boolean {
    const min = this.minDate;
    const max = this.maxDate;
    if (min && d < min) return true;
    if (max && d > max) return true;
    return false;
  }

  // ---- Selección -----------------------------------------------------------

  private selectDay(d: Date): void {
    if (this.isDisabled(d)) return;
    if (this.mode === 'single') {
      this.emit(toISO(d));
      this.close();
      return;
    }
    // Range: primer click fija start; segundo click cierra el rango (ordenando extremos).
    const r = this.rangeValue;
    if (!r.start || (r.start && r.end)) {
      this.hoverDate = null;
      this.emit({ start: toISO(d), end: null });
      return;
    }
    const start = parseISO(r.start);
    let next: OkDateRange;
    if (d < start) next = { start: toISO(d), end: r.start };
    else next = { start: r.start, end: toISO(d) };
    this.hoverDate = null;
    this.emit(next);
    this.close();
  }

  private emit(value: OkDatePickerValue): void {
    this.value = value;
    this.dispatchEvent(
      new CustomEvent('ok-change', { detail: { value }, bubbles: true, composed: true }),
    );
  }

  private prevMonth(): void {
    this.viewDate = addMonths(this.viewDate, -1);
  }
  private nextMonth(): void {
    this.viewDate = addMonths(this.viewDate, 1);
  }

  // ---- Presets -------------------------------------------------------------

  private applyPreset(id: string): void {
    const today = startOfDay(new Date());
    let value: OkDatePickerValue;
    let view = today;
    switch (id) {
      case 'today':
        value = this.mode === 'range' ? { start: toISO(today), end: toISO(today) } : toISO(today);
        break;
      case '7d': {
        const from = addDays(today, -6);
        value = this.mode === 'range' ? { start: toISO(from), end: toISO(today) } : toISO(from);
        view = from;
        break;
      }
      case 'week': {
        const from = startOfWeek(today);
        const to = addDays(from, 6);
        value = this.mode === 'range' ? { start: toISO(from), end: toISO(to) } : toISO(from);
        view = from;
        break;
      }
      case 'month': {
        const from = startOfMonth(today);
        const to = endOfMonth(today);
        value = this.mode === 'range' ? { start: toISO(from), end: toISO(to) } : toISO(from);
        view = from;
        break;
      }
      case 'quarter': {
        const q = Math.floor(today.getMonth() / 3);
        const from = new Date(today.getFullYear(), q * 3, 1);
        const to = endOfMonth(new Date(today.getFullYear(), q * 3 + 2, 1));
        value = this.mode === 'range' ? { start: toISO(from), end: toISO(to) } : toISO(from);
        view = from;
        break;
      }
      case 'ytd': {
        const from = new Date(today.getFullYear(), 0, 1);
        value = this.mode === 'range' ? { start: toISO(from), end: toISO(today) } : toISO(from);
        view = from;
        break;
      }
      default:
        return;
    }
    this.viewDate = startOfMonth(view);
    this.emit(value);
    if (this.mode === 'single') this.close();
  }

  // Decide si un preset está activo comparándolo con el valor actual.
  private isPresetActive(id: string): boolean {
    const expect = this.presetValue(id);
    if (!expect) return false;
    if (this.mode === 'range') {
      const r = this.rangeValue;
      const e = expect as OkDateRange;
      return r.start === e.start && r.end === e.end;
    }
    return this.singleValue === expect;
  }

  // Calcula (sin emitir) qué valor produciría un preset, para resaltar el chip activo.
  private presetValue(id: string): OkDatePickerValue {
    const today = startOfDay(new Date());
    const mk = (from: Date, to: Date): OkDatePickerValue =>
      this.mode === 'range' ? { start: toISO(from), end: toISO(to) } : toISO(from);
    switch (id) {
      case 'today':
        return mk(today, today);
      case '7d':
        return mk(addDays(today, -6), today);
      case 'week': {
        const from = startOfWeek(today);
        return mk(from, addDays(from, 6));
      }
      case 'month':
        return mk(startOfMonth(today), endOfMonth(today));
      case 'quarter': {
        const q = Math.floor(today.getMonth() / 3);
        return mk(
          new Date(today.getFullYear(), q * 3, 1),
          endOfMonth(new Date(today.getFullYear(), q * 3 + 2, 1)),
        );
      }
      case 'ytd':
        return mk(new Date(today.getFullYear(), 0, 1), today);
      default:
        return null;
    }
  }

  // ---- Render --------------------------------------------------------------

  // Etiqueta del campo a partir del valor (formato tabular, locale del componente).
  private fieldLabel(): string {
    const fmt = (iso: string): string =>
      new Date(parseISO(iso)).toLocaleDateString(this.locale, {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
      });
    if (this.mode === 'range') {
      const r = this.rangeValue;
      if (r.start && r.end) return `${fmt(r.start)} – ${fmt(r.end)}`;
      if (r.start) return `${fmt(r.start)} – …`;
      return '';
    }
    return this.singleValue ? fmt(this.singleValue) : '';
  }

  render(): unknown {
    const label = this.fieldLabel();
    const panels = this.months === 2 ? [0, 1] : [0];
    return html`
      <button
        type="button"
        class="field ${this.open ? 'open' : ''}"
        aria-haspopup="dialog"
        aria-expanded=${this.open ? 'true' : 'false'}
        aria-label=${label || this.t.open}
        @click=${() => this.toggle()}
      >
        <ion-icon name="calendar-outline"></ion-icon>
        <span class="label ${label ? '' : 'placeholder'}">${label || this.placeholder}</span>
      </button>
      ${this.open
        ? html`<div
            class="popover ${this.side.end ? 'end' : ''} ${this.side.above ? 'above' : ''}"
            role="dialog"
            aria-modal="false"
          >
            <div class="months ${this.months === 2 ? 'two' : ''}">
              ${panels.map((offset) => this.renderMonth(addMonths(this.viewDate, offset), offset))}
            </div>
            ${this.presets && this.presets.length
              ? html`<div class="presets" role="group">
                  ${this.presets.map(
                    (p) => html`<button
                      type="button"
                      class="preset ${this.isPresetActive(p.id) ? 'active' : ''}"
                      aria-pressed=${this.isPresetActive(p.id) ? 'true' : 'false'}
                      @click=${() => this.applyPreset(p.id)}
                    >
                      ${p.label}
                    </button>`,
                  )}
                </div>`
              : nothing}
          </div>`
        : nothing}
    `;
  }

  // Render de un mes: cabecera con navegación (solo el primer panel mueve la vista global), header de
  // días y rejilla de 6 semanas (lunes primero).
  private renderMonth(monthDate: Date, offset: number): unknown {
    const title = monthDate.toLocaleDateString(this.locale, { month: 'long', year: 'numeric' });
    const days = monthGridDays(monthDate);
    return html`
      <div class="month">
        <div class="head">
          ${offset === 0
            ? html`<button
                type="button"
                class="nav-btn"
                aria-label=${this.t.prev}
                @click=${() => this.prevMonth()}
              >
                <ion-icon name="chevron-back-outline"></ion-icon>
              </button>`
            : html`<span style="width:28px"></span>`}
          <span class="title">${title}</span>
          ${offset === (this.months === 2 ? 1 : 0)
            ? html`<button
                type="button"
                class="nav-btn"
                aria-label=${this.t.next}
                @click=${() => this.nextMonth()}
              >
                <ion-icon name="chevron-forward-outline"></ion-icon>
              </button>`
            : html`<span style="width:28px"></span>`}
        </div>
        <div class="grid" role="grid">
          ${WEEKDAYS.map((d) => html`<div class="dow" role="columnheader">${d}</div>`)}
          ${days.map((d) => this.renderDay(d, monthDate))}
        </div>
      </div>
    `;
  }

  private renderDay(d: Date, monthDate: Date): unknown {
    const inMonth = d.getMonth() === monthDate.getMonth();
    const disabled = this.isDisabled(d);
    const today = isSameDay(d, new Date());
    const cls = ['day'];
    if (!inMonth) cls.push('muted');
    if (today) cls.push('today');

    const flags = this.dayRangeFlags(d);
    if (flags.selected) cls.push('selected');
    if (flags.inRange) cls.push('in-range');
    if (flags.rangeStart) cls.push('range-start');
    if (flags.rangeEnd) cls.push('range-end');

    return html`<button
      type="button"
      class=${cls.join(' ')}
      role="gridcell"
      ?disabled=${disabled}
      aria-selected=${flags.selected ? 'true' : 'false'}
      aria-current=${today ? 'date' : nothing}
      @click=${() => this.selectDay(d)}
      @mouseenter=${() => this.onDayHover(d)}
    >
      ${d.getDate()}
    </button>`;
  }

  // Hover durante la selección del segundo extremo (preview del rango).
  private onDayHover(d: Date): void {
    if (this.mode !== 'range') return;
    const r = this.rangeValue;
    if (r.start && !r.end) this.hoverDate = d;
  }

  // Banderas de estado de un día respecto a la selección (single o range, con preview de hover).
  private dayRangeFlags(d: Date): {
    selected: boolean;
    inRange: boolean;
    rangeStart: boolean;
    rangeEnd: boolean;
  } {
    const none = { selected: false, inRange: false, rangeStart: false, rangeEnd: false };
    if (this.mode === 'single') {
      const v = this.singleValue;
      return v && isSameDay(d, parseISO(v)) ? { ...none, selected: true } : none;
    }
    const r = this.rangeValue;
    if (!r.start) return none;
    let start = parseISO(r.start);
    let end = r.end ? parseISO(r.end) : this.hoverDate;
    if (!end) {
      // Solo hay start fijado: ese día es el extremo seleccionado.
      return isSameDay(d, start) ? { ...none, selected: true, rangeStart: true, rangeEnd: true } : none;
    }
    // Ordena extremos (el hover puede ir antes del start).
    if (end < start) [start, end] = [end, start];
    const isStart = isSameDay(d, start);
    const isEnd = isSameDay(d, end);
    if (isStart || isEnd) {
      return {
        selected: true,
        inRange: false,
        rangeStart: isStart,
        rangeEnd: isEnd,
      };
    }
    if (d > start && d < end) return { ...none, inRange: true };
    return none;
  }
}

// ---- Utilidades de fecha (Date nativo; sin libs) ---------------------------

// Parsea `YYYY-MM-DD` a Date local (mediodía evita saltos por DST).
function parseISO(iso: string): Date {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(y, (m || 1) - 1, d || 1);
}

// Serializa a `YYYY-MM-DD` en hora local.
function toISO(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

function startOfDay(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate());
}

function startOfMonth(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), 1);
}

function endOfMonth(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth() + 1, 0);
}

function addMonths(d: Date, n: number): Date {
  return new Date(d.getFullYear(), d.getMonth() + n, 1);
}

function addDays(d: Date, n: number): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);
}

// Lunes como primer día de la semana (getDay(): 0=domingo).
function startOfWeek(d: Date): Date {
  const day = (d.getDay() + 6) % 7;
  return addDays(startOfDay(d), -day);
}

function isSameDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

// 42 días (6 semanas) empezando en el lunes de la semana del día 1 del mes.
function monthGridDays(monthDate: Date): Date[] {
  const first = startOfMonth(monthDate);
  const gridStart = startOfWeek(first);
  const out: Date[] = [];
  for (let i = 0; i < 42; i++) out.push(addDays(gridStart, i));
  return out;
}

define('ok-date-picker', OkDatePicker);

declare global {
  interface HTMLElementTagNameMap {
    'ok-date-picker': OkDatePicker;
  }
}
