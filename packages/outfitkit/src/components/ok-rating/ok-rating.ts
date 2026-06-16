import { LitElement, html, css } from 'lit';
import { property, state } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// ok-rating — valoración por estrellas (inline). El hover previsualiza el valor y el click lo fija;
// con `allow-half` se permiten medias estrellas (la mitad izquierda de cada estrella = .5).
// AUTOCONTENIDO: CSS propio en el shadow; solo usa `ion-icon` (lo registra el host) con los iconos
// star / star-half / star-outline. Color por defecto = warning de Ionic.
//   • prop `value`       → valor actual (number)
//   • prop `max`         → número de estrellas (def 5)
//   • prop `readonly`    → solo lectura (sin hover ni click)
//   • prop `allow-half`  → permite medias estrellas
// Eventos (bubbles + composed):
//   • `ok-change`  detail { value }

// Textos traducibles (default inglés). Pásalos desde fuera vía la prop `labels`.
export interface OkRatingLabels {
  /** aria-label de cada estrella / del grupo. Recibe el valor y el máximo. */
  starLabel: (value: number, max: number) => string;
}

const DEFAULT_LABELS: OkRatingLabels = {
  starLabel: (value, max) => `${value} of ${max}`,
};

export class OkRating extends LitElement {
  static styles = css`
    :host {
      /* Vars overridable (estilo Ionic), default = cadena --ok-* → --ion-* → hex */
      --color: var(--ok-warning, var(--ion-color-warning, #ffc409));
      --color-empty: var(--ok-border-soft, rgba(var(--ion-text-color-rgb, 28, 27, 23), 0.25));
      --size: var(--ok-rating-size, 1.5rem);
      --gap: var(--ok-rating-gap, 0.15rem);

      display: inline-flex;
      align-items: center;
      gap: var(--gap);
      line-height: 1;
    }
    /* Cada estrella es un botón clicable (o estático en readonly). */
    .star {
      flex: 0 0 auto;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      padding: 0;
      margin: 0;
      border: 0;
      background: none;
      color: var(--color-empty);
      cursor: pointer;
      font-size: var(--size);
      transition: background-color var(--ok-transition, 150ms ease),
        color var(--ok-transition, 150ms ease),
        border-color var(--ok-transition, 150ms ease),
        box-shadow var(--ok-transition, 150ms ease), transform 120ms ease;
    }
    .star.filled {
      color: var(--color);
    }
    @media (hover: hover) {
      .star:not(.readonly):hover {
        transform: scale(1.12);
      }
    }
    .star:not(.readonly):active {
      transform: scale(var(--ok-press-scale, 0.97));
    }
    :host([readonly]) .star,
    .star.readonly {
      cursor: default;
    }
    @media (prefers-reduced-motion: reduce) {
      .star:not(.readonly):hover,
      .star:not(.readonly):active {
        transform: none;
      }
    }
    ion-icon {
      pointer-events: none;
    }
    /* Zonas izquierda/derecha para medias estrellas (allow-half). */
    .star.half-mode {
      position: relative;
    }
    .half-zone {
      position: absolute;
      top: 0;
      bottom: 0;
      width: 50%;
      cursor: pointer;
    }
    .half-zone.left {
      left: 0;
    }
    .half-zone.right {
      right: 0;
    }
  `;

  /** Valor actual de la valoración. */
  @property({ type: Number }) value = 0;
  /** Número total de estrellas. */
  @property({ type: Number }) max = 5;
  /** Solo lectura: sin hover ni interacción. */
  @property({ type: Boolean, reflect: true }) readonly = false;
  /** Permite seleccionar medias estrellas. */
  @property({ type: Boolean, attribute: 'allow-half' }) allowHalf = false;
  /** Textos traducibles (merge sobre los defaults en inglés). */
  @property({ attribute: false }) labels: Partial<OkRatingLabels> = {};

  // Textos efectivos: defaults en inglés + overrides del consumidor.
  private get t(): OkRatingLabels {
    return { ...DEFAULT_LABELS, ...this.labels };
  }

  // Valor previsualizado por hover (null = sin hover, se muestra `value`).
  @state() private hoverValue: number | null = null;

  // Valor efectivo a pintar: el de hover si lo hay, si no el real.
  private get displayValue(): number {
    return this.hoverValue ?? this.value;
  }

  // Fija el valor y emite `ok-change` (solo si cambia y no es readonly).
  private setValue(next: number): void {
    if (this.readonly) return;
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

  private onEnter(v: number): void {
    if (this.readonly) return;
    this.hoverValue = v;
  }

  private onLeave(): void {
    this.hoverValue = null;
  }

  // Devuelve el icono apropiado para la estrella `index` (1-based) según el valor mostrado.
  private iconFor(index: number): string {
    const v = this.displayValue;
    if (v >= index) return 'star';
    if (this.allowHalf && v >= index - 0.5) return 'star-half';
    return 'star-outline';
  }

  // Render de una estrella con medias (zonas izquierda = .5, derecha = entero).
  private renderHalfStar(index: number): unknown {
    const filled = this.displayValue >= index - 0.5;
    return html`<span class=${`star half-mode ${filled ? 'filled' : ''}`}>
      <ion-icon .name=${this.iconFor(index)}></ion-icon>
      ${this.readonly
        ? ''
        : html`<span
              class="half-zone left"
              @mouseenter=${() => this.onEnter(index - 0.5)}
              @click=${() => this.setValue(index - 0.5)}
            ></span>
            <span
              class="half-zone right"
              @mouseenter=${() => this.onEnter(index)}
              @click=${() => this.setValue(index)}
            ></span>`}
    </span>`;
  }

  // Render de una estrella entera (sin medias).
  private renderFullStar(index: number): unknown {
    const filled = this.displayValue >= index;
    return html`<button
      type="button"
      class=${`star ${filled ? 'filled' : ''} ${this.readonly ? 'readonly' : ''}`}
      aria-label=${this.t.starLabel(index, this.max)}
      ?disabled=${this.readonly}
      @mouseenter=${() => this.onEnter(index)}
      @click=${() => this.setValue(index)}
    >
      <ion-icon .name=${this.iconFor(index)}></ion-icon>
    </button>`;
  }

  render(): unknown {
    const stars = Array.from({ length: Math.max(0, this.max) }, (_, i) => i + 1);
    return html`<span
      role="img"
      aria-label=${this.t.starLabel(this.value, this.max)}
      @mouseleave=${() => this.onLeave()}
    >
      ${stars.map((i) => (this.allowHalf ? this.renderHalfStar(i) : this.renderFullStar(i)))}
    </span>`;
  }
}

define('ok-rating', OkRating);

declare global {
  interface HTMLElementTagNameMap {
    'ok-rating': OkRating;
  }
}
