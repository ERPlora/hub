import { LitElement, html, css } from 'lit';
import { property } from 'lit/decorators.js';
import { define } from '../../base/define.js';

/** Nivel/tier de la tarjeta de fidelización. */
export type OkLoyaltyTier = 'silver' | 'gold' | 'platinum' | 'brand';

/** Tamaño de la tarjeta. */
export type OkLoyaltySize = 'sm' | 'md' | 'lg';

// ok-loyalty-card — tarjeta de socio/fidelización de marca (presentacional).
// Formato apaisado 340x210, gradiente de marca a 135deg + overlays radiales de
// luz/sombra, chip EMV dibujado en CSS, número mono con tracking, valor de puntos
// y badge de tier "glass". El tier platinum añade un barrido de brillo (sheen).
export class OkLoyaltyCard extends LitElement {
  static styles = css`
    :host {
      display: block;
      width: 100%;
      /* Tokens propios estilo Ionic (overridables): --ok-* → --ion-* → hex. */
      --brand-a: var(--ok-color-primary-shade, var(--ion-color-primary-shade, #b83a12));
      --brand-b: var(--ok-color-primary, var(--ion-color-primary, #e8552a));
      --brand-fg: var(--ok-color-primary-contrast, var(--ion-color-primary-contrast, #ffffff));
      --radius: var(--ok-radius-xl, 18px);
      --shadow: var(--ok-shadow-md, 0 8px 24px rgba(0, 0, 0, 0.18));
      /* Paleta de tiers (defaults del diseño original). */
      --tier-silver-a: #6e6e74;
      --tier-silver-b: #b4b6bb;
      --tier-silver-fg: #1a1a1c;
      --tier-gold-a: #8a6418;
      --tier-gold-b: #e6c159;
      --tier-gold-fg: #2a1d05;
      --tier-platinum-a: #1f2024;
      --tier-platinum-b: #4a4d56;
      --tier-platinum-fg: #f0f1f3;
    }

    .card {
      /* Variables internas resueltas por la variante de tier. */
      --grad-a: var(--brand-a);
      --grad-b: var(--brand-b);
      --fg: var(--brand-fg);
      --w: 340px;
      --h: 210px;
      --pad: 1.25rem;
      --num-size: 1.125rem;
      --points-size: 1.5rem;

      position: relative;
      width: var(--w);
      height: var(--h);
      max-width: 100%;
      box-sizing: border-box;
      border-radius: var(--radius);
      padding: var(--pad);
      background: linear-gradient(135deg, var(--grad-a), var(--grad-b));
      color: var(--fg);
      box-shadow: var(--shadow);
      overflow: hidden;
      isolation: isolate;
      display: grid;
      grid-template-rows: auto auto 1fr auto;
      gap: 0.5rem;
      font-family: var(
        --ok-font-sans,
        var(--ion-font-family, system-ui, -apple-system, sans-serif)
      );
    }

    /* Overlays radiales de luz (arriba-derecha) y sombra (abajo-izquierda). */
    .card::before {
      content: '';
      position: absolute;
      inset: 0;
      background:
        radial-gradient(circle at 80% 0%, rgba(255, 255, 255, 0.18) 0%, transparent 45%),
        radial-gradient(circle at 0% 100%, rgba(0, 0, 0, 0.22) 0%, transparent 55%);
      z-index: -1;
    }

    .head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 0.75rem;
    }

    .brand {
      font-size: 1rem;
      font-weight: 700;
      letter-spacing: -0.01em;
      text-transform: uppercase;
    }

    /* Chip EMV dibujado en CSS. */
    .chip {
      width: 36px;
      height: 26px;
      flex: 0 0 auto;
      border-radius: 5px;
      position: relative;
      background: linear-gradient(
        135deg,
        rgba(255, 255, 255, 0.7),
        rgba(255, 255, 255, 0.35)
      );
      box-shadow: inset 0 0 0 1px rgba(0, 0, 0, 0.25);
    }
    .chip::before,
    .chip::after {
      content: '';
      position: absolute;
      inset: 4px;
      border: 1px solid rgba(0, 0, 0, 0.35);
      border-radius: 2px;
    }
    .chip::after {
      inset: 8px 6px;
      border-top: 0;
      border-bottom: 0;
    }

    .num {
      font-family: var(--ok-font-mono, ui-monospace, 'SFMono-Regular', Menlo, monospace);
      font-size: var(--num-size);
      font-weight: 600;
      letter-spacing: 0.12em;
      word-spacing: 0.25em;
      color: var(--fg);
      text-shadow: 0 1px 1px rgba(0, 0, 0, 0.3);
      align-self: center;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .points {
      display: grid;
      gap: 2px;
    }
    .points-value {
      font-size: var(--points-size);
      font-weight: 700;
      letter-spacing: -0.02em;
      font-variant-numeric: tabular-nums;
      line-height: 1;
    }
    .points-label {
      font-size: 0.625rem;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      opacity: 0.85;
    }

    .row {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 0.75rem;
      align-items: end;
    }

    .name {
      font-size: 1rem;
      font-weight: 600;
      letter-spacing: -0.01em;
      text-transform: uppercase;
    }

    /* Badge de tier "glass". */
    .tier-badge {
      display: inline-flex;
      align-items: center;
      gap: 0.25rem;
      margin-top: 0.25rem;
      padding: 4px 0.5rem;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.22);
      border: 1px solid rgba(255, 255, 255, 0.3);
      font-size: 0.625rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      backdrop-filter: blur(6px);
      -webkit-backdrop-filter: blur(6px);
    }

    .expires {
      font-family: var(--ok-font-mono, ui-monospace, 'SFMono-Regular', Menlo, monospace);
      font-size: 0.5625rem;
      opacity: 0.85;
      letter-spacing: 0.06em;
      text-align: right;
    }
    .expires b {
      display: block;
      font-size: 0.75rem;
      font-weight: 600;
      letter-spacing: 0.04em;
      margin-top: 2px;
    }

    /* ── Variantes de tier ── */
    .card.silver {
      --grad-a: var(--tier-silver-a);
      --grad-b: var(--tier-silver-b);
      --fg: var(--tier-silver-fg);
    }
    .card.silver .tier-badge {
      background: rgba(0, 0, 0, 0.12);
      border-color: rgba(0, 0, 0, 0.22);
    }
    .card.gold {
      --grad-a: var(--tier-gold-a);
      --grad-b: var(--tier-gold-b);
      --fg: var(--tier-gold-fg);
    }
    .card.gold .tier-badge {
      background: rgba(0, 0, 0, 0.14);
      border-color: rgba(0, 0, 0, 0.24);
    }
    .card.platinum {
      --grad-a: var(--tier-platinum-a);
      --grad-b: var(--tier-platinum-b);
      --fg: var(--tier-platinum-fg);
    }
    /* platinum: barrido de brillo (sheen) animado. */
    .card.platinum::after {
      content: '';
      position: absolute;
      inset: 0;
      background: linear-gradient(
        115deg,
        transparent 35%,
        rgba(255, 255, 255, 0.18) 50%,
        transparent 65%
      );
      pointer-events: none;
      z-index: -1;
      transform: translateX(-100%);
      animation: ok-loyalty-sheen 4.5s ease-in-out infinite;
    }
    @keyframes ok-loyalty-sheen {
      0%,
      60% {
        transform: translateX(-100%);
      }
      100% {
        transform: translateX(100%);
      }
    }
    @media (prefers-reduced-motion: reduce) {
      .card.platinum::after {
        animation: none;
        transform: none;
      }
    }
    .card.brand {
      --grad-a: var(--brand-a);
      --grad-b: var(--brand-b);
      --fg: var(--brand-fg);
    }

    /* ── Tamaños ── */
    .card.sm {
      --w: 280px;
      --h: 172px;
      --pad: 1rem;
      --num-size: 1rem;
      --points-size: 1.25rem;
    }
    .card.lg {
      --w: 400px;
      --h: 250px;
      --pad: 1.5rem;
      --num-size: 1.25rem;
      --points-size: 1.875rem;
    }
  `;

  /** Nombre del titular de la tarjeta. */
  @property() holder?: string;

  /** Número de socio/tarjeta (se renderiza en mono). */
  @property() number?: string;

  /** Puntos de fidelización (string o número, se muestra tal cual). */
  @property() points?: string;

  /** Etiqueta bajo el valor de puntos. */
  @property({ attribute: 'points-label' }) pointsLabel = 'Reward points';

  /** Nombre de marca/programa en la cabecera. */
  @property() brand = '';

  /** Nivel/tier visual. */
  @property() tier: OkLoyaltyTier = 'brand';

  /** Etiqueta del badge de tier (por defecto = el tier capitalizado). */
  @property({ attribute: 'tier-label' }) tierLabel?: string;

  /** Texto previo al valor "miembro desde / caduca". */
  @property({ attribute: 'meta-label' }) metaLabel = 'Member since';

  /** Valor de la meta (fecha de alta o caducidad, ej. "03 / 24"). */
  @property({ attribute: 'meta-value' }) metaValue?: string;

  /** Tamaño de la tarjeta. */
  @property() size: OkLoyaltySize = 'md';

  private get badgeText(): string {
    if (this.tierLabel) return this.tierLabel;
    return this.tier.charAt(0).toUpperCase() + this.tier.slice(1);
  }

  render(): unknown {
    const classes = ['card', this.tier, this.size].join(' ');
    return html`
      <div class=${classes} role="group" aria-label="Tarjeta de fidelización">
        <div class="head">
          <div class="brand">${this.brand}</div>
          <div class="chip" aria-hidden="true"></div>
        </div>

        ${this.number ? html`<div class="num">${this.number}</div>` : html`<div></div>`}

        <div class="points">
          ${this.points != null && this.points !== ''
            ? html`<span class="points-value">${this.points}</span>`
            : null}
          ${this.pointsLabel
            ? html`<span class="points-label">${this.pointsLabel}</span>`
            : null}
        </div>

        <div class="row">
          <div>
            ${this.holder ? html`<div class="name">${this.holder}</div>` : null}
            <span class="tier-badge">${this.badgeText}</span>
          </div>
          ${this.metaValue
            ? html`<div class="expires">
                ${this.metaLabel}<b>${this.metaValue}</b>
              </div>`
            : null}
        </div>
      </div>
    `;
  }
}

define('ok-loyalty-card', OkLoyaltyCard);

declare global {
  interface HTMLElementTagNameMap {
    'ok-loyalty-card': OkLoyaltyCard;
  }
}
