import { LitElement, html, css } from 'lit';
import { property } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// ok-pricing-card — tarjeta de plan/precio. Nombre, precio + periodo, descripción, lista de
// features y CTA (slot="cta" para un <ion-button>). `featured` la destaca con borde de marca
// y badge flotante. Las features se pasan como prop array `.features` (o slot default con un
// <ul>). Pensada para una rejilla de planes.
//
//   <ok-pricing-card name="Pro" price="€49" period="/ mes" .features=${[...]} featured badge="Popular">
//     <ion-button slot="cta" expand="block" href="/signup">Empezar</ion-button>
//   </ok-pricing-card>

// Textos i18n (default inglés). Pásalos desde fuera con `.labels`.
export interface OkPricingCardLabels {
  /** Texto por defecto del badge cuando `featured` y no se pasa `badge`. */
  popular: string;
}

const DEFAULT_LABELS: OkPricingCardLabels = {
  popular: 'Popular',
};

export class OkPricingCard extends LitElement {
  static styles = css`
    :host {
      display: block;
      width: 100%;
      height: 100%;
      --color: var(--ok-text, var(--ion-text-color, #18181b));
      --muted: var(--ok-muted, rgba(var(--ion-text-color-rgb, 24, 24, 27), 0.62));
      --surface: var(--ok-surface, var(--ion-card-background, var(--ion-background-color, #fff)));
      --border: var(--ok-border, rgba(var(--ion-text-color-rgb, 24, 24, 27), 0.1));
      --radius: var(--ok-radius, 18px);
      --primary: var(--ion-color-primary, #1496d6);
      --success: var(--ion-color-success, #2dd36f);
      font-family: var(--ok-font, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif);
    }
    .card {
      box-sizing: border-box;
      height: 100%;
      display: flex;
      flex-direction: column;
      padding: clamp(1.4rem, 2.5vw, 2rem);
      color: var(--color);
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      position: relative;
      transition: transform var(--ok-transition, 160ms ease), box-shadow var(--ok-transition, 160ms ease);
    }
    :host([featured]) .card {
      border: 1.5px solid color-mix(in oklab, var(--primary) 70%, transparent);
      box-shadow: 0 24px 60px -30px color-mix(in oklab, var(--primary) 65%, transparent);
      background: linear-gradient(180deg, color-mix(in oklab, var(--primary) 6%, var(--surface)), var(--surface));
    }
    .card:hover { transform: translateY(-4px); }
    .badge {
      position: absolute;
      top: -0.8rem;
      left: 50%;
      transform: translateX(-50%);
      padding: 0.3rem 0.85rem;
      border-radius: 999px;
      font-size: 0.7rem;
      font-weight: 700;
      letter-spacing: 0.03em;
      text-transform: uppercase;
      color: var(--ion-color-primary-contrast, #fff);
      background: var(--primary);
      box-shadow: 0 6px 16px -6px color-mix(in oklab, var(--primary) 80%, transparent);
      white-space: nowrap;
    }
    .name {
      font-size: 0.72rem;
      font-weight: 700;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      color: var(--muted);
    }
    :host([featured]) .name { color: var(--primary); }
    .price {
      display: flex;
      align-items: baseline;
      gap: 0.35rem;
      margin-top: 0.4rem;
    }
    .price .amount {
      font-size: clamp(2rem, 1.4rem + 2vw, 2.6rem);
      font-weight: 700;
      letter-spacing: -0.03em;
      line-height: 1;
    }
    .price .period { font-size: 0.95rem; color: var(--muted); }
    .desc {
      margin-top: 0.6rem;
      color: var(--muted);
      font-size: 0.92rem;
      line-height: 1.5;
    }
    ul {
      list-style: none;
      margin: 1.25rem 0 0;
      padding: 1.25rem 0 0;
      border-top: 1px solid color-mix(in oklab, var(--color) 9%, transparent);
      display: flex;
      flex-direction: column;
      gap: 0.65rem;
      flex: 1;
    }
    li {
      display: flex;
      gap: 0.55rem;
      align-items: flex-start;
      font-size: 0.92rem;
      line-height: 1.4;
    }
    li .check {
      flex: 0 0 auto;
      width: 1.15rem;
      height: 1.15rem;
      margin-top: 0.05rem;
      display: grid;
      place-items: center;
      border-radius: 999px;
      color: var(--success);
      background: color-mix(in oklab, var(--success) 16%, transparent);
      font-size: 0.7rem;
      font-weight: 700;
    }
    .cta { margin-top: 1.4rem; }
    ::slotted([slot='cta']) { width: 100%; }
  `;

  /** Nombre del plan. */
  @property() name?: string;
  /** Precio (ya formateado, p.ej. "€49"). */
  @property() price?: string;
  /** Periodo, p.ej. "/ mes". */
  @property() period = '';
  /** Descripción corta. */
  @property() description?: string;
  /** Lista de características (texto). Alternativa: slot default con un <ul>. */
  @property({ attribute: false }) features: string[] = [];
  /** Plan destacado (borde de marca + badge). */
  @property({ type: Boolean, reflect: true }) featured = false;
  /** Texto del badge flotante (def "Popular" si featured y sin texto). */
  @property() badge?: string;

  /** Textos traducibles (merge sobre los defaults en inglés). */
  @property({ attribute: false }) labels: Partial<OkPricingCardLabels> = {};

  private get t(): OkPricingCardLabels {
    return { ...DEFAULT_LABELS, ...this.labels };
  }

  render(): unknown {
    const badgeText = this.badge ?? (this.featured ? this.t.popular : '');
    return html`
      <div class="card">
        ${badgeText ? html`<span class="badge">${badgeText}</span>` : null}
        ${this.name ? html`<div class="name">${this.name}</div>` : null}
        ${this.price
          ? html`<div class="price">
              <span class="amount">${this.price}</span>
              ${this.period ? html`<span class="period">${this.period}</span>` : null}
            </div>`
          : null}
        ${this.description ? html`<p class="desc">${this.description}</p>` : null}
        ${this.features.length
          ? html`<ul>
              ${this.features.map((f) => html`<li><span class="check">✓</span><span>${f}</span></li>`)}
            </ul>`
          : html`<slot></slot>`}
        <div class="cta"><slot name="cta"></slot></div>
      </div>
    `;
  }
}

define('ok-pricing-card', OkPricingCard);

declare global {
  interface HTMLElementTagNameMap {
    'ok-pricing-card': OkPricingCard;
  }
}
