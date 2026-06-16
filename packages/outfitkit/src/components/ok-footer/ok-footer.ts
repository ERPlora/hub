import { LitElement, html, css } from 'lit';
import { define } from '../../base/define.js';

// ok-footer — footer web multi-columna responsive (Ionic no lo cubre; ion-footer es barra
// de app móvil). Slots:
//   • slot (default) → columnas (cada hijo es una columna; grid responsive auto-fit)
//   • slot="bottom"  → barra inferior (copyright, legal)
// Contenido por slot (light DOM) → SEO crawlable.
export class OkFooter extends LitElement {
  static styles = css`
    :host {
      --background: var(--ok-surface, var(--ion-card-background, #ffffff));
      --color: var(--ok-text, var(--ion-text-color, #1c1b17));
      --color-muted: var(--ok-muted, rgba(var(--ion-text-color-rgb, 24, 24, 27), 0.55));
      --border-color: var(--ok-border, rgba(var(--ion-text-color-rgb, 24, 24, 27), 0.12));
      --border-color-soft: var(--ok-border-soft, rgba(var(--ion-text-color-rgb, 24, 24, 27), 0.07));
      --primary-color: var(--ok-primary, var(--ion-color-primary, #3880ff));
      --max-width: var(--ok-container-max, 1140px);
      --padding: var(--ok-spacing, var(--ion-padding, 16px));
      --font: var(--ok-font, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif);

      display: block;
      background: var(--background);
      border-top: 1px solid var(--border-color);
      color: var(--color);
      font-family: var(--font);
    }
    .wrap {
      max-width: var(--max-width);
      margin-inline: auto;
      padding: 2rem var(--padding);
      display: grid;
      gap: 1.5rem;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    }
    .bottom {
      border-top: 1px solid var(--border-color-soft);
      padding: 1rem var(--padding);
      text-align: center;
      color: var(--color-muted);
      font-size: 0.85rem;
      max-width: var(--max-width);
      margin-inline: auto;
    }
    ::slotted(a) {
      color: var(--color-muted);
      text-decoration: none;
      /* Micro-interacción: transición sutil en color al hacer hover. */
      transition: background-color var(--ok-transition, 150ms ease), color var(--ok-transition, 150ms ease), border-color var(--ok-transition, 150ms ease), box-shadow var(--ok-transition, 150ms ease), transform 120ms ease;
    }
    /* Hover de enlaces solo con ratón (evita estados pegados en táctil). */
    @media (hover: hover) {
      ::slotted(a:hover) { color: var(--primary-color); }
    }
    @media (prefers-reduced-motion: reduce) {
      ::slotted(a):active { transform: none; }
    }
  `;

  render(): unknown {
    return html`
      <footer>
        <div class="wrap"><slot></slot></div>
        <div class="bottom"><slot name="bottom"></slot></div>
      </footer>
    `;
  }
}

define('ok-footer', OkFooter);

declare global {
  interface HTMLElementTagNameMap {
    'ok-footer': OkFooter;
  }
}
