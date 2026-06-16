import { LitElement, html, css } from 'lit';
import { property } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// ok-bar-list — lista ranking de barras horizontales (top-N).
// Cada fila es un grid de 3 columnas: etiqueta (ellipsis) / track con relleno animado / valor
// (tabular-nums, en negrita). El ancho del relleno es proporcional al valor frente a `max`
// (auto-calculado del dataset si no se da). Presentacional: no emite eventos.
//   • prop `.items`        → BarListItem[] (label, value, color?)
//   • prop `max`           → tope de la escala (def: máximo de los valores)
//   • prop `value-format`  → 'number' | 'compact' | 'currency' | 'percent' (def 'number')
//   • prop `locale`        → locale para Intl (def navegador)
//   • prop `currency`      → divisa ISO si value-format='currency' (def 'EUR')
// El color por ítem acepta una variante semántica (brand/leaf/warn/info/danger) o un color CSS
// literal; si no se da, usa la variante 'brand' (token --bar-brand).

/** Variante de color semántica predefinida para una barra. */
export type BarListColor = 'brand' | 'leaf' | 'warn' | 'info' | 'danger';

/** Formato de presentación del valor numérico. */
export type BarListValueFormat = 'number' | 'compact' | 'currency' | 'percent';

/** Un ítem de la lista de barras. */
export interface BarListItem {
  /** Texto de la fila (se trunca con ellipsis si no cabe). */
  label: string;
  /** Valor numérico; determina el ancho del relleno y el texto del valor. */
  value: number;
  /** Variante semántica o color CSS literal del relleno (def 'brand'). */
  color?: BarListColor | string;
}

const SEMANTIC: ReadonlySet<string> = new Set(['brand', 'leaf', 'warn', 'info', 'danger']);

export class OkBarList extends LitElement {
  static styles = css`
    :host {
      display: block;
      width: 100%;

      /* Tokens propios estilo Ionic: --ok-* → --ion-* → hex. */
      --label-color: var(--ok-color-medium, var(--ion-color-medium, #6b7280));
      --value-color: var(--ok-text-color, var(--ion-text-color, #1f2933));
      --track-bg: var(--ok-color-step-100, var(--ion-color-step-100, #e5e7eb));

      /* Variantes de color del relleno. */
      --bar-brand: var(--ok-primary, var(--ion-color-primary, #3880ff));
      --bar-leaf: var(--ok-success, var(--ion-color-success, #2dd36f));
      --bar-warn: var(--ok-warning, var(--ion-color-warning, #ffc409));
      --bar-info: var(--ok-tertiary, var(--ion-color-tertiary, #5260ff));
      --bar-danger: var(--ok-danger, var(--ion-color-danger, #eb445a));

      /* Geometría del track. */
      --track-height: 8px;
      --track-radius: 4px;
      --label-width: 110px;
      --value-width: 60px;
    }

    .bars {
      display: flex;
      flex-direction: column;
      gap: 8px;
      width: 100%;
      box-sizing: border-box;
    }

    .row {
      display: grid;
      grid-template-columns: var(--label-width) 1fr var(--value-width);
      gap: 10px;
      align-items: center;
      font-size: 0.75rem;
    }

    .label {
      color: var(--label-color);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      min-width: 0;
    }

    .track {
      height: var(--track-height);
      background: var(--track-bg);
      border-radius: var(--track-radius);
      overflow: hidden;
      position: relative;
    }

    .fill {
      height: 100%;
      border-radius: var(--track-radius);
      background: var(--bar-brand);
      transition: width 0.5s cubic-bezier(0.22, 1, 0.36, 1);
      min-width: 2px;
    }

    .value {
      text-align: right;
      font-variant-numeric: tabular-nums;
      color: var(--value-color);
      font-weight: 700;
      white-space: nowrap;
    }

    /* En móvil estrecho compactamos la columna de etiqueta. */
    @media (max-width: 420px) {
      .row {
        --label-width: 80px;
        --value-width: 52px;
      }
    }

    @media (prefers-reduced-motion: reduce) {
      .fill {
        transition: none;
      }
    }
  `;

  /** Lista de ítems a representar (se asigna como propiedad desde JS). */
  @property({ attribute: false }) items: BarListItem[] = [];

  /** Tope de la escala; si no se da, se usa el valor máximo del dataset. */
  @property({ type: Number }) max?: number;

  /** Formato de presentación del valor. */
  @property({ attribute: 'value-format' }) valueFormat: BarListValueFormat = 'number';

  /** Locale para Intl.NumberFormat (def: navegador). */
  @property() locale = '';

  /** Divisa ISO 4217 cuando value-format='currency'. */
  @property() currency = 'EUR';

  // Tope efectivo de la escala: prop `max` o el máximo de los valores (mínimo 1 para evitar /0).
  private get scaleMax(): number {
    if (this.max != null && this.max > 0) return this.max;
    const values = (this.items ?? []).map((i) => i.value);
    return Math.max(1, ...values);
  }

  // Devuelve el background CSS del relleno según el color del ítem.
  private fillColor(color?: string): string {
    if (!color) return 'var(--bar-brand)';
    if (SEMANTIC.has(color)) return `var(--bar-${color})`;
    return color; // color CSS literal
  }

  // Formatea el valor según value-format usando Intl nativo.
  private formatValue(value: number): string {
    const locale = this.locale || undefined;
    switch (this.valueFormat) {
      case 'compact':
        return new Intl.NumberFormat(locale, { notation: 'compact', maximumFractionDigits: 1 }).format(value);
      case 'currency':
        return new Intl.NumberFormat(locale, {
          style: 'currency',
          currency: this.currency,
          maximumFractionDigits: 0,
        }).format(value);
      case 'percent':
        return new Intl.NumberFormat(locale, { style: 'percent', maximumFractionDigits: 1 }).format(value);
      case 'number':
      default:
        return new Intl.NumberFormat(locale).format(value);
    }
  }

  render(): unknown {
    const items = this.items ?? [];
    const max = this.scaleMax;
    return html`
      <div class="bars" role="list">
        ${items.map((item) => {
          // Ancho proporcional del relleno, acotado a [0, 100].
          const pct = Math.max(0, Math.min(100, (item.value / max) * 100));
          const formatted = this.formatValue(item.value);
          return html`
            <div class="row" role="listitem">
              <span class="label" title=${item.label}>${item.label}</span>
              <div
                class="track"
                role="progressbar"
                aria-label=${item.label}
                aria-valuemin="0"
                aria-valuemax=${max}
                aria-valuenow=${item.value}
                aria-valuetext=${formatted}
              >
                <div class="fill" style=${`width:${pct}%;background:${this.fillColor(item.color)}`}></div>
              </div>
              <span class="value">${formatted}</span>
            </div>
          `;
        })}
      </div>
    `;
  }
}

define('ok-bar-list', OkBarList);

declare global {
  interface HTMLElementTagNameMap {
    'ok-bar-list': OkBarList;
  }
}
