import { LitElement, html, css } from 'lit';
import { property } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// ok-qty-stepper — selector de cantidad (botones -/+ con campo central editable). Ionic no trae
// un stepper numérico con clamp; este lo cubre. AUTOCONTENIDO: CSS propio en el shadow; usa
// `ion-button`/`ion-icon` NATIVOS (los registra el host). Valida y hace clamp del input a min/max.
//   • prop `value`     → number (def 0)
//   • prop `min`       → number (def 0)
//   • prop `max`       → number opcional (sin tope si no se da)
//   • prop `step`      → number (def 1)
//   • prop `disabled`  → boolean
// Eventos (bubbles + composed):
//   • `ok-change`  detail { value }

// Textos traducibles (default inglés). Pásalos desde fuera vía la prop `labels`.
export interface OkQtyStepperLabels {
  /** aria-label del botón restar (−). */
  decrement: string;
  /** aria-label del botón sumar (+). */
  increment: string;
}

const DEFAULT_LABELS: OkQtyStepperLabels = {
  decrement: 'Decrease',
  increment: 'Increase',
};

export class OkQtyStepper extends LitElement {
  static styles = css`
    :host {
      /* Vars overridable (estilo Ionic), default = cadena --ok-* -> --ion-* -> hex */
      --color: var(--ok-text, var(--ion-text-color, #1c1b17));
      --field-bg: var(--ok-surface, var(--ion-background-color, #ffffff));
      --border-color: var(--ok-border, rgba(var(--ion-text-color-rgb, 28, 27, 23), 0.18));
      --border-radius: var(--ok-radius, 8px);
      --field-width: var(--ok-qty-field-width, 3.2rem);
      --font: var(--ok-font, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif);

      /* Inline: ocupa solo lo necesario, alineado con texto circundante. */
      display: inline-flex;
      vertical-align: middle;
      color: var(--color);
      font-family: var(--font);
    }
    :host([disabled]) {
      opacity: 0.5;
      pointer-events: none;
    }

    .wrap {
      display: inline-flex;
      align-items: stretch;
      border: 1px solid var(--border-color);
      border-radius: var(--border-radius);
      overflow: hidden;
      background: var(--field-bg);
    }

    /* Botones -/+ : ion-button compactos y sin margen, encajados en la caja. */
    ion-button {
      --padding-start: 0;
      --padding-end: 0;
      --border-radius: 0;
      --box-shadow: none;
      margin: 0;
      height: auto;
      min-width: 2.1rem;
    }
    ion-button ion-icon {
      font-size: 1.1rem;
    }

    /* Campo central editable: numérico, centrado, sin spinners nativos. */
    .field {
      width: var(--field-width);
      min-width: 0;
      text-align: center;
      border: 0;
      border-left: 1px solid var(--border-color);
      border-right: 1px solid var(--border-color);
      background: transparent;
      color: inherit;
      font: inherit;
      font-size: 0.95rem;
      padding: 0.25rem 0.2rem;
      -moz-appearance: textfield;
      appearance: textfield;
    }
    .field::-webkit-outer-spin-button,
    .field::-webkit-inner-spin-button {
      -webkit-appearance: none;
      margin: 0;
    }
    .field:focus {
      outline: none;
    }
    .field:disabled {
      background: transparent;
    }
  `;

  /** Valor actual. */
  @property({ type: Number }) value = 0;
  /** Mínimo permitido. */
  @property({ type: Number }) min = 0;
  /** Máximo permitido (sin tope si es undefined). */
  @property({ type: Number }) max?: number;
  /** Incremento de cada pulsación. */
  @property({ type: Number }) step = 1;
  /** Deshabilita toda la interacción. */
  @property({ type: Boolean, reflect: true }) disabled = false;
  /** Textos traducibles (merge sobre los defaults en inglés). */
  @property({ attribute: false }) labels: Partial<OkQtyStepperLabels> = {};

  // Textos efectivos: defaults en inglés + overrides del consumidor.
  private get t(): OkQtyStepperLabels {
    return { ...DEFAULT_LABELS, ...this.labels };
  }

  // Recorta `n` al rango [min, max] respetando los límites definidos.
  private clamp(n: number): number {
    let v = n;
    if (typeof this.min === 'number' && v < this.min) v = this.min;
    if (typeof this.max === 'number' && v > this.max) v = this.max;
    return v;
  }

  // Aplica un nuevo valor (con clamp) y emite `ok-change` si cambió.
  private commit(next: number): void {
    const clamped = this.clamp(next);
    if (clamped === this.value) {
      // Reasigna por si el input mostraba un valor fuera de rango (fuerza re-render).
      this.requestUpdate();
      return;
    }
    this.value = clamped;
    this.dispatchEvent(
      new CustomEvent('ok-change', {
        detail: { value: clamped },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private decrement(): void {
    if (this.disabled) return;
    this.commit(this.value - this.step);
  }

  private increment(): void {
    if (this.disabled) return;
    this.commit(this.value + this.step);
  }

  // Valida la edición manual: parsea, ignora no-números y hace clamp.
  private onInput(e: Event): void {
    const raw = (e.target as HTMLInputElement).value;
    const parsed = Number(raw);
    if (raw === '' || Number.isNaN(parsed)) return; // espera a que termine de escribir
    this.commit(parsed);
  }

  // Al salir del campo, normaliza el texto al valor válido actual.
  private onBlur(e: Event): void {
    const input = e.target as HTMLInputElement;
    const parsed = Number(input.value);
    if (input.value === '' || Number.isNaN(parsed)) {
      input.value = String(this.value);
    } else {
      this.commit(parsed);
      input.value = String(this.value);
    }
  }

  render(): unknown {
    const atMin = typeof this.min === 'number' && this.value <= this.min;
    const atMax = typeof this.max === 'number' && this.value >= this.max;

    return html`<div class="wrap">
      <ion-button
        fill="clear"
        size="small"
        aria-label=${this.t.decrement}
        ?disabled=${this.disabled || atMin}
        @click=${() => this.decrement()}
      >
        <ion-icon slot="icon-only" name="remove"></ion-icon>
      </ion-button>
      <input
        class="field"
        type="number"
        inputmode="numeric"
        .value=${String(this.value)}
        min=${this.min}
        max=${this.max ?? ''}
        step=${this.step}
        ?disabled=${this.disabled}
        @input=${(e: Event) => this.onInput(e)}
        @change=${(e: Event) => this.onBlur(e)}
        @blur=${(e: Event) => this.onBlur(e)}
      />
      <ion-button
        fill="clear"
        size="small"
        aria-label=${this.t.increment}
        ?disabled=${this.disabled || atMax}
        @click=${() => this.increment()}
      >
        <ion-icon slot="icon-only" name="add"></ion-icon>
      </ion-button>
    </div>`;
  }
}

define('ok-qty-stepper', OkQtyStepper);

declare global {
  interface HTMLElementTagNameMap {
    'ok-qty-stepper': OkQtyStepper;
  }
}
