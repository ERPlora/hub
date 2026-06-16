import { LitElement, html, css, render, nothing } from 'lit';
import { property, state } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// Tipo de medio de un item del lightbox.
export type OkLightboxItemType = 'img' | 'video';

// Item (medio). Lo aporta el consumidor vía la prop `.items`.
export interface OkLightboxItem {
  /** URL del medio (imagen o vídeo). */
  src: string;
  /** Texto alternativo / nombre de fichero mostrado en la cabecera. */
  alt?: string;
  /** Tipo de medio; por defecto `img`. */
  type?: OkLightboxItemType;
  /** URL opcional para la miniatura del filmstrip (si difiere de `src`). */
  thumb?: string;
}

// Textos traducibles (default inglés). Pásalos desde fuera vía la prop `labels`.
export interface OkLightboxLabels {
  /** aria-label del botón anterior. */
  prev: string;
  /** aria-label del botón siguiente. */
  next: string;
  /** aria-label del botón cerrar. */
  close: string;
  /** aria-label del botón descargar. */
  download: string;
  /** aria-label del botón pantalla completa. */
  fullscreen: string;
}

const DEFAULT_LABELS: OkLightboxLabels = {
  prev: 'Previous',
  next: 'Next',
  close: 'Close',
  download: 'Download',
  fullscreen: 'Fullscreen',
};

// ok-lightbox — visor de medios a pantalla completa (galería). Overlay oscuro `fixed inset:0`,
// cabecera mono "N / M · fichero" + descargar/fullscreen/cerrar, medio centrado (máx 60% de ancho,
// 16:10), navegación circular glass prev/next de 44px y filmstrip inferior de miniaturas 50×36
// (la activa a opacidad total con outline de marca). Teclado: flechas para navegar, Esc para cerrar.
// AUTOCONTENIDO (sin Ionic salvo `ion-icon`, que registra el host) y cumple CSP.
// El overlay se PORTA a `document.body` (shadow propio con la misma hoja de estilos) para que el
// `position:fixed` se ancle al viewport y no a un ancestro con transform/filter/contain.
//   • prop `.items` → Array<OkLightboxItem>
//   • prop `index`  → índice activo (0-based)
//   • prop `open`   → muestra/oculta el visor
// Eventos (bubbles + composed):
//   • `ok-close`            (al cerrar)
//   • `ok-index` detail { index }  (al cambiar de medio)
export class OkLightbox extends LitElement {
  static styles = css`
    :host {
      display: block;
      width: 100%;
      /* Vars overridable (estilo Ionic), default = cadena --ok-* → --ion-* → hex/literal. */
      --overlay-bg: var(--ok-media-bg, rgba(0, 0, 0, 0.92));
      --fg-soft: var(--ok-media-fg, rgba(255, 255, 255, 0.7));
      --glass: var(--ok-overlay-glass, rgba(255, 255, 255, 0.1));
      --glass-hover: var(--ok-overlay-glass-2, rgba(255, 255, 255, 0.18));
      --brand: var(--ok-primary, var(--ion-color-primary, #e8552a));
      --media-bg: var(--ok-media-frame, rgba(255, 255, 255, 0.06));
      --radius-lg: var(--ok-radius-lg, 10px);
      --radius-sm: var(--ok-radius-sm, 6px);
      --font: var(--ok-font, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif);
      --font-mono: var(--ok-font-mono, ui-monospace, 'SF Mono', 'Cascadia Code', Menlo, monospace);
    }

    /* Overlay a pantalla completa: columna [cabecera | medio | filmstrip]. */
    .lightbox {
      position: fixed;
      inset: 0;
      z-index: 1000;
      display: flex;
      flex-direction: column;
      padding: 20px;
      box-sizing: border-box;
      background: var(--overlay-bg);
      color: var(--fg-soft);
      font-family: var(--font);
      opacity: 0;
      transition: opacity var(--ok-transition, 200ms ease);
    }
    .lightbox.shown {
      opacity: 1;
    }
    @media (prefers-reduced-motion: reduce) {
      .lightbox {
        transition: none;
      }
    }

    /* Cabecera mono: contador + nombre a la izquierda; acciones a la derecha. */
    .head {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      font-family: var(--font-mono);
      font-size: 12px;
      color: var(--fg-soft);
    }
    .head .meta {
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .head .count {
      font-variant-numeric: tabular-nums;
    }
    .head .sep {
      opacity: 0.5;
      margin: 0 6px;
    }
    .head .actions {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      flex: none;
    }
    .icon-btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 36px;
      height: 36px;
      padding: 0;
      border: 0;
      border-radius: 50%;
      background: transparent;
      color: var(--fg-soft);
      cursor: pointer;
      text-decoration: none;
      transition: background var(--ok-transition, 150ms ease), color var(--ok-transition, 150ms ease);
    }
    @media (hover: hover) {
      .icon-btn:hover {
        background: var(--glass);
        color: #fff;
      }
    }
    .icon-btn ion-icon {
      font-size: 1.25rem;
    }

    /* Zona central: medio centrado con flechas de navegación absolutas. */
    .main {
      flex: 1;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 16px 0;
      position: relative;
      min-height: 0;
    }
    .media {
      max-width: 60%;
      max-height: 100%;
      width: auto;
      object-fit: contain;
      background: var(--media-bg);
      border-radius: var(--radius-lg);
      display: block;
    }
    /* Reserva de proporción 16:10 cuando no hay medio o como marco de fondo. */
    .media-empty {
      width: 60%;
      aspect-ratio: 16 / 10;
      max-height: 100%;
      background: var(--media-bg);
      border-radius: var(--radius-lg);
      display: flex;
      align-items: center;
      justify-content: center;
      font-family: var(--font-mono);
      font-size: 12px;
      color: var(--fg-soft);
    }
    video.media {
      max-height: 100%;
    }

    /* Navegación circular glass de 44px. */
    .nav {
      position: absolute;
      top: 50%;
      transform: translateY(-50%);
      width: 44px;
      height: 44px;
      border-radius: 50%;
      border: 0;
      background: var(--glass);
      color: #fff;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      backdrop-filter: blur(4px);
      transition: background var(--ok-transition, 150ms ease), opacity var(--ok-transition, 150ms ease);
    }
    @media (hover: hover) {
      .nav:hover {
        background: var(--glass-hover);
      }
    }
    .nav[disabled] {
      opacity: 0.25;
      cursor: default;
      pointer-events: none;
    }
    .nav ion-icon {
      font-size: 1.5rem;
    }
    .nav.prev {
      left: 20px;
    }
    .nav.next {
      right: 20px;
    }

    /* Filmstrip inferior: miniaturas 50×36, la activa a opacidad total con outline de marca. */
    .strip {
      display: flex;
      gap: 6px;
      justify-content: center;
      flex-wrap: wrap;
      padding-top: 12px;
      max-height: 96px;
      overflow-x: auto;
      overflow-y: hidden;
    }
    .thumb {
      flex: none;
      width: 50px;
      height: 36px;
      padding: 0;
      border: 0;
      border-radius: var(--radius-sm);
      background: var(--media-bg);
      background-size: cover;
      background-position: center;
      cursor: pointer;
      opacity: 0.5;
      overflow: hidden;
      transition: opacity var(--ok-transition, 150ms ease);
    }
    @media (hover: hover) {
      .thumb:hover {
        opacity: 0.8;
      }
    }
    .thumb.active {
      opacity: 1;
      outline: 2px solid var(--brand);
      outline-offset: 2px;
    }
    .thumb img {
      width: 100%;
      height: 100%;
      object-fit: cover;
      display: block;
    }
    .thumb .vid {
      display: flex;
      align-items: center;
      justify-content: center;
      width: 100%;
      height: 100%;
      color: var(--fg-soft);
    }
    .thumb .vid ion-icon {
      font-size: 1rem;
    }
  `;

  /** Medios a mostrar. */
  @property({ attribute: false }) items: OkLightboxItem[] = [];
  /** Índice activo (0-based). */
  @property({ type: Number }) index = 0;
  /** Muestra/oculta el visor. */
  @property({ type: Boolean }) open = false;
  /** Textos traducibles (merge sobre los defaults en inglés). */
  @property({ attribute: false }) labels: Partial<OkLightboxLabels> = {};

  // Estado interno: clase de visibilidad para disparar la transición de entrada/salida.
  @state() private shown = false;

  // Textos efectivos: defaults en inglés + overrides del consumidor.
  private get t(): OkLightboxLabels {
    return { ...DEFAULT_LABELS, ...this.labels };
  }

  // Portal del overlay en `document.body` (shadow propio) para escapar de ancestros transformados.
  private portalRoot: ShadowRoot | null = null;

  disconnectedCallback(): void {
    super.disconnectedCallback();
    this.unbind();
    const host = this.portalRoot?.host;
    this.portalRoot = null;
    if (host && host.parentNode) host.parentNode.removeChild(host);
  }

  // Handler de teclado: flechas navegan, Esc cierra.
  private readonly onKeydown = (e: KeyboardEvent): void => {
    if (!this.open) return;
    if (e.key === 'Escape') {
      e.preventDefault();
      this.requestClose();
    } else if (e.key === 'ArrowLeft') {
      e.preventDefault();
      this.go(-1);
    } else if (e.key === 'ArrowRight') {
      e.preventDefault();
      this.go(1);
    }
  };

  private bind(): void {
    document.addEventListener('keydown', this.onKeydown);
  }

  private unbind(): void {
    document.removeEventListener('keydown', this.onKeydown);
  }

  // Crea (una vez) el portal: un div en `document.body` con shadow propio que ADOPTA la misma hoja
  // de estilos del componente.
  private ensurePortal(): ShadowRoot {
    if (this.portalRoot) return this.portalRoot;
    const host = document.createElement('div');
    host.setAttribute('data-ok-lightbox-portal', '');
    document.body.appendChild(host);
    const root = host.attachShadow({ mode: 'open' });
    const styles = (this.constructor as typeof OkLightbox).elementStyles ?? [];
    root.adoptedStyleSheets = styles
      .map((s) => (s instanceof CSSStyleSheet ? s : s.styleSheet))
      .filter((s): s is CSSStyleSheet => !!s);
    this.portalRoot = root;
    return root;
  }

  protected updated(changed: Map<string, unknown>): void {
    if (changed.has('open')) {
      if (this.open) {
        this.bind();
        // Tras montar el overlay, en el siguiente frame activamos la clase para el fade-in.
        requestAnimationFrame(() => requestAnimationFrame(() => (this.shown = true)));
      } else {
        this.unbind();
        this.shown = false;
      }
    }
    // Renderiza (o limpia) el overlay en el portal del body. No crea el portal hasta la 1ª apertura.
    if (!this.open && !this.portalRoot) return;
    render(this.open ? this.overlayTemplate() : nothing, this.ensurePortal());
  }

  // Índice saneado dentro de los límites.
  private get safeIndex(): number {
    const n = this.items.length;
    if (n === 0) return 0;
    return Math.max(0, Math.min(this.index, n - 1));
  }

  private prefersReducedMotion(): boolean {
    return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;
  }

  // Navega delta posiciones (clamp, sin wrap). Emite `ok-index` si cambia.
  private go(delta: number): void {
    const next = this.safeIndex + delta;
    if (next < 0 || next >= this.items.length || next === this.safeIndex) return;
    this.setIndex(next);
  }

  private setIndex(i: number): void {
    if (i === this.safeIndex) return;
    this.index = i;
    this.dispatchEvent(
      new CustomEvent('ok-index', { detail: { index: i }, bubbles: true, composed: true }),
    );
  }

  // Pide cerrar: anima el fade-out y al terminar emite `ok-close` (el consumidor pone `open=false`).
  private requestClose(): void {
    this.unbind();
    this.shown = false;
    const box = this.portalRoot?.querySelector('.lightbox') as HTMLElement | null;
    const finish = (): void => {
      this.dispatchEvent(new CustomEvent('ok-close', { bubbles: true, composed: true }));
    };
    if (box && !this.prefersReducedMotion()) {
      box.addEventListener('transitionend', finish, { once: true });
    } else {
      finish();
    }
  }

  // Nombre de fichero mostrado en la cabecera (alt o último segmento de la URL).
  private fileName(item: OkLightboxItem | undefined): string {
    if (!item) return '';
    if (item.alt) return item.alt;
    try {
      const path = item.src.split(/[?#]/)[0];
      return path.substring(path.lastIndexOf('/') + 1) || item.src;
    } catch {
      return item.src;
    }
  }

  render(): unknown {
    // Solo el portal renderiza el overlay; el host en el flujo no pinta nada visible.
    return nothing;
  }

  // Overlay (cabecera + medio + filmstrip). Se renderiza en el portal de `document.body`.
  private overlayTemplate(): unknown {
    const items = this.items;
    const i = this.safeIndex;
    const current: OkLightboxItem | undefined = items[i];
    const isVideo = current?.type === 'video';
    const name = this.fileName(current);
    const total = items.length;

    return html`
      <div
        class="lightbox ${this.shown ? 'shown' : ''}"
        role="dialog"
        aria-modal="true"
        aria-label=${name}
      >
        <div class="head">
          <div class="meta">
            <span class="count">${total ? i + 1 : 0} / ${total}</span>
            ${name ? html`<span class="sep">·</span><span>${name}</span>` : null}
          </div>
          <div class="actions">
            ${current
              ? html`<a
                  class="icon-btn"
                  href=${current.src}
                  download
                  target="_blank"
                  rel="noopener"
                  aria-label=${this.t.download}
                >
                  <ion-icon name="download-outline"></ion-icon>
                </a>`
              : null}
            <button
              type="button"
              class="icon-btn"
              aria-label=${this.t.fullscreen}
              @click=${() => this.toggleFullscreen()}
            >
              <ion-icon name="expand-outline"></ion-icon>
            </button>
            <button
              type="button"
              class="icon-btn"
              aria-label=${this.t.close}
              @click=${() => this.requestClose()}
            >
              <ion-icon name="close-outline"></ion-icon>
            </button>
          </div>
        </div>

        <div class="main">
          <button
            type="button"
            class="nav prev"
            aria-label=${this.t.prev}
            ?disabled=${i <= 0}
            @click=${() => this.go(-1)}
          >
            <ion-icon name="chevron-back-outline"></ion-icon>
          </button>

          ${current
            ? isVideo
              ? html`<video
                  class="media"
                  src=${current.src}
                  controls
                  playsinline
                  aria-label=${name}
                ></video>`
              : html`<img class="media" src=${current.src} alt=${name} />`
            : html`<div class="media-empty"></div>`}

          <button
            type="button"
            class="nav next"
            aria-label=${this.t.next}
            ?disabled=${i >= total - 1}
            @click=${() => this.go(1)}
          >
            <ion-icon name="chevron-forward-outline"></ion-icon>
          </button>
        </div>

        ${total > 1
          ? html`<div class="strip" role="tablist">
              ${items.map((it, idx) => this.renderThumb(it, idx, idx === i))}
            </div>`
          : null}
      </div>
    `;
  }

  private renderThumb(item: OkLightboxItem, idx: number, active: boolean): unknown {
    const isVideo = item.type === 'video';
    return html`<button
      type="button"
      class="thumb ${active ? 'active' : ''}"
      role="tab"
      aria-selected=${active ? 'true' : 'false'}
      aria-label=${this.fileName(item)}
      @click=${() => this.setIndex(idx)}
    >
      ${isVideo
        ? html`<span class="vid"><ion-icon name="play-outline"></ion-icon></span>`
        : html`<img src=${item.thumb ?? item.src} alt="" loading="lazy" />`}
    </button>`;
  }

  // Pantalla completa nativa sobre el overlay portado (con fallback silencioso si no se concede).
  private toggleFullscreen(): void {
    const box = this.portalRoot?.querySelector('.lightbox') as HTMLElement | null;
    if (!box) return;
    if (document.fullscreenElement) {
      void document.exitFullscreen?.();
    } else {
      void box.requestFullscreen?.().catch(() => undefined);
    }
  }
}

define('ok-lightbox', OkLightbox);

declare global {
  interface HTMLElementTagNameMap {
    'ok-lightbox': OkLightbox;
  }
}
