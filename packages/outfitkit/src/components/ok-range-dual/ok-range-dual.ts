import { LitElement, html, css } from 'lit';
import { property } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// ok-range-dual — slider min-max de doble thumb (hueco que Ionic no cubre: ion-range
// es de un solo valor o dual sin fill/readout propio). Dos <input type=range> apilados
// sobre una pista compartida, con relleno coloreado entre los thumbs y readout "low – high".

/** Detalle del evento ok-change emitido al mover cualquiera de los dos thumbs. */
export interface OkRangeDualChangeDetail {
  low: number;
  high: number;
}

export class OkRangeDual extends LitElement {
  static styles = css`
    :host {
      display: block;
      width: 100%;
      box-sizing: border-box;
      /* Tokens propios estilo Ionic (overridables): --ok-* → --ion-* → hex. */
      --track-color: var(--ok-range-track, var(--ion-color-step-150, #e0e2e6));
      --fill-color: var(--ok-range-fill, var(--ion-color-primary, #3880ff));
      --thumb-bg: var(--ok-range-thumb-bg, var(--ion-background-color, #ffffff));
      --thumb-border: var(--ok-range-thumb-border, var(--ion-color-primary, #3880ff));
      --label-color: var(--ok-color-medium, var(--ion-color-medium, #92949c));
      --value-color: var(--ok-text-color, var(--ion-text-color, #1f2933));
      --value-bg: var(--ok-range-value-bg, var(--ion-color-step-100, #f1f2f4));
      --focus-ring: var(--ok-range-focus, var(--ion-color-primary-tint, #4c8dff));
    }

    .block {
      display: grid;
      gap: 6px;
      width: 100%;
    }

    .head {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      font-size: 0.8125rem;
    }

    .label {
      color: var(--label-color);
      font-weight: 500;
    }

    .readout {
      color: var(--value-color);
      font-variant-numeric: tabular-nums;
      background: var(--value-bg);
      padding: 1px 8px;
      border-radius: 6px;
      font-size: 12px;
      white-space: nowrap;
    }

    /* Pista + thumbs apilados */
    .range {
      position: relative;
      height: 24px;
    }

    .track {
      position: absolute;
      top: 50%;
      left: 0;
      right: 0;
      height: 4px;
      transform: translateY(-50%);
      background: var(--track-color);
      border-radius: 999px;
      pointer-events: none;
    }

    .fill {
      position: absolute;
      top: 50%;
      transform: translateY(-50%);
      height: 4px;
      border-radius: 999px;
      background: var(--fill-color);
      pointer-events: none;
    }

    /* Ambos inputs ocupan toda la pista; solo el thumb captura el puntero */
    input[type='range'] {
      position: absolute;
      inset: 0;
      width: 100%;
      height: 100%;
      appearance: none;
      -webkit-appearance: none;
      background: transparent;
      pointer-events: none;
      margin: 0;
    }

    input[type='range']::-webkit-slider-thumb {
      -webkit-appearance: none;
      appearance: none;
      width: 16px;
      height: 16px;
      border-radius: 50%;
      background: var(--thumb-bg);
      border: 2px solid var(--thumb-border);
      box-shadow: 0 1px 2px rgba(0, 0, 0, 0.25);
      pointer-events: auto;
      cursor: grab;
      transition: transform 0.12s ease;
    }
    input[type='range']::-webkit-slider-thumb:hover {
      transform: scale(1.15);
    }
    input[type='range']:active::-webkit-slider-thumb {
      cursor: grabbing;
    }

    input[type='range']::-moz-range-thumb {
      width: 14px;
      height: 14px;
      border-radius: 50%;
      background: var(--thumb-bg);
      border: 2px solid var(--thumb-border);
      box-shadow: 0 1px 2px rgba(0, 0, 0, 0.25);
      pointer-events: auto;
      cursor: grab;
    }

    input[type='range']::-webkit-slider-runnable-track {
      background: transparent;
      height: 100%;
    }
    input[type='range']::-moz-range-track {
      background: transparent;
      height: 100%;
    }

    input[type='range']:focus-visible::-webkit-slider-thumb {
      outline: 2px solid var(--focus-ring);
      outline-offset: 3px;
    }
    input[type='range']:focus-visible::-moz-range-thumb {
      outline: 2px solid var(--focus-ring);
      outline-offset: 3px;
    }

    :host([disabled]) {
      opacity: 0.55;
      pointer-events: none;
    }
  `;

  /** Etiqueta opcional mostrada a la izquierda del readout. */
  @property() label?: string;

  /** Mínimo del rango. */
  @property({ type: Number }) min = 0;

  /** Máximo del rango. */
  @property({ type: Number }) max = 100;

  /** Paso de incremento. */
  @property({ type: Number }) step = 1;

  /** Valor inferior actual. */
  @property({ type: Number }) low = 0;

  /** Valor superior actual. */
  @property({ type: Number }) high = 100;

  /** Prefijo del valor en el readout (p.ej. "€"). */
  @property() prefix = '';

  /** Sufijo del valor en el readout (p.ej. "%", " kg"). */
  @property() suffix = '';

  /** Deshabilita la interacción. */
  @property({ type: Boolean, reflect: true }) disabled = false;

  // Clampa low<=high respetando min/max.
  private clamp(): { low: number; high: number } {
    const lo = Math.min(Math.max(this.low, this.min), this.max);
    const hi = Math.min(Math.max(this.high, this.min), this.max);
    return { low: Math.min(lo, hi), high: Math.max(lo, hi) };
  }

  private onLow(e: Event): void {
    const v = Number((e.target as HTMLInputElement).value);
    // El thumb bajo no puede superar al alto.
    this.low = Math.min(v, this.high);
    this.high = Math.max(this.low, this.high);
    this.emit();
  }

  private onHigh(e: Event): void {
    const v = Number((e.target as HTMLInputElement).value);
    // El thumb alto no puede bajar del bajo.
    this.high = Math.max(v, this.low);
    this.low = Math.min(this.low, this.high);
    this.emit();
  }

  private emit(): void {
    const { low, high } = this.clamp();
    this.dispatchEvent(
      new CustomEvent<OkRangeDualChangeDetail>('ok-change', {
        detail: { low, high },
        bubbles: true,
        composed: true,
      }),
    );
  }

  // Formatea un valor con prefijo/sufijo.
  private fmt(v: number): string {
    return `${this.prefix}${v}${this.suffix}`;
  }

  render(): unknown {
    const { low, high } = this.clamp();
    const span = this.max - this.min || 1;
    const leftPct = ((low - this.min) / span) * 100;
    const rightPct = ((this.max - high) / span) * 100;

    return html`
      <div class="block">
        <div class="head">
          ${this.label ? html`<span class="label">${this.label}</span>` : html`<span></span>`}
          <span class="readout" aria-live="polite">${this.fmt(low)} – ${this.fmt(high)}</span>
        </div>
        <div class="range">
          <div class="track"></div>
          <div
            class="fill"
            style="left:${leftPct}%; right:${rightPct}%"
          ></div>
          <input
            type="range"
            .min=${String(this.min)}
            .max=${String(this.max)}
            .step=${String(this.step)}
            .value=${String(low)}
            ?disabled=${this.disabled}
            role="slider"
            aria-label=${(this.label ? this.label + ' ' : '') + 'mínimo'}
            aria-valuemin=${this.min}
            aria-valuemax=${this.max}
            aria-valuenow=${low}
            aria-valuetext=${this.fmt(low)}
            @input=${this.onLow}
          />
          <input
            type="range"
            .min=${String(this.min)}
            .max=${String(this.max)}
            .step=${String(this.step)}
            .value=${String(high)}
            ?disabled=${this.disabled}
            role="slider"
            aria-label=${(this.label ? this.label + ' ' : '') + 'máximo'}
            aria-valuemin=${this.min}
            aria-valuemax=${this.max}
            aria-valuenow=${high}
            aria-valuetext=${this.fmt(high)}
            @input=${this.onHigh}
          />
        </div>
      </div>
    `;
  }
}

define('ok-range-dual', OkRangeDual);

declare global {
  interface HTMLElementTagNameMap {
    'ok-range-dual': OkRangeDual;
  }
}
