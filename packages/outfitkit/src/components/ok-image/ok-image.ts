import { LitElement, html, css } from 'lit';
import { property, state } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// ok-image — wrapper de imagen lazy con skeleton shimmer + fade-in (port de .ux-img/.ux-zoom).
// Construye lo que Ionic no trae: ratio fijo (aspect-ratio), placeholder con barrido shimmer
// mientras carga, fade-in al cargar (is-loaded), caption con degradado pinned abajo, y zoom
// opcional: lens (lupa que sigue el puntero, scale + spotlight box-shadow) o lightbox (click
// abre overlay a pantalla completa). Imagen nativa con loading="lazy".

/** Relación de aspecto del marco. */
export type OkImageRatio = '16:9' | 'square' | 'portrait' | 'free';

/** Radio de las esquinas. */
export type OkImageRadius = 'sm' | 'md' | 'lg';

/** Modo de zoom/interacción. */
export type OkImageZoom = 'none' | 'lens' | 'lightbox';

export class OkImage extends LitElement {
  static styles = css`
    :host {
      display: block;
      width: 100%;
      /* Tokens propios estilo Ionic (overridables): --ok-* → --ion-* → hex/literal. */
      --bg: var(--ok-surface-variant, var(--ion-color-step-100, #e9edf0));
      --radius: var(--ok-radius-md, 8px);
      --caption-color: #ffffff;
      --caption-fade: linear-gradient(180deg, transparent, rgba(0, 0, 0, 0.66));
      --ph-color: var(--ok-color-medium, var(--ion-color-medium, #92949c));
      --shimmer-tint: rgba(0, 0, 0, 0.08);
      --lens-size: 96px;
      --lens-scale: 1.5;
      --dur-fade: 280ms;
      --dur-fast: 120ms;
      --ease: cubic-bezier(0.22, 1, 0.36, 1);
    }

    /* ---------- Marco ---------- */
    .frame {
      display: block;
      position: relative;
      overflow: hidden;
      width: 100%;
      background: var(--bg);
      border-radius: var(--radius);
      aspect-ratio: 16 / 9;
    }
    :host([ratio='square']) .frame {
      aspect-ratio: 1 / 1;
    }
    :host([ratio='portrait']) .frame {
      aspect-ratio: 3 / 4;
    }
    :host([ratio='free']) .frame {
      aspect-ratio: auto;
    }
    :host([radius='sm']) {
      --radius: var(--ok-radius-sm, 6px);
    }
    :host([radius='lg']) {
      --radius: var(--ok-radius-xl, 14px);
    }

    /* ---------- Imagen ---------- */
    .el {
      display: block;
      width: 100%;
      height: 100%;
      object-fit: cover;
      opacity: 0;
      transition: opacity var(--dur-fade) var(--ease),
        transform var(--dur-fade) var(--ease);
      transform-origin: center center;
    }
    :host([ratio='free']) .el {
      height: auto;
    }
    .frame.is-loaded .el {
      opacity: 1;
    }

    /* ---------- Placeholder + shimmer ---------- */
    .ph {
      position: absolute;
      inset: 0;
      display: grid;
      place-items: center;
      background: linear-gradient(135deg, var(--bg), color-mix(in srgb, var(--bg) 70%, #fff));
      color: var(--ph-color);
      font-size: 0.7rem;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      opacity: 1;
      transition: opacity var(--dur-fade) var(--ease);
    }
    .ph::after {
      content: '';
      position: absolute;
      inset: 0;
      background: linear-gradient(
        90deg,
        transparent 0%,
        var(--shimmer-tint) 50%,
        transparent 100%
      );
      background-size: 200% 100%;
      animation: shimmer 1.6s linear infinite;
      pointer-events: none;
    }
    @keyframes shimmer {
      from {
        background-position: 200% 0;
      }
      to {
        background-position: -200% 0;
      }
    }
    .frame.is-loaded .ph,
    .frame.is-error .ph {
      opacity: 0;
      pointer-events: none;
    }
    .frame.is-error .ph::after {
      animation: none;
    }
    .frame.is-error .err {
      opacity: 1;
    }
    .err {
      position: absolute;
      inset: 0;
      display: grid;
      place-items: center;
      background: var(--bg);
      color: var(--ph-color);
      font-size: 0.7rem;
      letter-spacing: 0.04em;
      opacity: 0;
      transition: opacity var(--dur-fade) var(--ease);
    }

    /* ---------- Caption ---------- */
    .caption {
      position: absolute;
      left: 0;
      right: 0;
      bottom: 0;
      padding: 1.5rem 0.75rem 0.75rem;
      background: var(--caption-fade);
      color: var(--caption-color);
      font-size: 0.85rem;
      font-weight: 500;
      pointer-events: none;
      z-index: 2;
    }

    /* ---------- Zoom: lens ---------- */
    :host([zoom='lens']) .frame {
      cursor: zoom-in;
    }
    :host([zoom='lens']) .frame.is-zooming {
      cursor: zoom-out;
    }
    :host([zoom='lens']) .frame.is-zooming .el {
      transform: scale(var(--lens-scale));
    }
    .lens {
      position: absolute;
      width: var(--lens-size);
      height: var(--lens-size);
      border: 2px solid #fff;
      border-radius: var(--ok-radius-sm, 6px);
      background: rgba(255, 255, 255, 0.1);
      backdrop-filter: blur(2px);
      pointer-events: none;
      opacity: 0;
      box-shadow: 0 0 0 9999px rgba(0, 0, 0, 0.25), 0 1px 3px rgba(0, 0, 0, 0.2);
      transition: opacity var(--dur-fast) var(--ease);
      z-index: 3;
    }
    .frame.is-zooming .lens {
      opacity: 1;
    }

    /* ---------- Zoom: lightbox ---------- */
    :host([zoom='lightbox']) .frame {
      cursor: pointer;
    }
    .lb-hint {
      position: absolute;
      top: 0.5rem;
      right: 0.5rem;
      width: 28px;
      height: 28px;
      display: grid;
      place-items: center;
      border-radius: var(--ok-radius-sm, 6px);
      background: rgba(0, 0, 0, 0.5);
      color: #fff;
      opacity: 0;
      transition: opacity var(--dur-fast) var(--ease);
      pointer-events: none;
      z-index: 3;
    }
    :host([zoom='lightbox']) .frame:hover .lb-hint {
      opacity: 1;
    }
    .lb-hint svg {
      width: 14px;
      height: 14px;
    }

    /* ---------- Overlay del lightbox ---------- */
    .lightbox {
      position: fixed;
      inset: 0;
      z-index: 9999;
      display: grid;
      place-items: center;
      padding: 2rem;
      background: rgba(0, 0, 0, 0.85);
      cursor: zoom-out;
      animation: lb-in var(--dur-fade) var(--ease);
    }
    @keyframes lb-in {
      from {
        opacity: 0;
      }
      to {
        opacity: 1;
      }
    }
    .lightbox img {
      max-width: 100%;
      max-height: 100%;
      object-fit: contain;
      border-radius: var(--ok-radius-md, 8px);
      box-shadow: 0 12px 48px rgba(0, 0, 0, 0.5);
    }
    .lb-close {
      position: absolute;
      top: 1rem;
      right: 1rem;
      width: 40px;
      height: 40px;
      display: grid;
      place-items: center;
      border: none;
      border-radius: 50%;
      background: rgba(255, 255, 255, 0.14);
      color: #fff;
      cursor: pointer;
      transition: background var(--dur-fast) var(--ease);
    }
    .lb-close:hover {
      background: rgba(255, 255, 255, 0.28);
    }
    .lb-close svg {
      width: 20px;
      height: 20px;
    }

    @media (prefers-reduced-motion: reduce) {
      .el,
      .ph,
      .lightbox {
        transition-duration: 0.01ms;
        animation: none;
      }
      .ph::after {
        animation: none;
      }
    }
  `;

  /** URL de la imagen. */
  @property() src = '';

  /** Texto alternativo (accesibilidad). */
  @property() alt = '';

  /** Relación de aspecto del marco. */
  @property({ reflect: true }) ratio: OkImageRatio = '16:9';

  /** Caption opcional pinned abajo con degradado. */
  @property() caption?: string;

  /** Radio de esquinas. */
  @property({ reflect: true }) radius: OkImageRadius = 'md';

  /** Modo de zoom/interacción. */
  @property({ reflect: true }) zoom: OkImageZoom = 'none';

  /** Texto del placeholder mientras carga. */
  @property({ attribute: 'placeholder-text' }) placeholderText = 'cargando…';

  /** true cuando la imagen ha cargado (fade-in). */
  @state() private loaded = false;

  /** true si la imagen falló al cargar. */
  @state() private errored = false;

  /** true mientras el cursor está sobre la imagen en modo lens. */
  @state() private zooming = false;

  /** true mientras el overlay lightbox está abierto. */
  @state() private lightboxOpen = false;

  /** Posición (%) de la lente, seguida con el puntero. */
  @state() private lensX = 50;
  @state() private lensY = 50;

  // Resetea el estado de carga cuando cambia el src.
  protected willUpdate(changed: Map<string, unknown>): void {
    if (changed.has('src')) {
      this.loaded = false;
      this.errored = false;
    }
  }

  private onLoad(): void {
    this.loaded = true;
  }

  private onError(): void {
    this.errored = true;
  }

  // ---------- Lens: seguir el puntero ----------
  private onPointerMove(e: PointerEvent): void {
    if (this.zoom !== 'lens' || !this.zooming) return;
    const frame = e.currentTarget as HTMLElement;
    const r = frame.getBoundingClientRect();
    // Posición relativa dentro del marco, acotada a [0, 100].
    this.lensX = Math.min(100, Math.max(0, ((e.clientX - r.left) / r.width) * 100));
    this.lensY = Math.min(100, Math.max(0, ((e.clientY - r.top) / r.height) * 100));
  }

  private onFrameClick(): void {
    if (this.zoom === 'lens') {
      this.zooming = !this.zooming;
      return;
    }
    if (this.zoom === 'lightbox') {
      this.openLightbox();
    }
  }

  private onPointerEnter(): void {
    // En lens el zoom se activa por click (toggle); no se auto-activa al entrar.
  }

  private onPointerLeave(): void {
    if (this.zoom === 'lens') this.zooming = false;
  }

  private openLightbox(): void {
    this.lightboxOpen = true;
    // Evento propio: permite al host abrir su propio visor en vez del overlay interno.
    this.dispatchEvent(
      new CustomEvent('ok-open', {
        detail: { src: this.src, alt: this.alt },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private closeLightbox = (): void => {
    this.lightboxOpen = false;
  };

  private onKeydown = (e: KeyboardEvent): void => {
    if (e.key === 'Escape' && this.lightboxOpen) this.closeLightbox();
  };

  connectedCallback(): void {
    super.connectedCallback();
    window.addEventListener('keydown', this.onKeydown);
  }

  disconnectedCallback(): void {
    super.disconnectedCallback();
    window.removeEventListener('keydown', this.onKeydown);
  }

  private renderLens(): unknown {
    if (this.zoom !== 'lens') return null;
    return html`
      <span
        class="lens"
        style="left:${this.lensX}%;top:${this.lensY}%;transform:translate(-50%,-50%);"
      ></span>
    `;
  }

  private renderLightboxHint(): unknown {
    if (this.zoom !== 'lightbox') return null;
    return html`
      <span class="lb-hint" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="11" cy="11" r="8"></circle>
          <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
          <line x1="11" y1="8" x2="11" y2="14"></line>
          <line x1="8" y1="11" x2="14" y2="11"></line>
        </svg>
      </span>
    `;
  }

  private renderLightbox(): unknown {
    if (!this.lightboxOpen) return null;
    return html`
      <div class="lightbox" role="dialog" aria-modal="true" @click=${this.closeLightbox}>
        <button
          class="lb-close"
          type="button"
          aria-label="Cerrar"
          @click=${this.closeLightbox}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="18" y1="6" x2="6" y2="18"></line>
            <line x1="6" y1="6" x2="18" y2="18"></line>
          </svg>
        </button>
        <img src=${this.src} alt=${this.alt} />
      </div>
    `;
  }

  render(): unknown {
    const interactive = this.zoom !== 'none';
    const cls = [
      'frame',
      this.loaded ? 'is-loaded' : '',
      this.errored ? 'is-error' : '',
      this.zooming ? 'is-zooming' : '',
    ]
      .filter(Boolean)
      .join(' ');

    return html`
      <div
        class=${cls}
        role=${interactive ? 'button' : 'img'}
        aria-label=${interactive ? this.alt || 'Imagen' : this.alt}
        tabindex=${interactive ? '0' : '-1'}
        @click=${interactive ? this.onFrameClick : null}
        @keydown=${interactive
          ? (e: KeyboardEvent) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                this.onFrameClick();
              }
            }
          : null}
        @pointermove=${this.onPointerMove}
        @pointerenter=${this.onPointerEnter}
        @pointerleave=${this.onPointerLeave}
      >
        <img
          class="el"
          src=${this.src}
          alt=${this.alt}
          loading="lazy"
          decoding="async"
          @load=${this.onLoad}
          @error=${this.onError}
        />
        <div class="ph" aria-hidden="true">${this.placeholderText}</div>
        <div class="err" aria-hidden=${!this.errored}>imagen no disponible</div>
        ${this.renderLens()} ${this.renderLightboxHint()}
        ${this.caption
          ? html`<div class="caption">${this.caption}</div>`
          : null}
      </div>
      ${this.renderLightbox()}
    `;
  }
}

define('ok-image', OkImage);

declare global {
  interface HTMLElementTagNameMap {
    'ok-image': OkImage;
  }
}
