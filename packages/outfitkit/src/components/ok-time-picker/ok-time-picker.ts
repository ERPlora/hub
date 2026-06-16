import { LitElement, html, css } from 'lit';
import { property, state } from 'lit/decorators.js';
import { define } from '../../base/define.js';
import { computeAnchor } from '../../base/anchor.js';

// ok-time-picker — selector compacto de hora del día. Mucho más ligero que `ion-datetime`:
// una "pastilla" inline con dos campos mono (HH y MM) separados por dos puntos, con `tabular-nums`.
// Al pulsar la pastilla abre un POPOVER propio (position:absolute, anclado con computeAnchor) con
// listas desplazables de horas y minutos (y AM/PM si `use-ampm`). El valor canónico SIEMPRE es
// 24h "HH:MM"; `use-ampm` solo afecta a la presentación.
//
// Props:
//   • value     "HH:MM" (24h, valor canónico)
//   • step      paso de minutos para la lista (default 5)
//   • use-ampm  presentación 12h con segmento AM/PM
//   • min/max   "HH:MM" que acotan las horas/minutos seleccionables
//   • disabled  desactiva la interacción
// Evento: `ok-change` detail { value } (bubbles + composed) al cambiar la hora.

// Resultado de un parseo "HH:MM" a minutos desde medianoche (o null si inválido).
type Minutes = number | null;

// Convierte "HH:MM" a minutos desde medianoche; null si no es un valor válido.
function parseHHMM(v: string | undefined): Minutes {
  if (!v) return null;
  const m = /^(\d{1,2}):(\d{1,2})$/.exec(v.trim());
  if (!m) return null;
  const h = Number(m[1]);
  const mm = Number(m[2]);
  if (h < 0 || h > 23 || mm < 0 || mm > 59) return null;
  return h * 60 + mm;
}

// Formatea minutos desde medianoche a "HH:MM" (24h, cero a la izquierda).
function toHHMM(total: number): string {
  const t = ((total % 1440) + 1440) % 1440;
  const h = Math.floor(t / 60);
  const mm = t % 60;
  return `${String(h).padStart(2, '0')}:${String(mm).padStart(2, '0')}`;
}

const pad2 = (n: number): string => String(n).padStart(2, '0');

export class OkTimePicker extends LitElement {
  static styles = css`
    :host {
      /* Tokens propios estilo Ionic (overridables): --ok-* → --ion-* → hex. */
      --color: var(--ok-text-color, var(--ion-text-color, #1f2933));
      --color-muted: var(--ok-color-medium, var(--ion-color-medium, #92949c));
      --surface: var(--ok-surface, var(--ion-card-background, var(--ion-background-color, #ffffff)));
      --border-color: var(--ok-border, rgba(var(--ion-text-color-rgb, 31, 41, 51), 0.14));
      --hover-bg: var(--ok-hover, rgba(var(--ion-text-color-rgb, 31, 41, 51), 0.06));
      --primary-color: var(--ok-primary, var(--ion-color-primary, #3880ff));
      --primary-contrast: var(--ok-primary-contrast, var(--ion-color-primary-contrast, #ffffff));
      --primary-soft: var(--ok-primary-soft, rgba(var(--ion-color-primary-rgb, 56, 128, 255), 0.14));
      --radius: var(--ok-radius, 10px);
      --shadow: var(--ok-shadow, 0 8px 28px rgba(0, 0, 0, 0.18));
      --font: var(--ok-font, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif);

      /* Inline: ocupa solo lo que mide la pastilla. */
      display: inline-block;
      position: relative;
      color: var(--color);
      font-family: var(--font);
    }

    /* Pastilla disparadora: HH : MM (+ AM/PM) en mono tabular. */
    .pill {
      display: inline-flex;
      align-items: center;
      gap: 0.1rem;
      padding: 0.3rem 0.6rem;
      border: 1px solid var(--border-color);
      border-radius: var(--radius);
      background: var(--surface);
      color: inherit;
      font-family: inherit;
      cursor: pointer;
      transition: border-color 150ms ease, box-shadow 150ms ease, background-color 150ms ease;
    }
    @media (hover: hover) {
      .pill:hover:not([disabled]) {
        background: var(--hover-bg);
      }
    }
    .pill:focus-visible {
      outline: none;
      border-color: var(--primary-color);
      box-shadow: 0 0 0 3px var(--primary-soft);
    }
    .pill[disabled] {
      opacity: 0.5;
      cursor: not-allowed;
    }
    .pill.open {
      border-color: var(--primary-color);
    }

    /* Campos numéricos: mono + tabular-nums para que HH/MM no "bailen". */
    .field {
      font-size: 1.05rem;
      font-weight: 600;
      line-height: 1;
      font-variant-numeric: tabular-nums;
      font-family: ui-monospace, 'SF Mono', 'Cascadia Code', Menlo, Consolas, monospace;
      min-width: 1.7ch;
      text-align: center;
    }
    .colon {
      font-size: 1.05rem;
      font-weight: 600;
      line-height: 1;
      opacity: 0.7;
      padding: 0 0.05rem;
    }
    .meridiem {
      margin-left: 0.3rem;
      font-size: 0.7rem;
      font-weight: 700;
      letter-spacing: 0.04em;
      color: var(--color-muted);
    }
    .caret {
      margin-left: 0.35rem;
      font-size: 0.95rem;
      color: var(--color-muted);
      transition: transform 180ms ease;
    }
    .pill.open .caret {
      transform: rotate(180deg);
    }

    /* Popover propio: absolute (NO fixed) para no romperse bajo ancestros transformados. */
    .panel {
      position: absolute;
      top: 100%;
      left: 0;
      margin-top: 6px;
      z-index: 50;
      display: flex;
      background: var(--surface);
      border: 1px solid var(--border-color);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
      overflow: hidden;
    }
    .panel.end {
      left: auto;
      right: 0;
    }
    .panel.above {
      top: auto;
      bottom: 100%;
      margin-top: 0;
      margin-bottom: 6px;
    }

    /* Columna desplazable de opciones (horas / minutos / meridiano). */
    .col {
      display: flex;
      flex-direction: column;
      max-height: 220px;
      overflow-y: auto;
      scrollbar-width: thin;
      border-right: 1px solid var(--border-color);
      padding: 0.25rem 0;
    }
    .col:last-child {
      border-right: 0;
    }
    .opt {
      padding: 0.35rem 1rem;
      font-size: 0.85rem;
      font-variant-numeric: tabular-nums;
      font-family: ui-monospace, 'SF Mono', 'Cascadia Code', Menlo, Consolas, monospace;
      background: transparent;
      border: 0;
      color: var(--color-muted);
      cursor: pointer;
      text-align: center;
      min-width: 56px;
      transition: background-color 120ms ease, color 120ms ease;
    }
    @media (hover: hover) {
      .opt:hover:not([disabled]) {
        background: var(--hover-bg);
        color: var(--color);
      }
    }
    .opt[aria-selected='true'] {
      background: var(--primary-soft);
      color: var(--primary-color);
      font-weight: 700;
    }
    .opt[disabled] {
      opacity: 0.35;
      cursor: not-allowed;
    }
    .opt:focus-visible {
      outline: none;
      background: var(--primary-soft);
      color: var(--primary-color);
    }

    @media (prefers-reduced-motion: reduce) {
      .pill,
      .caret,
      .opt {
        transition: none;
      }
    }
  `;

  /** Valor canónico "HH:MM" (24h). */
  @property() value = '';

  /** Paso de minutos para la lista de minutos (default 5). */
  @property({ type: Number }) step = 5;

  /** Presentación 12h con segmento AM/PM (el valor sigue siendo 24h). */
  @property({ type: Boolean, attribute: 'use-ampm' }) useAmpm = false;

  /** Hora mínima seleccionable "HH:MM" (inclusive). */
  @property() min = '';

  /** Hora máxima seleccionable "HH:MM" (inclusive). */
  @property() max = '';

  /** Desactiva la interacción. */
  @property({ type: Boolean, reflect: true }) disabled = false;

  // Estado interno: popover abierto.
  @state() private open = false;
  // Lado calculado del popover (alineación / dirección).
  @state() private end = false;
  @state() private above = false;

  // Cierra al hacer click fuera del componente.
  private readonly onDocPointer = (e: Event): void => {
    if (!this.open) return;
    if (e.composedPath().includes(this)) return;
    this.close();
  };

  // Esc cierra el popover.
  private readonly onKeydown = (e: KeyboardEvent): void => {
    if (e.key === 'Escape' && this.open) {
      e.stopPropagation();
      this.close();
    }
  };

  disconnectedCallback(): void {
    super.disconnectedCallback();
    this.unbind();
  }

  private bind(): void {
    document.addEventListener('pointerdown', this.onDocPointer, true);
    document.addEventListener('keydown', this.onKeydown);
  }

  private unbind(): void {
    document.removeEventListener('pointerdown', this.onDocPointer, true);
    document.removeEventListener('keydown', this.onKeydown);
  }

  // Minutos canónicos del valor actual (null si vacío/ inválido).
  private get current(): Minutes {
    return parseHHMM(this.value);
  }

  private get minMin(): Minutes {
    return parseHHMM(this.min);
  }

  private get maxMin(): Minutes {
    return parseHHMM(this.max);
  }

  // ¿Un total de minutos cae dentro de [min, max]?
  private inRange(total: number): boolean {
    const lo = this.minMin;
    const hi = this.maxMin;
    if (lo !== null && total < lo) return false;
    if (hi !== null && total > hi) return false;
    return true;
  }

  private toggle(): void {
    if (this.disabled) return;
    this.open ? this.close() : this.openPanel();
  }

  private openPanel(): void {
    if (this.open) return;
    this.open = true;
    this.bind();
    // Tras montar el panel, calculamos el lado con espacio y centramos la selección.
    this.updateComplete.then(() => {
      this.reanchor();
      this.scrollToSelected();
    });
  }

  private close(): void {
    if (!this.open) return;
    this.open = false;
    this.unbind();
  }

  // Recalcula alineación del popover según el espacio en viewport.
  private reanchor(): void {
    const trigger = this.renderRoot.querySelector('.pill') as HTMLElement | null;
    const panel = this.renderRoot.querySelector('.panel') as HTMLElement | null;
    if (!trigger || !panel) return;
    const side = computeAnchor(trigger, panel);
    this.end = side.end;
    this.above = side.above;
  }

  // Centra (sin animación brusca) la opción seleccionada en cada columna al abrir.
  private scrollToSelected(): void {
    const sel = this.renderRoot.querySelectorAll<HTMLElement>('.opt[aria-selected="true"]');
    sel.forEach((el) => {
      const col = el.parentElement;
      if (col) col.scrollTop = el.offsetTop - col.clientHeight / 2 + el.clientHeight / 2;
    });
  }

  // Emite el nuevo valor canónico y lo refleja en la prop.
  private commit(total: number): void {
    const next = toHHMM(total);
    if (next === this.value) return;
    this.value = next;
    this.dispatchEvent(
      new CustomEvent('ok-change', {
        detail: { value: next },
        bubbles: true,
        composed: true,
      }),
    );
  }

  // Selecciona la hora (manteniendo los minutos actuales o 0).
  private pickHour(h: number): void {
    const cur = this.current;
    const mm = cur !== null ? cur % 60 : 0;
    this.commit(h * 60 + mm);
  }

  // Selecciona el minuto (manteniendo la hora actual o 0).
  private pickMinute(mm: number): void {
    const cur = this.current;
    const h = cur !== null ? Math.floor(cur / 60) : 0;
    this.commit(h * 60 + mm);
  }

  // Cambia el meridiano (AM/PM) desplazando la hora ±12 si hace falta.
  private pickMeridiem(pm: boolean): void {
    const cur = this.current ?? 0;
    let h = Math.floor(cur / 60);
    const mm = cur % 60;
    const isPm = h >= 12;
    if (pm && !isPm) h += 12;
    else if (!pm && isPm) h -= 12;
    this.commit(h * 60 + mm);
  }

  // Lista de horas válidas (0..23). El filtrado de rango se aplica por opción.
  private hourOptions(): number[] {
    return Array.from({ length: 24 }, (_, i) => i);
  }

  // Lista de minutos según `step` (siempre ≥1, ≤30 por seguridad).
  private minuteOptions(): number[] {
    const step = Math.min(Math.max(Math.floor(this.step) || 5, 1), 30);
    const out: number[] = [];
    for (let m = 0; m < 60; m += step) out.push(m);
    return out;
  }

  // Texto del campo HH para la pastilla (12h si use-ampm, con la hora canónica si existe).
  private displayHour(): string {
    const cur = this.current;
    if (cur === null) return '--';
    const h24 = Math.floor(cur / 60);
    if (this.useAmpm) {
      const h12 = h24 % 12 === 0 ? 12 : h24 % 12;
      return pad2(h12);
    }
    return pad2(h24);
  }

  private displayMinute(): string {
    const cur = this.current;
    if (cur === null) return '--';
    return pad2(cur % 60);
  }

  // Etiqueta de hora dentro de la columna (respeta 12h/24h).
  private hourLabel(h24: number): string {
    if (this.useAmpm) {
      const h12 = h24 % 12 === 0 ? 12 : h24 % 12;
      return pad2(h12);
    }
    return pad2(h24);
  }

  private get isPm(): boolean {
    const cur = this.current;
    return cur !== null && Math.floor(cur / 60) >= 12;
  }

  render(): unknown {
    const cur = this.current;
    const selHour = cur !== null ? Math.floor(cur / 60) : -1;
    const selMinute = cur !== null ? cur % 60 : -1;

    return html`
      <button
        type="button"
        class="pill ${this.open ? 'open' : ''}"
        ?disabled=${this.disabled}
        aria-haspopup="listbox"
        aria-expanded=${this.open ? 'true' : 'false'}
        aria-label="Time picker"
        @click=${() => this.toggle()}
      >
        <span class="field" aria-hidden="true">${this.displayHour()}</span>
        <span class="colon" aria-hidden="true">:</span>
        <span class="field" aria-hidden="true">${this.displayMinute()}</span>
        ${this.useAmpm
          ? html`<span class="meridiem">${this.isPm ? 'PM' : 'AM'}</span>`
          : null}
        <span class="caret" aria-hidden="true">▾</span>
      </button>
      ${this.open ? this.panelTemplate(selHour, selMinute) : null}
    `;
  }

  private panelTemplate(selHour: number, selMinute: number): unknown {
    const cls = `panel ${this.end ? 'end' : ''} ${this.above ? 'above' : ''}`;
    return html`
      <div class=${cls} role="dialog" aria-label="Choose time">
        <div class="col" role="listbox" aria-label="Hours">
          ${this.hourOptions().map((h) => {
            // Una hora está disponible si existe ALGÚN minuto del paso dentro del rango.
            const enabled = this.minuteOptions().some((mm) => this.inRange(h * 60 + mm));
            const selected = h === selHour;
            return html`<button
              type="button"
              class="opt"
              role="option"
              aria-selected=${selected ? 'true' : 'false'}
              ?disabled=${!enabled}
              @click=${() => this.pickHour(h)}
            >
              ${this.hourLabel(h)}
            </button>`;
          })}
        </div>
        <div class="col" role="listbox" aria-label="Minutes">
          ${this.minuteOptions().map((mm) => {
            const baseHour = selHour >= 0 ? selHour : 0;
            const enabled = this.inRange(baseHour * 60 + mm);
            const selected = mm === selMinute;
            return html`<button
              type="button"
              class="opt"
              role="option"
              aria-selected=${selected ? 'true' : 'false'}
              ?disabled=${!enabled}
              @click=${() => this.pickMinute(mm)}
            >
              ${pad2(mm)}
            </button>`;
          })}
        </div>
        ${this.useAmpm
          ? html`<div class="col" role="listbox" aria-label="AM/PM">
              ${['AM', 'PM'].map((m, i) => {
                const pm = i === 1;
                const selected = this.current !== null && pm === this.isPm;
                return html`<button
                  type="button"
                  class="opt"
                  role="option"
                  aria-selected=${selected ? 'true' : 'false'}
                  @click=${() => this.pickMeridiem(pm)}
                >
                  ${m}
                </button>`;
              })}
            </div>`
          : null}
      </div>
    `;
  }
}

define('ok-time-picker', OkTimePicker);

declare global {
  interface HTMLElementTagNameMap {
    'ok-time-picker': OkTimePicker;
  }
}
