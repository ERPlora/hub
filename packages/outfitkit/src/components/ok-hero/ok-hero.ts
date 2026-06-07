import { LitElement, html, css } from 'lit';
import { define } from '../../base/define.js';

// ok-hero — sección hero de marketing. Slots:
//   • slot="title"    → titular (pon un <h1> dentro → SEO)
//   • slot="subtitle" → subtítulo
//   • slot="actions"  → CTAs
//   • slot (default)  → media / contenido extra
// Contenido por slot (light DOM) → SEO crawlable.
export class OkHero extends LitElement {
  static styles = css`
    :host {
      --color: var(--ok-text, var(--ion-text-color, #1c1b17));
      --color-muted: var(--ok-muted, rgba(var(--ion-text-color-rgb, 24, 24, 27), 0.55));
      --max-width: var(--ok-container-max, 1140px);
      --padding: var(--ok-spacing, var(--ion-padding, 16px));
      --font: var(--ok-font, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif);

      display: block;
      color: var(--color);
      font-family: var(--font);
    }
    .h {
      max-width: var(--max-width);
      margin-inline: auto;
      padding: clamp(2rem, 6vw, 5rem) var(--padding);
      display: grid;
      gap: 1rem;
    }
    ::slotted([slot='title']) { font-size: clamp(1.8rem, 4vw, 3rem); line-height: 1.1; margin: 0; }
    ::slotted([slot='subtitle']) { font-size: clamp(1rem, 2vw, 1.25rem); color: var(--color-muted); margin: 0; max-width: 42ch; }
    .actions { display: flex; gap: 0.75rem; flex-wrap: wrap; margin-top: 0.5rem; }
  `;

  render(): unknown {
    return html`
      <section class="h">
        <slot name="title"></slot>
        <slot name="subtitle"></slot>
        <div class="actions"><slot name="actions"></slot></div>
        <slot></slot>
      </section>
    `;
  }
}

define('ok-hero', OkHero);

declare global {
  interface HTMLElementTagNameMap {
    'ok-hero': OkHero;
  }
}
