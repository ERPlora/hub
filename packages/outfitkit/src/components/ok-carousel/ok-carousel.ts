import { LitElement, html, css } from 'lit';
import { property, state, query } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// ok-carousel — carrusel de slides con transición por `transform`.
// AUTOCONTENIDO: CSS propio en el shadow (sin Ionic salvo `ion-button`/`ion-icon` para las flechas,
// que registra el host). El contenido de los slides se aporta de dos formas (excluyentes):
//   • por `<slot>`: cada hijo directo del host es un slide.
//   • por prop `.slides`: array de strings (texto/HTML) renderizados como slides.
// Interacción: flechas prev/next, puntos indicadores clicables y swipe táctil (pointer events).
// Opcionales: `autoplay` (ms entre slides; 0 = desactivado) y `loop` (vuelve al inicio/fin).
// Eventos (bubbles + composed):
//   • `ok-change` detail { index }

// Textos i18n (default inglés). Pásalos desde fuera con `.labels`.
export interface OkCarouselLabels {
  /** aria-label de la flecha anterior. */
  previous: string;
  /** aria-label de la flecha siguiente. */
  next: string;
  /** aria-label de cada punto indicador. `{n}` se reemplaza por el número de slide. */
  goToSlide: string;
}

const DEFAULT_LABELS: OkCarouselLabels = {
  previous: 'Previous',
  next: 'Next',
  goToSlide: 'Go to slide {n}',
};

export class OkCarousel extends LitElement {
  static styles = css`
    :host {
      /* Vars overridable (estilo Ionic), default = cadena --ok-* → --ion-* → hex */
      --bg: var(--ok-surface, var(--ion-background-color, #ffffff));
      --color: var(--ok-text, var(--ion-text-color, #1c1b17));
      --primary-color: var(--ok-primary, var(--ion-color-primary, #3880ff));
      --dot-color: var(--ok-border, rgba(var(--ion-text-color-rgb, 28, 27, 23), 0.25));
      --dot-active: var(--ok-primary, var(--ion-color-primary, #3880ff));
      --arrow-bg: var(--ok-surface, var(--ion-background-color, #ffffff));
      --shadow: var(--ok-shadow, 0 2px 10px rgba(0, 0, 0, 0.15));
      --border-radius: var(--ok-radius, 12px);
      --height: var(--ok-carousel-height, 260px);
      --font: var(--ok-font, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif);

      /* Ocupa el ancho del contenedor y es responsive. */
      display: block;
      width: 100%;
      color: var(--color);
      font-family: var(--font);
    }
    /* Ventana del carrusel: recorta los slides; el track se desplaza dentro. */
    .viewport {
      position: relative;
      width: 100%;
      height: var(--height);
      overflow: hidden;
      border-radius: var(--border-radius);
      background: var(--bg);
      touch-action: pan-y;
    }
    /* Pista horizontal con todos los slides en fila; se mueve con translateX. */
    .track {
      display: flex;
      height: 100%;
      width: 100%;
      transition: transform 0.35s ease;
      will-change: transform;
    }
    /* Mientras se arrastra con el dedo, sin transición (sigue al puntero). */
    .track.dragging {
      transition: none;
    }
    .slide {
      flex: 0 0 100%;
      width: 100%;
      height: 100%;
      box-sizing: border-box;
      display: flex;
      align-items: center;
      justify-content: center;
      overflow: hidden;
    }
    /* Cuando los slides vienen de .slides (HTML/string). */
    .slide.from-prop {
      padding: 1rem;
      text-align: center;
    }
    .slide ::slotted(*) {
      width: 100%;
      height: 100%;
    }
    /* Flechas de navegación, superpuestas a izquierda/derecha y centradas verticalmente. */
    .arrow {
      position: absolute;
      top: 50%;
      transform: translateY(-50%);
      z-index: 2;
      --background: var(--arrow-bg);
      --color: var(--color);
      --border-radius: 50%;
      --box-shadow: var(--shadow);
      --padding-start: 0;
      --padding-end: 0;
      margin: 0;
      width: 40px;
      height: 40px;
    }
    .arrow.prev {
      left: 8px;
    }
    .arrow.next {
      right: 8px;
    }
    .arrow[disabled] {
      opacity: 0.35;
    }
    /* Tira de puntos indicadores bajo la ventana. */
    .dots {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 0.5rem;
      margin-top: 0.6rem;
    }
    .dot {
      width: 9px;
      height: 9px;
      padding: 0;
      border: 0;
      border-radius: 50%;
      background: var(--dot-color);
      cursor: pointer;
      transition: background-color var(--ok-transition, 150ms ease), color var(--ok-transition, 150ms ease),
        border-color var(--ok-transition, 150ms ease), box-shadow var(--ok-transition, 150ms ease),
        transform 120ms ease;
    }
    .dot.active {
      background: var(--dot-active);
      transform: scale(1.25);
    }
    @media (hover: hover) {
      .dot:not(.active):hover {
        background: var(--dot-active);
        transform: scale(1.15);
      }
    }
    .dot:active {
      transform: scale(var(--ok-press-scale, 0.97));
    }
    @media (prefers-reduced-motion: reduce) {
      .dot:hover,
      .dot:active {
        transform: none;
      }
    }
    /* En móvil, oculta las flechas y deja navegar por swipe + puntos. */
    @media (max-width: 480px) {
      .arrow {
        width: 34px;
        height: 34px;
      }
    }
  `;

  /** Slides aportados por datos (texto/HTML). Si está vacío, se usa el `<slot>`. */
  @property({ attribute: false }) slides: string[] = [];
  /** Índice del slide activo (controlable desde fuera). */
  @property({ type: Number }) index = 0;
  /** Si > 0, avanza automáticamente cada N milisegundos. */
  @property({ type: Number }) autoplay = 0;
  /** Permite saltar del último al primero (y viceversa). */
  @property({ type: Boolean }) loop = false;
  /** Textos i18n (parcial; se mezclan sobre los defaults en inglés). */
  @property({ attribute: false }) labels: Partial<OkCarouselLabels> = {};

  private get t(): OkCarouselLabels {
    return { ...DEFAULT_LABELS, ...this.labels };
  }

  // Número de slides aportados por `<slot>` (se mide al asignarse hijos).
  @state() private slottedCount = 0;

  @query('.track') private trackEl!: HTMLElement;

  // Temporizador del autoplay.
  private autoplayTimer?: ReturnType<typeof setInterval>;
  // Estado del gesto de arrastre (pointer events).
  private dragStartX = 0;
  private dragging = false;
  private dragDelta = 0;

  disconnectedCallback(): void {
    super.disconnectedCallback();
    this.stopAutoplay();
  }

  updated(changed: Map<string, unknown>): void {
    // Reinicia el autoplay si cambia el intervalo o el número de slides.
    if (changed.has('autoplay') || changed.has('slides')) {
      this.restartAutoplay();
    }
  }

  // Total de slides según la fuente activa (datos > slot).
  private get count(): number {
    return this.slides.length > 0 ? this.slides.length : this.slottedCount;
  }

  // Lee cuántos slides hay en el slot por defecto (un hijo = un slide).
  private onSlotChange(e: Event): void {
    const slot = e.target as HTMLSlotElement;
    this.slottedCount = slot.assignedElements().length;
  }

  // Mueve el carrusel a un índice concreto (respeta loop) y emite `ok-change`.
  private goTo(i: number, emit = true): void {
    const n = this.count;
    if (n === 0) return;
    let next = i;
    if (next < 0) next = this.loop ? n - 1 : 0;
    if (next > n - 1) next = this.loop ? 0 : n - 1;
    if (next === this.index) return;
    this.index = next;
    if (emit) {
      this.dispatchEvent(
        new CustomEvent('ok-change', {
          detail: { index: this.index },
          bubbles: true,
          composed: true,
        }),
      );
    }
  }

  private next(): void {
    this.goTo(this.index + 1);
    this.restartAutoplay();
  }

  private prev(): void {
    this.goTo(this.index - 1);
    this.restartAutoplay();
  }

  // ---- Autoplay -----------------------------------------------------------
  private restartAutoplay(): void {
    this.stopAutoplay();
    if (this.autoplay > 0 && this.count > 1) {
      this.autoplayTimer = setInterval(() => {
        // Si no hay loop y estamos al final, no hace nada (se queda en el último).
        if (!this.loop && this.index >= this.count - 1) {
          this.goTo(0);
        } else {
          this.goTo(this.index + 1);
        }
      }, this.autoplay);
    }
  }

  private stopAutoplay(): void {
    if (this.autoplayTimer) {
      clearInterval(this.autoplayTimer);
      this.autoplayTimer = undefined;
    }
  }

  // ---- Swipe táctil (pointer events) --------------------------------------
  private onPointerDown(e: PointerEvent): void {
    if (this.count <= 1) return;
    this.dragging = true;
    this.dragStartX = e.clientX;
    this.dragDelta = 0;
    this.stopAutoplay();
    (e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId);
  }

  private onPointerMove(e: PointerEvent): void {
    if (!this.dragging) return;
    this.dragDelta = e.clientX - this.dragStartX;
    // Sigue al dedo: desplaza el track el delta del gesto sobre la posición base.
    if (this.trackEl) {
      const base = -this.index * 100;
      const pct = (this.dragDelta / (this.offsetWidth || 1)) * 100;
      this.trackEl.style.transform = `translateX(${base + pct}%)`;
    }
  }

  private onPointerUp(): void {
    if (!this.dragging) return;
    this.dragging = false;
    const threshold = (this.offsetWidth || 1) * 0.18; // 18% del ancho para cambiar
    if (this.dragDelta <= -threshold) this.goTo(this.index + 1);
    else if (this.dragDelta >= threshold) this.goTo(this.index - 1);
    // Limpia el estilo inline para volver al render controlado por `transform`.
    if (this.trackEl) this.trackEl.style.transform = '';
    this.dragDelta = 0;
    this.restartAutoplay();
  }

  render(): unknown {
    const n = this.count;
    const fromProp = this.slides.length > 0;
    const atStart = this.index <= 0;
    const atEnd = this.index >= n - 1;

    return html`
      <div class="viewport">
        <ion-button
          class="arrow prev"
          fill="clear"
          aria-label=${this.t.previous}
          ?disabled=${n <= 1 || (!this.loop && atStart)}
          @click=${() => this.prev()}
        >
          <ion-icon slot="icon-only" name="chevron-back-outline"></ion-icon>
        </ion-button>

        <div
          class=${`track ${this.dragging ? 'dragging' : ''}`.trim()}
          style=${`transform: translateX(-${this.index * 100}%)`}
          @pointerdown=${this.onPointerDown}
          @pointermove=${this.onPointerMove}
          @pointerup=${this.onPointerUp}
          @pointercancel=${this.onPointerUp}
          @pointerleave=${this.onPointerUp}
        >
          ${fromProp
            ? this.slides.map(
                (s) => html`<div class="slide from-prop">${this.unsafeSlide(s)}</div>`,
              )
            : html`<div class="slide">
                <slot @slotchange=${this.onSlotChange}></slot>
              </div>`}
        </div>

        <ion-button
          class="arrow next"
          fill="clear"
          aria-label=${this.t.next}
          ?disabled=${n <= 1 || (!this.loop && atEnd)}
          @click=${() => this.next()}
        >
          <ion-icon slot="icon-only" name="chevron-forward-outline"></ion-icon>
        </ion-button>
      </div>

      ${n > 1
        ? html`<div class="dots" role="tablist">
            ${Array.from({ length: n }).map(
              (_, i) => html`<button
                type="button"
                class=${`dot ${i === this.index ? 'active' : ''}`.trim()}
                role="tab"
                aria-selected=${i === this.index ? 'true' : 'false'}
                aria-label=${this.t.goToSlide.replace('{n}', String(i + 1))}
                @click=${() => {
                  this.goTo(i);
                  this.restartAutoplay();
                }}
              ></button>`,
            )}
          </div>`
        : ''}
    `;
  }

  // Renderiza un slide aportado por `.slides`. Por seguridad CSP/XSS, NO inyectamos HTML crudo;
  // se muestra como texto. (El consumidor que necesite HTML rico debe usar el `<slot>`.)
  private unsafeSlide(s: string): unknown {
    return html`${s}`;
  }
}

define('ok-carousel', OkCarousel);

declare global {
  interface HTMLElementTagNameMap {
    'ok-carousel': OkCarousel;
  }
}
