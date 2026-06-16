import { LitElement, html, css, render, nothing } from 'lit';
import { property, state } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// Paso de un tour guiado. Lo aporta el consumidor vía la prop `.steps`.
export interface OkCoachStep {
  /** Selector CSS del elemento a destacar (spotlight). Si no resuelve, el bubble se centra. */
  target: string;
  /** Título del paso (negrita). */
  title?: string;
  /** Cuerpo descriptivo del paso. */
  text?: string;
  /**
   * Lado preferido del bubble respecto al target: `top` | `bottom` | `left` | `right`.
   * Default `bottom`. Igualmente se voltea si no cabe en el viewport (edge-aware).
   */
  placement?: OkCoachPlacement;
}

export type OkCoachPlacement = 'top' | 'bottom' | 'left' | 'right';

// Textos traducibles (default inglés). Pásalos desde fuera vía la prop `labels`.
export interface OkCoachmarkLabels {
  /** Botón anterior. */
  prev: string;
  /** Botón siguiente. */
  next: string;
  /** Botón del último paso (finaliza el tour). */
  finish: string;
  /** Botón saltar (cierra el tour). */
  skip: string;
  /** Plantilla de etiqueta de paso; `{n}` = actual (1-based), `{total}` = total. */
  step: string;
}

const DEFAULT_LABELS: OkCoachmarkLabels = {
  prev: 'Back',
  next: 'Next',
  finish: 'Done',
  skip: 'Skip',
  step: 'Step {n} of {total}',
};

// Geometría del bubble respecto al rect del target, con conciencia de bordes del viewport. Devuelve
// la posición fija (top/left) del bubble y el lado efectivo (para la flecha). REUTILIZA el espíritu
// del helper computeAnchor (elegir el lado con sitio), adaptado a 4 lados sobre un rect arbitrario.
interface BubblePos {
  top: number;
  left: number;
  side: OkCoachPlacement;
}

export class OkCoachmark extends LitElement {
  static styles = css`
    :host {
      /* Tokens propios estilo Ionic (overridables): --ok-* → --ion-* → hex. */
      --brand: var(--ok-primary, var(--ion-color-primary, #3880ff));
      --brand-soft: var(--ok-primary-soft, rgba(var(--ion-color-primary-rgb, 56, 128, 255), 0.25));
      --brand-contrast: var(--ok-primary-contrast, var(--ion-color-primary-contrast, #ffffff));
      --panel-bg: var(--ok-surface, var(--ion-card-background, var(--ion-background-color, #ffffff)));
      --color: var(--ok-text, var(--ion-text-color, #1c1b17));
      --color-muted: var(--ok-text-muted, rgba(var(--ion-text-color-rgb, 28, 27, 23), 0.62));
      --border-radius: var(--ok-radius, 14px);
      --shadow: var(--ok-shadow, 0 16px 48px rgba(0, 0, 0, 0.22));
      --scrim: var(--ok-coach-scrim, rgba(0, 0, 0, 0.45));
      --dot-off: var(--ok-coach-dot, rgba(var(--ion-text-color-rgb, 28, 27, 23), 0.2));
      --font: var(--ok-font, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif);

      display: block;
      width: 100%;
    }

    /* El host no pinta nada visible: todo el overlay se porta a document.body. */
    :host {
      position: absolute;
      width: 0;
      height: 0;
      overflow: hidden;
    }

    /* ---- Estilos del portal (adoptados por el shadow del portal en body) ---- */

    /* Scrim de cuatro paneles que rodean el hueco del spotlight (deja ver el target). */
    .scrim-piece {
      position: fixed;
      z-index: 9000;
      background: var(--scrim);
      transition: opacity 200ms ease;
    }

    /* Anillo de spotlight pulsante alrededor del target. */
    .spot {
      position: fixed;
      z-index: 9001;
      border-radius: var(--ok-coach-spot-radius, 10px);
      pointer-events: none;
      box-shadow: 0 0 0 3px var(--brand), 0 0 0 7px var(--brand-soft);
      animation: ok-coach-pulse 2s ease-in-out infinite;
    }
    @keyframes ok-coach-pulse {
      0%,
      100% {
        box-shadow: 0 0 0 3px var(--brand), 0 0 0 7px var(--brand-soft);
      }
      50% {
        box-shadow: 0 0 0 3px var(--brand), 0 0 0 12px transparent;
      }
    }
    @media (prefers-reduced-motion: reduce) {
      .spot {
        animation: none;
      }
    }

    /* Bubble anclado al target. position:fixed porque sigue rects reales del viewport. */
    .bubble {
      position: fixed;
      z-index: 9002;
      box-sizing: border-box;
      width: 290px;
      max-width: calc(100vw - 24px);
      padding: 14px 16px 12px;
      background: var(--panel-bg);
      color: var(--color);
      border: 1px solid var(--brand);
      border-radius: var(--border-radius);
      box-shadow: var(--shadow);
      font-family: var(--font);
    }

    /* Flecha del bubble: cuadrado rotado pegado al borde según el lado. */
    .arrow {
      position: absolute;
      width: 12px;
      height: 12px;
      background: var(--panel-bg);
      border: 1px solid var(--brand);
      transform: rotate(45deg);
    }
    .arrow.bottom {
      top: -7px;
      left: 50%;
      margin-left: -6px;
      border-right: 0;
      border-bottom: 0;
    }
    .arrow.top {
      bottom: -7px;
      left: 50%;
      margin-left: -6px;
      border-left: 0;
      border-top: 0;
    }
    .arrow.right {
      left: -7px;
      top: 50%;
      margin-top: -6px;
      border-right: 0;
      border-top: 0;
    }
    .arrow.left {
      right: -7px;
      top: 50%;
      margin-top: -6px;
      border-left: 0;
      border-bottom: 0;
    }

    .step-label {
      font-size: 10px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: var(--brand);
      margin: 0 0 4px;
    }
    .title {
      font-size: 14px;
      font-weight: 600;
      color: var(--color);
      margin: 0 0 4px;
    }
    .text {
      font-size: 12.5px;
      line-height: 1.5;
      color: var(--color-muted);
      margin: 0 0 12px;
    }

    .bar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
    }
    .dots {
      display: inline-flex;
      gap: 4px;
      flex-wrap: wrap;
    }
    .dots button {
      width: 6px;
      height: 6px;
      padding: 0;
      border: 0;
      border-radius: 50%;
      background: var(--dot-off);
      cursor: pointer;
      transition: width 180ms ease, background-color 180ms ease, border-radius 180ms ease;
    }
    .dots button.on {
      width: 18px;
      border-radius: 3px;
      background: var(--brand);
    }

    .actions {
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }
    /* Botones propios mínimos (ghost + primary). No reusamos ion-button para no acoplar el portal a
       estilos de host; son controles simples accesibles. */
    .btn {
      font: inherit;
      font-size: 12px;
      font-weight: 600;
      line-height: 1;
      padding: 7px 11px;
      border-radius: 8px;
      border: 1px solid transparent;
      cursor: pointer;
      background: none;
      color: var(--color-muted);
      transition: background-color 150ms ease, color 150ms ease, opacity 150ms ease;
    }
    .btn.ghost:hover {
      background: rgba(var(--ion-text-color-rgb, 28, 27, 23), 0.06);
    }
    .btn.primary {
      background: var(--brand);
      color: var(--brand-contrast);
      border-color: var(--brand);
    }
    .btn.primary:hover {
      opacity: 0.92;
    }
    .btn:focus-visible {
      outline: 2px solid var(--brand);
      outline-offset: 2px;
    }
    @media (prefers-reduced-motion: reduce) {
      .scrim-piece,
      .dots button,
      .btn {
        transition: none;
      }
    }
  `;

  /** Pasos del tour. */
  @property({ attribute: false }) steps: OkCoachStep[] = [];
  /** Índice del paso activo (0-based). Reflejado para control externo. */
  @property({ type: Number }) current = 0;
  /** Si el tour está abierto/visible. */
  @property({ type: Boolean }) open = false;
  /** Textos traducibles (merge sobre los defaults en inglés). */
  @property({ attribute: false }) labels: Partial<OkCoachmarkLabels> = {};

  // Posición calculada del spotlight + bubble (en coords de viewport). Recalculada en cada update,
  // scroll y resize.
  @state() private rect: DOMRect | null = null;
  @state() private bubble: BubblePos | null = null;

  // Portal en document.body para escapar de ancestros con transform/overflow.
  private portalRoot: ShadowRoot | null = null;

  // Textos efectivos: defaults en inglés + overrides del consumidor.
  private get t(): OkCoachmarkLabels {
    return { ...DEFAULT_LABELS, ...this.labels };
  }

  private get step(): OkCoachStep | undefined {
    return this.steps[this.current];
  }

  private get isLast(): boolean {
    return this.current >= this.steps.length - 1;
  }

  // Reposiciona en scroll/resize mientras el tour está abierto.
  private readonly onReflow = (): void => {
    if (this.open) this.measure();
  };

  private readonly onKeydown = (e: KeyboardEvent): void => {
    if (!this.open) return;
    if (e.key === 'Escape') {
      this.skip();
    } else if (e.key === 'ArrowRight') {
      this.next();
    } else if (e.key === 'ArrowLeft') {
      this.prev();
    }
  };

  disconnectedCallback(): void {
    super.disconnectedCallback();
    this.unbind();
    const host = this.portalRoot?.host;
    this.portalRoot = null;
    if (host && host.parentNode) host.parentNode.removeChild(host);
  }

  protected updated(changed: Map<string, unknown>): void {
    if (changed.has('open')) {
      if (this.open) {
        this.bind();
        this.measure();
      } else {
        this.unbind();
      }
    } else if (this.open && (changed.has('current') || changed.has('steps'))) {
      this.measure();
    }
    // Pinta (o limpia) el overlay en el portal del body.
    if (!this.open && !this.portalRoot) return;
    render(this.open ? this.overlayTemplate() : nothing, this.ensurePortal());
  }

  private bind(): void {
    document.addEventListener('keydown', this.onKeydown);
    window.addEventListener('scroll', this.onReflow, true);
    window.addEventListener('resize', this.onReflow);
  }

  private unbind(): void {
    document.removeEventListener('keydown', this.onKeydown);
    window.removeEventListener('scroll', this.onReflow, true);
    window.removeEventListener('resize', this.onReflow);
  }

  // Crea (una vez) el portal: un div en document.body con shadow propio que ADOPTA la hoja de
  // estilos del componente, de modo que scrim/spot/bubble se ven idénticos fuera del host.
  private ensurePortal(): ShadowRoot {
    if (this.portalRoot) return this.portalRoot;
    const host = document.createElement('div');
    host.setAttribute('data-ok-coachmark-portal', '');
    document.body.appendChild(host);
    const root = host.attachShadow({ mode: 'open' });
    const styles = (this.constructor as typeof OkCoachmark).elementStyles;
    // `elementStyles` mezcla CSSResult (Lit, con `.styleSheet`) y CSSStyleSheet nativo: normaliza ambos.
    root.adoptedStyleSheets = styles
      .map((s) => (s instanceof CSSStyleSheet ? s : s.styleSheet))
      .filter((s): s is CSSStyleSheet => !!s);
    this.portalRoot = root;
    return root;
  }

  // Localiza el target del paso actual, mide su rect y calcula la posición del bubble.
  private measure(): void {
    const sel = this.step?.target;
    let el: Element | null = null;
    if (sel) {
      try {
        el = document.querySelector(sel);
      } catch {
        el = null; // selector inválido → bubble centrado
      }
    }
    this.rect = el ? el.getBoundingClientRect() : null;
    this.bubble = this.computeBubble(this.rect);
  }

  // Coloca el bubble respecto al rect del target eligiendo el lado con sitio (edge-aware). Mismo
  // criterio que computeAnchor: lado preferido y, si no cabe, volteo al opuesto; clamp a márgenes.
  private computeBubble(rect: DOMRect | null): BubblePos {
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const gap = 14;
    const margin = 8;
    // Dimensiones estimadas del bubble (coinciden con el CSS); el clamp evita desbordes.
    const bw = Math.min(290, vw - 24);
    const bh = 150;

    // Sin target: centrado en el viewport.
    if (!rect) {
      return { top: (vh - bh) / 2, left: (vw - bw) / 2, side: 'bottom' };
    }

    const want: OkCoachPlacement = this.step?.placement ?? 'bottom';
    const fits = {
      bottom: rect.bottom + gap + bh <= vh - margin,
      top: rect.top - gap - bh >= margin,
      right: rect.right + gap + bw <= vw - margin,
      left: rect.left - gap - bw >= margin,
    };
    // Orden de preferencia: el deseado, luego su opuesto, luego el resto.
    const opposite: Record<OkCoachPlacement, OkCoachPlacement> = {
      bottom: 'top',
      top: 'bottom',
      left: 'right',
      right: 'left',
    };
    const order: OkCoachPlacement[] = [want, opposite[want], 'bottom', 'top', 'right', 'left'];
    const side = order.find((s) => fits[s]) ?? want;

    let top: number;
    let left: number;
    if (side === 'bottom' || side === 'top') {
      // Centrado horizontal sobre el target, abriendo arriba/abajo.
      left = rect.left + rect.width / 2 - bw / 2;
      top = side === 'bottom' ? rect.bottom + gap : rect.top - gap - bh;
    } else {
      // Centrado vertical sobre el target, abriendo izq/dcha.
      top = rect.top + rect.height / 2 - bh / 2;
      left = side === 'right' ? rect.right + gap : rect.left - gap - bw;
    }
    // Clamp a los márgenes del viewport.
    left = Math.max(margin, Math.min(left, vw - bw - margin));
    top = Math.max(margin, Math.min(top, vh - bh - margin));
    return { top, left, side };
  }

  // ---- Navegación / eventos ----

  private emit(name: string, detail?: unknown): void {
    this.dispatchEvent(new CustomEvent(name, { detail, bubbles: true, composed: true }));
  }

  private goTo(index: number): void {
    if (index < 0 || index >= this.steps.length || index === this.current) return;
    this.current = index;
    this.emit('ok-step', { index });
  }

  private next(): void {
    if (this.isLast) {
      this.finish();
      return;
    }
    const index = this.current + 1;
    this.current = index;
    this.emit('ok-next', { index });
    this.emit('ok-step', { index });
  }

  private prev(): void {
    if (this.current <= 0) return;
    const index = this.current - 1;
    this.current = index;
    this.emit('ok-prev', { index });
    this.emit('ok-step', { index });
  }

  private finish(): void {
    this.open = false;
    this.emit('ok-finish');
  }

  private skip(): void {
    this.open = false;
    this.emit('ok-skip');
  }

  // El host no renderiza nada visible (es un controlador); el overlay vive en el portal.
  render(): unknown {
    return nothing;
  }

  // Cuatro paneles de scrim que rodean el hueco del target (efecto recorte sin clip-path), o un
  // scrim completo si no hay target.
  private scrimTemplate(): unknown {
    const r = this.rect;
    if (!r) {
      return html`<div class="scrim-piece" style="inset:0" @click=${() => this.skip()}></div>`;
    }
    const pad = 6; // halo alrededor del target
    const t = Math.max(0, r.top - pad);
    const b = Math.max(0, r.bottom + pad);
    const l = Math.max(0, r.left - pad);
    const rr = Math.max(0, r.right + pad);
    const click = (): void => this.skip();
    return html`
      <div class="scrim-piece" style="left:0;top:0;right:0;height:${t}px" @click=${click}></div>
      <div class="scrim-piece" style="left:0;top:${b}px;right:0;bottom:0" @click=${click}></div>
      <div class="scrim-piece" style="left:0;top:${t}px;width:${l}px;height:${b - t}px" @click=${click}></div>
      <div class="scrim-piece" style="left:${rr}px;top:${t}px;right:0;height:${b - t}px" @click=${click}></div>
    `;
  }

  private spotTemplate(): unknown {
    const r = this.rect;
    if (!r) return nothing;
    const pad = 6;
    return html`<div
      class="spot"
      style="left:${r.left - pad}px;top:${r.top - pad}px;width:${r.width + pad * 2}px;height:${r.height + pad * 2}px"
    ></div>`;
  }

  private bubbleTemplate(): unknown {
    const pos = this.bubble;
    const s = this.step;
    if (!pos || !s) return nothing;
    const total = this.steps.length;
    const label = this.t.step
      .replace('{n}', String(this.current + 1))
      .replace('{total}', String(total));
    return html`
      <div
        class="bubble"
        role="dialog"
        aria-modal="true"
        aria-label=${s.title ?? label}
        style="top:${pos.top}px;left:${pos.left}px"
      >
        <span class="arrow ${pos.side}"></span>
        <p class="step-label">${label}</p>
        ${s.title ? html`<h2 class="title">${s.title}</h2>` : nothing}
        ${s.text ? html`<p class="text">${s.text}</p>` : nothing}
        <div class="bar">
          <div class="dots" role="tablist">
            ${this.steps.map(
              (_, i) => html`<button
                type="button"
                role="tab"
                class=${i === this.current ? 'on' : ''}
                aria-selected=${i === this.current ? 'true' : 'false'}
                aria-label=${this.t.step
                  .replace('{n}', String(i + 1))
                  .replace('{total}', String(total))}
                @click=${() => this.goTo(i)}
              ></button>`,
            )}
          </div>
          <div class="actions">
            <button type="button" class="btn ghost" @click=${() => this.skip()}>
              ${this.t.skip}
            </button>
            ${this.current > 0
              ? html`<button type="button" class="btn ghost" @click=${() => this.prev()}>
                  ${this.t.prev}
                </button>`
              : nothing}
            <button type="button" class="btn primary" @click=${() => this.next()}>
              ${this.isLast ? this.t.finish : this.t.next}
            </button>
          </div>
        </div>
      </div>
    `;
  }

  // Overlay completo renderizado en el portal de document.body.
  private overlayTemplate(): unknown {
    if (!this.step) return nothing;
    return html`${this.scrimTemplate()}${this.spotTemplate()}${this.bubbleTemplate()}`;
  }
}

define('ok-coachmark', OkCoachmark);

declare global {
  interface HTMLElementTagNameMap {
    'ok-coachmark': OkCoachmark;
  }
}
