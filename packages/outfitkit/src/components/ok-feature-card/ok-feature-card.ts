import { LitElement, html, css } from 'lit';
import { property } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// ok-feature-card — tarjeta de característica para marketing: icono + (eyebrow) + título +
// descripción (slot default). Eleva al hover. Si se pasa `href`, toda la tarjeta es enlace.
// Reemplaza el patrón <ion-card> manual de la landing.
//
//   <ok-feature-card icon="lucide:box" eyebrow="01 · POS" heading="Punto de venta">
//     Cobra, factura y controla caja desde cualquier dispositivo.
//   </ok-feature-card>
export class OkFeatureCard extends LitElement {
  static styles = css`
    :host {
      display: block;
      width: 100%;
      height: 100%;
      --color: var(--ok-text, var(--ion-text-color, #18181b));
      --muted: var(--ok-muted, rgba(var(--ion-text-color-rgb, 24, 24, 27), 0.62));
      --surface: var(--ok-surface, var(--ion-card-background, var(--ion-background-color, #fff)));
      --border: var(--ok-border, rgba(var(--ion-text-color-rgb, 24, 24, 27), 0.1));
      --radius: var(--ok-radius, 16px);
      --accent: var(--ion-color-primary, #1496d6);
      font-family: var(--ok-font, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif);
    }
    .card {
      box-sizing: border-box;
      height: 100%;
      display: flex;
      flex-direction: column;
      gap: 0.55rem;
      padding: clamp(1.2rem, 2vw, 1.6rem);
      color: var(--color);
      text-decoration: none;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      position: relative;
      overflow: hidden;
      transition: transform var(--ok-transition, 160ms ease), box-shadow var(--ok-transition, 160ms ease),
        border-color var(--ok-transition, 160ms ease);
    }
    /* Línea de acento superior que aparece al hover */
    .card::before {
      content: '';
      position: absolute;
      inset: 0 0 auto 0;
      height: 3px;
      background: linear-gradient(90deg, var(--accent), color-mix(in oklab, var(--accent) 30%, transparent));
      transform: scaleX(0);
      transform-origin: left;
      transition: transform var(--ok-transition, 200ms ease);
    }
    :host([glass]) .card {
      background: color-mix(in oklab, var(--surface) 62%, transparent);
      -webkit-backdrop-filter: blur(14px) saturate(1.4);
      backdrop-filter: blur(14px) saturate(1.4);
      border-color: color-mix(in oklab, var(--color) 12%, transparent);
    }
    .card:hover {
      transform: translateY(-4px);
      border-color: color-mix(in oklab, var(--accent) 40%, var(--border));
      box-shadow: 0 22px 48px -26px color-mix(in oklab, var(--accent) 60%, transparent);
    }
    .card:hover::before { transform: scaleX(1); }
    .ico {
      display: inline-grid;
      place-items: center;
      width: 2.75rem;
      height: 2.75rem;
      border-radius: 13px;
      color: var(--accent);
      background: color-mix(in oklab, var(--accent) 13%, transparent);
      font-size: 1.4rem;
      margin-bottom: 0.35rem;
    }
    .ico ::slotted(img),
    .ico img { width: 1.4rem; height: 1.4rem; }
    /* Glifo via máscara CSS sobre la SVG del API de Iconify (funciona en Shadow DOM). */
    .glyph {
      width: 1.5rem;
      height: 1.5rem;
      background-color: currentColor;
      -webkit-mask: var(--u) center / contain no-repeat;
      mask: var(--u) center / contain no-repeat;
    }
    .eyebrow {
      font-size: 0.7rem;
      font-weight: 600;
      letter-spacing: 0.05em;
      text-transform: uppercase;
      color: var(--muted);
    }
    .title {
      margin: 0;
      font-size: 1.15rem;
      font-weight: 620;
      letter-spacing: -0.015em;
      line-height: 1.25;
    }
    .desc {
      color: var(--muted);
      font-size: 0.92rem;
      line-height: 1.55;
    }
    ::slotted(*) { margin: 0; }
  `;

  /** Icono (nombre iconify, p.ej. "lucide:box"). Para img/otro usa slot="icon". */
  @property() icon?: string;
  /** Eyebrow opcional (numeración, categoría…). */
  @property() eyebrow?: string;
  /** Título de la característica. */
  @property() heading?: string;
  /** Si se pasa, la tarjeta entera es un enlace. */
  @property() href?: string;
  /** Cristal esmerilado. */
  @property({ type: Boolean, reflect: true }) glass = false;

  /** "lucide:box" → "https://api.iconify.design/lucide/box.svg" (prefijo:nombre → prefijo/nombre). */
  private iconUrl(name: string): string {
    const i = name.indexOf(':');
    const prefix = i === -1 ? 'lucide' : name.slice(0, i);
    const icon = i === -1 ? name : name.slice(i + 1);
    return `https://api.iconify.design/${prefix}/${icon}.svg`;
  }

  private inner(): unknown {
    return html`
      ${this.icon
        ? html`<span class="ico"><i class="glyph" style="--u:url('${this.iconUrl(this.icon)}')"></i></span>`
        : html`<span class="ico"><slot name="icon"></slot></span>`}
      ${this.eyebrow ? html`<span class="eyebrow">${this.eyebrow}</span>` : null}
      ${this.heading ? html`<h3 class="title">${this.heading}</h3>` : null}
      <div class="desc"><slot></slot></div>
    `;
  }

  render(): unknown {
    return this.href
      ? html`<a class="card" href=${this.href}>${this.inner()}</a>`
      : html`<div class="card">${this.inner()}</div>`;
  }
}

define('ok-feature-card', OkFeatureCard);

declare global {
  interface HTMLElementTagNameMap {
    'ok-feature-card': OkFeatureCard;
  }
}
