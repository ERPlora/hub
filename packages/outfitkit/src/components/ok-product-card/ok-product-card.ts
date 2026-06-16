import { LitElement, html, css } from 'lit';
import { property } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// ok-product-card — tarjeta de producto/módulo del catálogo (marketplace). Icono + categoría +
// nombre + descripción (slot) + badge opcional (precio/estado) + precio. Si hay `href`, toda la
// tarjeta es enlace y muestra una flecha de "ir" al hover.
//
//   <ok-product-card icon="lucide:boxes" category="Inventario" name="WMS multi-almacén"
//                    badge="Premium" price="€12/mes" href="/modules/wms">
//     Gestiona ubicaciones, lotes y picking en varios almacenes.
//   </ok-product-card>
export class OkProductCard extends LitElement {
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
      gap: 0.45rem;
      padding: clamp(1.1rem, 2vw, 1.5rem);
      color: var(--color);
      text-decoration: none;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      position: relative;
      transition: transform var(--ok-transition, 160ms ease), box-shadow var(--ok-transition, 160ms ease),
        border-color var(--ok-transition, 160ms ease);
    }
    .card:hover {
      transform: translateY(-3px);
      border-color: color-mix(in oklab, var(--accent) 40%, var(--border));
      box-shadow: 0 18px 40px -24px color-mix(in oklab, var(--accent) 55%, transparent);
    }
    .top {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 0.5rem;
    }
    .head {
      display: flex;
      align-items: center;
      gap: 0.6rem;
    }
    .ico {
      display: inline-grid;
      place-items: center;
      width: 2.25rem;
      height: 2.25rem;
      border-radius: 11px;
      color: var(--accent);
      background: color-mix(in oklab, var(--accent) 13%, transparent);
      font-size: 1.15rem;
      flex: 0 0 auto;
    }
    .ico img { width: 1.2rem; height: 1.2rem; }
    /* Glifo via máscara CSS sobre la SVG del API de Iconify (funciona en Shadow DOM). */
    .glyph {
      width: 1.25rem;
      height: 1.25rem;
      background-color: currentColor;
      -webkit-mask: var(--u) center / contain no-repeat;
      mask: var(--u) center / contain no-repeat;
    }
    .cat {
      font-size: 0.68rem;
      font-weight: 600;
      letter-spacing: 0.05em;
      text-transform: uppercase;
      color: var(--muted);
    }
    .badge {
      padding: 0.2rem 0.55rem;
      border-radius: 999px;
      font-size: 0.66rem;
      font-weight: 700;
      letter-spacing: 0.02em;
      text-transform: uppercase;
      color: var(--accent);
      background: color-mix(in oklab, var(--accent) 14%, transparent);
      white-space: nowrap;
    }
    .name {
      margin: 0.3rem 0 0;
      font-size: 1.05rem;
      font-weight: 620;
      letter-spacing: -0.01em;
      line-height: 1.25;
    }
    .desc {
      color: var(--muted);
      font-size: 0.88rem;
      line-height: 1.5;
      flex: 1;
    }
    .foot {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-top: 0.6rem;
    }
    .price { font-weight: 650; font-size: 0.92rem; }
    .go {
      color: var(--accent);
      font-size: 1.05rem;
      opacity: 0;
      transform: translateX(-4px);
      transition: opacity var(--ok-transition, 160ms ease), transform var(--ok-transition, 160ms ease);
    }
    .card:hover .go { opacity: 1; transform: none; }
    ::slotted(*) { margin: 0; }
  `;

  /** Icono (iconify) o usa slot="icon" para una <img>. */
  @property() icon?: string;
  /** Categoría / unidad funcional. */
  @property() category?: string;
  /** Nombre del producto/módulo. */
  @property() name?: string;
  /** Badge (precio/estado, p.ej. "Premium" o "Incluido"). */
  @property() badge?: string;
  /** Precio mostrado en el pie. */
  @property() price?: string;
  /** Enlace de la tarjeta. */
  @property() href?: string;

  /** "lucide:box" → "https://api.iconify.design/lucide/box.svg". */
  private iconUrl(name: string): string {
    const i = name.indexOf(':');
    const prefix = i === -1 ? 'lucide' : name.slice(0, i);
    const icon = i === -1 ? name : name.slice(i + 1);
    return `https://api.iconify.design/${prefix}/${icon}.svg`;
  }

  private inner(): unknown {
    return html`
      <div class="top">
        <div class="head">
          ${this.icon
            ? html`<span class="ico"><i class="glyph" style="--u:url('${this.iconUrl(this.icon)}')"></i></span>`
            : html`<span class="ico"><slot name="icon"></slot></span>`}
          ${this.category ? html`<span class="cat">${this.category}</span>` : null}
        </div>
        ${this.badge ? html`<span class="badge">${this.badge}</span>` : null}
      </div>
      ${this.name ? html`<h3 class="name">${this.name}</h3>` : null}
      <div class="desc"><slot></slot></div>
      ${this.price || this.href
        ? html`<div class="foot">
            <span class="price">${this.price ?? ''}</span>
            ${this.href
              ? html`<svg class="go" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14M13 6l6 6-6 6" /></svg>`
              : null}
          </div>`
        : null}
    `;
  }

  render(): unknown {
    return this.href
      ? html`<a class="card" href=${this.href}>${this.inner()}</a>`
      : html`<div class="card">${this.inner()}</div>`;
  }
}

define('ok-product-card', OkProductCard);

declare global {
  interface HTMLElementTagNameMap {
    'ok-product-card': OkProductCard;
  }
}
