import { LitElement, html, css } from 'lit';
import { property } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// ok-reveal — anima su contenido al entrar en el viewport (scroll reveal, tendencia 2026).
// Usa IntersectionObserver (CSP-safe, sin eval) y respeta `prefers-reduced-motion`.
//
//   <ok-reveal variant="up" delay="80"> …bloque… </ok-reveal>
//
// variant: 'up' (def) | 'fade' | 'scale' | 'left' | 'right'.
// delay: ms de retardo (para escalonar varios reveal seguidos).
// once: si true (def) revela una vez y deja de observar.
type RevealVariant = 'up' | 'fade' | 'scale' | 'left' | 'right';

export class OkReveal extends LitElement {
  static styles = css`
    :host {
      display: block;
      width: 100%;
    }
    .r {
      height: 100%;
      opacity: 0;
      transform: translateY(18px);
      transition:
        opacity var(--ok-reveal-duration, 0.65s) cubic-bezier(0.22, 0.7, 0.2, 1) var(--ok-reveal-delay, 0ms),
        transform var(--ok-reveal-duration, 0.65s) cubic-bezier(0.22, 0.7, 0.2, 1) var(--ok-reveal-delay, 0ms);
      will-change: opacity, transform;
    }
    :host([variant='fade']) .r { transform: none; }
    :host([variant='scale']) .r { transform: scale(0.95); }
    :host([variant='left']) .r { transform: translateX(-28px); }
    :host([variant='right']) .r { transform: translateX(28px); }
    :host(.ok-in) .r {
      opacity: 1;
      transform: none;
    }
    @media (prefers-reduced-motion: reduce) {
      .r {
        opacity: 1 !important;
        transform: none !important;
        transition: none !important;
      }
    }
  `;

  /** Variante de entrada. */
  @property({ reflect: true }) variant: RevealVariant = 'up';
  /** Retardo en ms (para escalonar). */
  @property({ type: Number }) delay = 0;
  /** Revelar solo una vez (def true). */
  @property({ type: Boolean }) once = true;

  private _io?: IntersectionObserver;

  connectedCallback(): void {
    super.connectedCallback();
    this.style.setProperty('--ok-reveal-delay', `${this.delay}ms`);
    // Sin IntersectionObserver (SSR/entornos viejos): muestra directamente.
    if (typeof IntersectionObserver === 'undefined') {
      this.classList.add('ok-in');
      return;
    }
    this._io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) {
            this.classList.add('ok-in');
            if (this.once) this._io?.disconnect();
          } else if (!this.once) {
            this.classList.remove('ok-in');
          }
        }
      },
      { threshold: 0.12, rootMargin: '0px 0px -8% 0px' },
    );
    this._io.observe(this);
  }

  disconnectedCallback(): void {
    super.disconnectedCallback();
    this._io?.disconnect();
  }

  render(): unknown {
    return html`<div class="r"><slot></slot></div>`;
  }
}

define('ok-reveal', OkReveal);

declare global {
  interface HTMLElementTagNameMap {
    'ok-reveal': OkReveal;
  }
}
