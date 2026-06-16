import { LitElement, html, css, type PropertyValues } from 'lit';
import { property, query } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// ok-drawer — panel lateral deslizante (slide-over) contextual. Ionic NO lo trae: `ion-menu` es
// navegación de app (ligado a split-pane/content-id) y `ion-modal` sheet es bottom-sheet. Este es
// el panel lateral derecho/izquierdo típico de un ERP: asistente, detalle de registro, filtros.
// Es un OVERLAY PROPIO (scrim opcional + panel fijo lateral), AUTOCONTENIDO: CSS en el shadow
// (solo `ion-icon`, que registra el host).
//   • `open`        → abierto/cerrado (reflejado). Modo CONTROLADO: el padre puede sincronizarlo
//                     (señal Datastar en Cloud, ref Vue en el Hub).
//   • `side`        → 'end' (def, derecha en LTR) | 'start'.
//   • `width`       → ancho del panel (def 420px; en móvil 100%).
//   • `heading`     → título de la cabecera · `icon` → ionicon junto al título.
//   • `scrim`       → fondo oscurecido clicable (def true).
//   • `dismissible` → cierra con ESC / click en scrim / botón X (def true).
//   • `labels`      → textos traducibles (patrón de la librería; default inglés).
// Cierre: los gestos (scrim/esc/botón) emiten `ok-close` CANCELABLE con detail.reason; si nadie
// hace `preventDefault()`, el componente se cierra solo (fallback no-controlado). Un padre en modo
// controlado puede vetar con `preventDefault()` y decidir él sobre `open`.
// Eventos (bubbles + composed):
//   • `ok-open`  detail { open: true }                    al abrirse
//   • `ok-close` detail { reason: 'scrim'|'esc'|'button' } cancelable, en cada gesto de cierre
// A11y: role="dialog" + aria-modal, focus-trap mientras está abierto, restore de foco al cerrar,
// `prefers-reduced-motion` sin transición.
// Theming: --ok-drawer-width, --ok-drawer-bg (cadena --ok-* → --ion-* → hex), sombra --ok-shadow-md.

/** Lado del drawer ('end' = derecha en LTR). */
export type OkDrawerSide = 'end' | 'start';

/** Textos humanos de ok-drawer (i18n; default inglés, override vía prop `labels`). */
export interface OkDrawerLabels {
  /** aria-label / tooltip del botón de cerrar (X). */
  close: string;
}

const DEFAULT_LABELS: OkDrawerLabels = {
  close: 'Close',
};

// Selector de elementos enfocables (para el focus-trap).
const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), ' +
  'textarea:not([disabled]), ion-button:not([disabled]), ion-input, ion-searchbar, ' +
  '[tabindex]:not([tabindex="-1"])';

export class OkDrawer extends LitElement {
  static styles = css`
    :host {
      /* Vars overridable (estilo Ionic), default = cadena --ok-* → --ion-* → hex */
      --color: var(--ok-text, var(--ion-text-color, #1c1b17));
      --color-muted: var(--ok-text-muted, rgba(var(--ion-text-color-rgb, 28, 27, 23), 0.6));
      --panel-bg: var(--ok-drawer-bg, var(--ok-surface, var(--ion-card-background, var(--ion-background-color, #ffffff))));
      --scrim-bg: var(--ok-scrim, rgba(0, 0, 0, 0.4));
      --border-soft: var(--ok-border-soft, rgba(var(--ion-text-color-rgb, 28, 27, 23), 0.08));
      --shadow: var(--ok-shadow-md, 0 10px 40px rgba(0, 0, 0, 0.22));
      --font: var(--ok-font, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif);

      /* El host no ocupa caja: scrim y panel van a position:fixed sobre todo. */
      display: contents;
    }

    /* Scrim a pantalla completa (cierra al click si dismissible). */
    .scrim {
      position: fixed;
      inset: 0;
      z-index: 2000;
      background: var(--scrim-bg);
      animation: fade-in 180ms ease;
    }

    /* Panel lateral fijo: columna header · body (scroll) · footer. */
    .panel {
      position: fixed;
      top: 0;
      bottom: 0;
      z-index: 2001;
      /* Cadena: token global → prop width (inyectada como var local) → 420px. */
      width: var(--ok-drawer-width, var(--drawer-width, 420px));
      max-width: 100vw;
      display: flex;
      flex-direction: column;
      box-sizing: border-box;
      background: var(--panel-bg);
      box-shadow: var(--shadow);
      font-family: var(--font);
      color: var(--color);
      /* Lado por defecto: end (derecha en LTR). */
      inset-inline-end: 0;
      border-inline-start: 1px solid var(--border-soft);
      animation: slide-in-end 200ms ease;
    }
    :host([side='start']) .panel {
      inset-inline-end: auto;
      inset-inline-start: 0;
      border-inline-start: 0;
      border-inline-end: 1px solid var(--border-soft);
      animation: slide-in-start 200ms ease;
    }

    @keyframes fade-in {
      from { opacity: 0; }
      to { opacity: 1; }
    }
    @keyframes slide-in-end {
      from { transform: translateX(100%); }
      to { transform: translateX(0); }
    }
    @keyframes slide-in-start {
      from { transform: translateX(-100%); }
      to { transform: translateX(0); }
    }
    @media (prefers-reduced-motion: reduce) {
      .scrim,
      .panel {
        animation: none;
      }
    }

    /* Cabecera: icono + título + acciones extra + botón X. */
    .header {
      flex: 0 0 auto;
      display: flex;
      align-items: center;
      gap: 0.6rem;
      padding: 0.85rem 1rem;
      border-bottom: 1px solid var(--border-soft);
    }
    .header > ion-icon {
      flex: 0 0 auto;
      font-size: 1.25rem;
      color: var(--color-muted);
    }
    .heading {
      flex: 1 1 auto;
      min-width: 0;
      margin: 0;
      font-size: 1.05rem;
      font-weight: 600;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    /* Acciones extra de cabecera (slot header-actions) + botón cerrar. */
    .header-actions {
      flex: 0 0 auto;
      display: flex;
      align-items: center;
      gap: 0.25rem;
    }
    .close {
      flex: 0 0 auto;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 32px;
      height: 32px;
      padding: 0;
      border: 0;
      border-radius: 8px;
      background: none;
      color: var(--color-muted);
      font-size: 1.25rem;
      cursor: pointer;
      transition: background-color var(--ok-transition, 150ms ease), color var(--ok-transition, 150ms ease);
    }
    @media (hover: hover) {
      .close:hover {
        background: var(--ok-hover, rgba(var(--ion-text-color-rgb, 28, 27, 23), 0.06));
        color: var(--color);
      }
    }

    /* Cuerpo: scroll interno. */
    .body {
      flex: 1 1 auto;
      min-height: 0;
      overflow-y: auto;
      padding: 1rem;
      box-sizing: border-box;
    }

    /* Pie fijo opcional (se oculta si el slot está vacío). */
    .footer {
      flex: 0 0 auto;
      padding: 0.75rem 1rem;
      border-top: 1px solid var(--border-soft);
    }
    .footer.empty {
      display: none;
    }

    /* En móvil el panel ocupa todo el ancho. */
    @media (max-width: 640px) {
      .panel {
        width: 100%;
        border: 0;
      }
    }
  `;

  /** Abierto/cerrado (reflejado). El padre puede controlarlo (señal/ref). */
  @property({ type: Boolean, reflect: true }) open = false;
  /** Lado del panel: 'end' (def, derecha en LTR) | 'start' (reflejado para CSS). */
  @property({ reflect: true }) side: OkDrawerSide = 'end';
  /** Ancho del panel (def 420px; en móvil siempre 100%). */
  @property() width = '420px';
  /** Título de la cabecera. */
  @property() heading?: string;
  /** Nombre de un ionicon junto al título. */
  @property() icon?: string;
  /** Fondo oscurecido clicable (def true). Para quitarlo: `.scrim=${false}`. */
  @property({ type: Boolean }) scrim = true;
  /** Si true (def), cierra con ESC / click en scrim / botón X. Si false, oculta la X. */
  @property({ type: Boolean }) dismissible = true;
  /** Overrides de textos humanos (i18n). Se fusionan sobre los defaults en inglés. */
  @property({ attribute: false }) labels: Partial<OkDrawerLabels> = {};

  /** Textos efectivos (defaults inglés + overrides). */
  private get t(): OkDrawerLabels {
    return { ...DEFAULT_LABELS, ...this.labels };
  }

  @query('.panel') private panel?: HTMLElement;

  // Elemento con foco antes de abrir (para restaurarlo al cerrar).
  private previousFocus: HTMLElement | null = null;
  // ¿El slot `footer` tiene contenido? (oculta el pie si no).
  private hasFooter = false;

  // Teclado global mientras está abierto: ESC cierra (si dismissible), Tab queda atrapado.
  private readonly onDocKeydown = (e: KeyboardEvent): void => {
    if (!this.open) return;
    if (e.key === 'Escape') {
      if (this.dismissible) {
        e.preventDefault();
        this.requestClose('esc');
      }
      return;
    }
    if (e.key === 'Tab') this.trapFocus(e);
  };

  disconnectedCallback(): void {
    super.disconnectedCallback();
    document.removeEventListener('keydown', this.onDocKeydown);
  }

  // ── Apertura / cierre ──────────────────────────────────────────────────────
  protected updated(changed: PropertyValues): void {
    if (!changed.has('open')) return;
    const was = changed.get('open') as boolean | undefined;
    if (this.open && !was) this.afterOpen();
    else if (!this.open && was) this.afterClose();
  }

  // Al abrir: guarda el foco actual, enfoca el panel y arma el teclado global.
  private afterOpen(): void {
    this.previousFocus = (document.activeElement as HTMLElement | null) ?? null;
    document.addEventListener('keydown', this.onDocKeydown);
    this.updateComplete.then(() => {
      // Enfoca el primer enfocable del panel; si no hay, el propio panel (tabindex -1).
      const first = this.focusables()[0];
      (first ?? this.panel)?.focus();
    });
    this.dispatchEvent(
      new CustomEvent('ok-open', { detail: { open: true }, bubbles: true, composed: true }),
    );
  }

  // Al cerrar: desarma el teclado y restaura el foco previo.
  private afterClose(): void {
    document.removeEventListener('keydown', this.onDocKeydown);
    this.previousFocus?.focus?.();
    this.previousFocus = null;
  }

  /**
   * Gesto de cierre (scrim/esc/botón): emite `ok-close` CANCELABLE con la razón. Si nadie hace
   * `preventDefault()` se auto-cierra (fallback no-controlado); un padre controlado puede vetar.
   */
  requestClose(reason: 'scrim' | 'esc' | 'button'): void {
    const ev = new CustomEvent('ok-close', {
      detail: { reason },
      bubbles: true,
      composed: true,
      cancelable: true,
    });
    const proceed = this.dispatchEvent(ev); // false si algún listener hizo preventDefault()
    if (proceed) this.open = false;
  }

  /** Abre el drawer (azúcar imperativo; equivale a `open = true`). */
  show(): void {
    this.open = true;
  }

  /** Cierra el drawer sin pasar por el gesto cancelable (azúcar imperativo). */
  hide(): void {
    this.open = false;
  }

  // ── Focus trap ─────────────────────────────────────────────────────────────
  // Enfocables del panel (shadow) + del contenido slotted (light DOM del host).
  private focusables(): HTMLElement[] {
    const inShadow = this.panel ? Array.from(this.panel.querySelectorAll<HTMLElement>(FOCUSABLE)) : [];
    const inLight = Array.from(this.querySelectorAll<HTMLElement>(FOCUSABLE));
    return [...inShadow, ...inLight].filter((el) => el.offsetParent !== null || el === document.activeElement);
  }

  // Mantiene Tab/Shift+Tab ciclando dentro del drawer mientras está abierto.
  private trapFocus(e: KeyboardEvent): void {
    const list = this.focusables();
    if (!list.length) {
      e.preventDefault();
      this.panel?.focus();
      return;
    }
    const active = (this.shadowRoot?.activeElement as HTMLElement | null) ?? (document.activeElement as HTMLElement | null);
    const idx = active ? list.indexOf(active) : -1;
    if (e.shiftKey) {
      if (idx <= 0) {
        e.preventDefault();
        list[list.length - 1].focus();
      }
    } else if (idx === -1 || idx === list.length - 1) {
      e.preventDefault();
      list[0].focus();
    }
  }

  // ── Interacción ────────────────────────────────────────────────────────────
  // Cierra al click en el scrim (solo si dismissible).
  private onScrimClick(): void {
    if (this.dismissible) this.requestClose('scrim');
  }

  private onFooterSlotChange(e: Event): void {
    const slot = e.target as HTMLSlotElement;
    const has = slot.assignedNodes({ flatten: true }).length > 0;
    if (has !== this.hasFooter) {
      this.hasFooter = has;
      this.requestUpdate();
    }
  }

  // ── Render ─────────────────────────────────────────────────────────────────
  render(): unknown {
    if (!this.open) return html``;

    return html`
      ${this.scrim ? html`<div class="scrim" @click=${() => this.onScrimClick()}></div>` : ''}
      <aside
        class="panel"
        style="--drawer-width:${this.width}"
        role="dialog"
        aria-modal="true"
        aria-label=${this.heading ?? 'drawer'}
        tabindex="-1"
      >
        <header class="header">
          ${this.icon ? html`<ion-icon .name=${this.icon} aria-hidden="true"></ion-icon>` : ''}
          ${this.heading ? html`<h2 class="heading">${this.heading}</h2>` : html`<span class="heading"></span>`}
          <div class="header-actions">
            <slot name="header-actions"></slot>
            ${this.dismissible
              ? html`<button
                  class="close"
                  type="button"
                  aria-label=${this.t.close}
                  title=${this.t.close}
                  @click=${() => this.requestClose('button')}
                >
                  <ion-icon name="close-outline" aria-hidden="true"></ion-icon>
                </button>`
              : ''}
          </div>
        </header>
        <div class="body"><slot></slot></div>
        <footer class=${this.hasFooter ? 'footer' : 'footer empty'}>
          <slot name="footer" @slotchange=${(e: Event) => this.onFooterSlotChange(e)}></slot>
        </footer>
      </aside>
    `;
  }
}

define('ok-drawer', OkDrawer);

declare global {
  interface HTMLElementTagNameMap {
    'ok-drawer': OkDrawer;
  }
}
