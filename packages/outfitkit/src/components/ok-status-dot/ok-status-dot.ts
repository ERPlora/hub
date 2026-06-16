import { LitElement, html, css } from 'lit';
import { property } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// ok-status-dot — punto de presencia/estado coloreado y compacto.
// Forma reducida de ok-status-pill: solo el dot (+ label opcional inline o sr-only)
// y animación de pulso opcional. Mapea tone → --ion-color-* con fallback a hex.
// Portado del antiguo .ux-status-dot (orphan-variants.css).

/** Tono semántico del dot. */
export type OkStatusDotTone = 'ok' | 'warn' | 'danger' | 'info' | 'off' | 'brand';

/** Tamaño del dot. */
export type OkStatusDotSize = 'sm' | 'md' | 'lg';

export class OkStatusDot extends LitElement {
  static styles = css`
    :host {
      /* Átomo inline: ocupa solo su contenido. */
      display: inline-flex;
      align-items: center;
      vertical-align: middle;
      /* Tono por defecto (off). Cada variante reescribe --dot-color en :host([tone=...]). */
      --dot-color: var(--ok-color-medium, var(--ion-color-medium, #92949c));
      --dot-size: 0.625rem;
      --label-color: var(--ok-text-color, var(--ion-text-color, #1f2933));
    }

    /* ---- Tonos: --ok-* → --ion-color-* → hex (tomados del diseño ux antiguo) ---- */
    :host([tone='ok']) {
      --dot-color: var(--ok-color-success, var(--ion-color-success, #4f9d6e));
    }
    :host([tone='warn']) {
      --dot-color: var(--ok-color-warning, var(--ion-color-warning, #d8a23a));
    }
    :host([tone='danger']) {
      --dot-color: var(--ok-color-danger, var(--ion-color-danger, #d8553f));
    }
    :host([tone='info']) {
      --dot-color: var(--ok-color-primary, var(--ion-color-primary, #3880ff));
    }
    :host([tone='off']) {
      --dot-color: var(--ok-color-medium, var(--ion-color-medium, #92949c));
    }
    :host([tone='brand']) {
      --dot-color: var(--ok-color-secondary, var(--ion-color-secondary, #0091ce));
    }

    /* ---- Tamaños ---- */
    :host([size='sm']) {
      --dot-size: 0.5rem;
    }
    :host([size='lg']) {
      --dot-size: 0.875rem;
    }

    .wrap {
      display: inline-flex;
      align-items: center;
      gap: 0.375rem;
    }

    .dot {
      position: relative;
      flex-shrink: 0;
      width: var(--dot-size);
      height: var(--dot-size);
      border-radius: 999px;
      background: var(--dot-color);
    }

    /* Aro de pulso: halo que escala y se desvanece como señal "en vivo". */
    :host([pulse]) .dot::after {
      content: '';
      position: absolute;
      inset: 0;
      border-radius: inherit;
      background: var(--dot-color);
      animation: ok-status-pulse 1.6s ease-out infinite;
    }

    @keyframes ok-status-pulse {
      0% {
        transform: scale(1);
        opacity: 0.55;
      }
      70% {
        transform: scale(2.6);
        opacity: 0;
      }
      100% {
        transform: scale(2.6);
        opacity: 0;
      }
    }

    @media (prefers-reduced-motion: reduce) {
      :host([pulse]) .dot::after {
        animation: none;
      }
    }

    .label {
      font-size: 0.8125rem;
      font-weight: 500;
      color: var(--label-color);
      line-height: 1.2;
    }

    /* Etiqueta accesible oculta visualmente (sr-only). */
    .sr-only {
      position: absolute;
      width: 1px;
      height: 1px;
      padding: 0;
      margin: -1px;
      overflow: hidden;
      clip: rect(0, 0, 0, 0);
      white-space: nowrap;
      border: 0;
    }
  `;

  /** Tono semántico: ok | warn | danger | info | off | brand. */
  @property({ reflect: true }) tone: OkStatusDotTone = 'off';

  /** Tamaño: sm | md | lg. */
  @property({ reflect: true }) size: OkStatusDotSize = 'md';

  /** Animación de pulso "en vivo". */
  @property({ type: Boolean, reflect: true }) pulse = false;

  /** Texto descriptivo del estado (para accesibilidad y/o visible). */
  @property() label?: string;

  /** Si hay label, mostrarlo inline junto al dot (si no, queda solo sr-only). */
  @property({ type: Boolean, attribute: 'show-label' }) showLabel = false;

  render(): unknown {
    const labelInline = this.label && this.showLabel;
    const labelSr = this.label && !this.showLabel;
    return html`
      <span
        class="wrap"
        role="img"
        aria-label=${this.label ?? this.tone}
      >
        <span class="dot"></span>
        ${labelInline ? html`<span class="label">${this.label}</span>` : null}
        ${labelSr ? html`<span class="sr-only">${this.label}</span>` : null}
      </span>
    `;
  }
}

define('ok-status-dot', OkStatusDot);

declare global {
  interface HTMLElementTagNameMap {
    'ok-status-dot': OkStatusDot;
  }
}
