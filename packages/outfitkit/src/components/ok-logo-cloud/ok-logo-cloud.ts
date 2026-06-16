import { LitElement, html, css } from 'lit';
import { property } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// ok-logo-cloud — banda de logos de clientes / "trusted by" (prueba social). Acepta los logos
// como slot (imgs o texto) y los muestra en rejilla atenuada (grayscale → color al hover). Con
// `marquee` desplaza la fila en bucle (CSS, sin JS). `label` opcional encima.
//
//   <ok-logo-cloud label="Usado por equipos de">
//     <img src="/a.svg" alt="A"><img src="/b.svg" alt="B"> …
//   </ok-logo-cloud>
export class OkLogoCloud extends LitElement {
  static styles = css`
    :host {
      display: block;
      width: 100%;
      --muted: var(--ok-muted, rgba(var(--ion-text-color-rgb, 24, 24, 27), 0.55));
      font-family: var(--ok-font, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif);
    }
    .label {
      text-align: center;
      font-size: 0.75rem;
      font-weight: 600;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--muted);
      margin-bottom: 1.5rem;
    }
    .row {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: center;
      gap: clamp(1.5rem, 5vw, 3.5rem);
    }
    ::slotted(*) {
      opacity: 0.55;
      filter: grayscale(1);
      transition: opacity var(--ok-transition, 200ms ease), filter var(--ok-transition, 200ms ease);
      max-height: var(--ok-logo-height, 30px);
      width: auto;
      font-weight: 650;
      font-size: 1.1rem;
      color: var(--ok-text, var(--ion-text-color, #18181b));
    }
    ::slotted(*:hover) {
      opacity: 1;
      filter: grayscale(0);
    }
    /* Marquee: track en bucle. Para continuidad perfecta duplica los logos en el HTML. */
    :host([marquee]) .viewport {
      overflow: hidden;
      -webkit-mask-image: linear-gradient(90deg, transparent, #000 8%, #000 92%, transparent);
      mask-image: linear-gradient(90deg, transparent, #000 8%, #000 92%, transparent);
    }
    :host([marquee]) .row {
      flex-wrap: nowrap;
      width: max-content;
      animation: scroll var(--ok-marquee-duration, 28s) linear infinite;
    }
    @keyframes scroll {
      from { transform: translateX(0); }
      to { transform: translateX(-50%); }
    }
    @media (prefers-reduced-motion: reduce) {
      :host([marquee]) .row { animation: none; flex-wrap: wrap; }
    }
  `;

  /** Etiqueta opcional encima de los logos. */
  @property() label?: string;
  /** Desplaza la fila en bucle (duplica los logos en el HTML para continuidad). */
  @property({ type: Boolean, reflect: true }) marquee = false;

  render(): unknown {
    return html`
      ${this.label ? html`<div class="label">${this.label}</div>` : null}
      <div class="viewport"><div class="row"><slot></slot></div></div>
    `;
  }
}

define('ok-logo-cloud', OkLogoCloud);

declare global {
  interface HTMLElementTagNameMap {
    'ok-logo-cloud': OkLogoCloud;
  }
}
