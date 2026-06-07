import { LitElement, html, css } from 'lit';
import { property } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// ok-navbar — barra de navegación web responsive con BURGER en móvil (el hueco que Ionic
// no cubre: ion-menu es un drawer de app, no una navbar de landing). Slots:
//   • slot="brand"   → logo / nombre (izquierda)
//   • slot (default) → enlaces de navegación (centro/derecha; se colapsan en móvil)
//   • slot="actions" → CTAs (login, "Empezar"); visibles siempre
// Contenido por slot (light DOM) → SEO crawlable. Atributos: `sticky`, `open`.
export class OkNavbar extends LitElement {
  static styles = css`
    :host {
      /* Vars overridable (estilo Ionic), default = cadena --ok-* → --ion-* → hex */
      --background: var(--ok-surface, var(--ion-card-background, #ffffff));
      --color: var(--ok-text, var(--ion-text-color, #1c1b17));
      --border-color: var(--ok-border, rgba(var(--ion-text-color-rgb, 24, 24, 27), 0.12));
      --border-color-soft: var(--ok-border-soft, rgba(var(--ion-text-color-rgb, 24, 24, 27), 0.07));
      --primary-color: var(--ok-primary, var(--ion-color-primary, #3880ff));
      --max-width: var(--ok-container-max, 1140px);
      --padding: var(--ok-spacing, var(--ion-padding, 16px));
      --font: var(--ok-font, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif);

      display: block;
      background: var(--background);
      border-bottom: 1px solid var(--border-color);
      color: var(--color);
      font-family: var(--font);
    }
    :host([sticky]) { position: sticky; top: 0; z-index: 50; }
    .bar {
      position: relative;
      max-width: var(--max-width);
      margin-inline: auto;
      display: flex;
      align-items: center;
      gap: 1rem;
      padding: 0.6rem var(--padding);
    }
    .brand { display: flex; align-items: center; gap: 0.5rem; font-weight: 700; }
    .spacer { flex: 1; }
    .links { display: flex; align-items: center; gap: 1.25rem; }
    .actions { display: flex; align-items: center; gap: 0.5rem; }
    ::slotted(a) { color: var(--color); text-decoration: none; font-size: 0.95rem; }
    ::slotted(a:hover) { color: var(--primary-color); }
    .burger {
      display: none;
      background: none;
      border: 0;
      cursor: pointer;
      padding: 0.5rem;
      color: var(--color);
    }
    .burger span { display: block; width: 22px; height: 2px; background: currentColor; border-radius: 2px; position: relative; }
    .burger span::before, .burger span::after { content: ''; position: absolute; left: 0; width: 22px; height: 2px; background: currentColor; border-radius: 2px; }
    .burger span::before { top: -7px; }
    .burger span::after { top: 7px; }
    @media (max-width: 800px) {
      .burger { display: block; }
      .links {
        display: none;
        position: absolute;
        left: 0;
        right: 0;
        top: 100%;
        flex-direction: column;
        align-items: stretch;
        gap: 0;
        background: var(--background);
        border-bottom: 1px solid var(--border-color);
        padding: 0.5rem var(--padding);
      }
      :host([open]) .links { display: flex; }
      :host([open]) ::slotted(a) { padding: 0.6rem 0; border-top: 1px solid var(--border-color-soft); }
    }
  `;

  /** Fija la navbar arriba al hacer scroll. */
  @property({ type: Boolean, reflect: true }) sticky = false;
  /** Estado del panel móvil (reflejado para el selector :host([open])). */
  @property({ type: Boolean, reflect: true }) open = false;

  private toggle(): void {
    this.open = !this.open;
  }

  render(): unknown {
    return html`
      <nav class="bar">
        <div class="brand"><slot name="brand"></slot></div>
        <div class="spacer"></div>
        <div class="links"><slot></slot></div>
        <div class="actions"><slot name="actions"></slot></div>
        <button class="burger" aria-label="Menú" aria-expanded=${this.open ? 'true' : 'false'} @click=${this.toggle}>
          <span></span>
        </button>
      </nav>
    `;
  }
}

define('ok-navbar', OkNavbar);

declare global {
  interface HTMLElementTagNameMap {
    'ok-navbar': OkNavbar;
  }
}
