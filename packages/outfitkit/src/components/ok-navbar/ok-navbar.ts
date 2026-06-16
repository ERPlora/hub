import { LitElement, html, css } from 'lit';
import { property, state } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// ok-navbar — barra de navegación web responsive (el hueco que Ionic no cubre: ion-menu es un
// drawer de app que exige ion-app + content-id y un shell de altura fija; esto es una navbar de
// landing autocontenida para páginas de scroll de documento).
// En MÓVIL el burger abre un `ion-modal` de Ionic (overlay standalone, no necesita ion-app)
// estilizado como PANEL lateral desde la DERECHA: backdrop, focus-trap, Esc, animación y a11y
// los pone Ionic. Cierra al pulsar el backdrop, el botón de cerrar, un enlace o Esc. Slots:
//   • slot="brand"   → logo / nombre (izquierda, siempre visible)
//   • slot (default) → enlaces de navegación (en línea en desktop; dentro del panel en móvil)
//   • slot="actions" → CTAs (login, "Empezar"); en línea en desktop, al pie del panel en móvil
// Contenido por slot (light DOM) → SEO crawlable. Atributos: `sticky`, `glass`, `open`.
//
// OJO (por qué el panel NO usa <slot>): Ionic re-parenta el ion-modal a <body> al presentarlo,
// fuera de nuestro shadow root — ahí los <slot> no proyectan y el CSS scoped no llega. Por eso
// el contenido del panel se construye imperativamente MOVIENDO los nodos light-DOM al modal al
// abrir (mismo patrón que el CoreDelegate de Ionic) y devolviéndolos al host al cerrar, y se
// estila con una constructed stylesheet adoptada por el documento (CSP-safe: CSSOM puro).

// Textos i18n (default inglés). Pásalos desde fuera con `.labels`.
export interface OkNavbarLabels {
  /** aria-label del botón hamburguesa (abre el menú). */
  menu: string;
  /** aria-label del botón de cerrar el panel. */
  close: string;
}

const DEFAULT_LABELS: OkNavbarLabels = {
  menu: 'Menu',
  close: 'Close',
};

const MOBILE_BREAKPOINT = '(max-width: 800px)';

// API mínima del ion-modal que usamos (sin depender de los types de @ionic/core).
interface IonModalLike extends HTMLElement {
  present(): Promise<void>;
  dismiss(): Promise<boolean>;
}

// Hoja de estilos global para el panel (vive en <body>, fuera de cualquier shadow root).
// Tokens --ok-*/--ion-* se resuelven en :root, así que la cadena de fallbacks se mantiene.
let panelSheetAdopted = false;
function adoptPanelSheet(): void {
  if (panelSheetAdopted) return;
  panelSheetAdopted = true;
  const sheet = new CSSStyleSheet();
  sheet.replaceSync(`
    ion-modal.ok-navbar-modal {
      --width: var(--ok-navbar-panel-width, min(320px, 86vw));
      --height: 100%;
      --border-radius: 0;
      --background: var(--ok-surface, var(--ion-card-background, #ffffff));
      --box-shadow: -12px 0 40px rgba(0, 0, 0, 0.18);
      /* El host del modal es un flex que centra el wrapper: lo anclamos a la derecha. */
      justify-content: flex-end;
      align-items: stretch;
    }
    .ok-navbar-modal .ok-navbar-panel {
      box-sizing: border-box;
      height: 100%;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      padding: 0.5rem var(--ok-spacing, var(--ion-padding, 16px)) var(--ok-spacing, var(--ion-padding, 16px));
      background: var(--ok-surface, var(--ion-card-background, #ffffff));
      color: var(--ok-text, var(--ion-text-color, #1c1b17));
      font-family: var(--ok-font, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif);
    }
    .ok-navbar-modal .ok-navbar-panel-head { display: flex; justify-content: flex-end; }
    .ok-navbar-modal .ok-navbar-close {
      background: none;
      border: 0;
      cursor: pointer;
      padding: 0.5rem;
      color: inherit;
    }
    .ok-navbar-modal .ok-navbar-close span { display: block; width: 22px; height: 2px; position: relative; }
    .ok-navbar-modal .ok-navbar-close span::before,
    .ok-navbar-modal .ok-navbar-close span::after {
      content: '';
      position: absolute;
      left: 0;
      top: 0;
      width: 22px;
      height: 2px;
      background: currentColor;
      border-radius: 2px;
    }
    .ok-navbar-modal .ok-navbar-close span::before { transform: rotate(45deg); }
    .ok-navbar-modal .ok-navbar-close span::after { transform: rotate(-45deg); }
    .ok-navbar-modal .ok-navbar-links { display: flex; flex-direction: column; }
    .ok-navbar-modal .ok-navbar-links a {
      display: block;
      padding: 0.85rem 0;
      color: inherit;
      text-decoration: none;
      font-size: 0.95rem;
      border-top: 1px solid var(--ok-border-soft, rgba(var(--ion-text-color-rgb, 24, 24, 27), 0.07));
    }
    .ok-navbar-modal .ok-navbar-links a:first-child { border-top: 0; }
    /* Acciones al pie: en columna, separadas de los enlaces y a ancho completo. */
    .ok-navbar-modal .ok-navbar-actions {
      display: flex;
      flex-direction: column;
      align-items: stretch;
      gap: 0.6rem;
      margin-top: 1.25rem;
      padding-top: 1.25rem;
      border-top: 1px solid var(--ok-border, rgba(var(--ion-text-color-rgb, 24, 24, 27), 0.12));
    }
    .ok-navbar-modal .ok-navbar-actions ion-button { width: 100%; }
  `);
  document.adoptedStyleSheets = [...document.adoptedStyleSheets, sheet];
}

export class OkNavbar extends LitElement {
  static styles = css`
    :host {
      /* Vars overridable (estilo Ionic), default = cadena --ok-* → --ion-* → hex */
      --background: var(--ok-surface, var(--ion-card-background, #ffffff));
      --color: var(--ok-text, var(--ion-text-color, #1c1b17));
      --border-color: var(--ok-border, rgba(var(--ion-text-color-rgb, 24, 24, 27), 0.12));
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
    /* Navbar de cristal (tendencia 2026): fondo translúcido + desenfoque. Úsalo con sticky. */
    :host([glass]) {
      background: color-mix(in oklab, var(--background) 72%, transparent);
      -webkit-backdrop-filter: blur(14px) saturate(1.4);
      backdrop-filter: blur(14px) saturate(1.4);
      border-bottom-color: color-mix(in oklab, var(--color) 9%, transparent);
    }
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
    .links { display: flex; align-items: center; gap: 1.75rem; }
    .links-inner { display: flex; align-items: center; gap: 1.25rem; }
    .actions { display: flex; align-items: center; gap: 0.5rem; }
    ::slotted(a) {
      color: var(--color);
      text-decoration: none;
      font-size: 0.95rem;
      /* Micro-interacción: transición sutil en color al hacer hover. */
      transition: background-color var(--ok-transition, 150ms ease), color var(--ok-transition, 150ms ease), border-color var(--ok-transition, 150ms ease), box-shadow var(--ok-transition, 150ms ease), transform 120ms ease;
    }
    /* Hover de enlaces solo con ratón (evita estados pegados en táctil). */
    @media (hover: hover) {
      ::slotted(a:hover) { color: var(--primary-color); }
    }

    .burger {
      display: block;
      background: none;
      border: 0;
      cursor: pointer;
      padding: 0.5rem;
      color: var(--color);
      /* Micro-interacción: feedback sutil al presionar el burger. */
      transition: background-color var(--ok-transition, 150ms ease), color var(--ok-transition, 150ms ease), border-color var(--ok-transition, 150ms ease), box-shadow var(--ok-transition, 150ms ease), transform 120ms ease;
    }
    @media (hover: hover) {
      .burger:hover { color: var(--primary-color); }
    }
    .burger:active { transform: scale(var(--ok-press-scale, 0.97)); }
    @media (prefers-reduced-motion: reduce) {
      ::slotted(a):active, .burger:hover, .burger:active { transform: none; }
    }
    .burger span { display: block; width: 22px; height: 2px; background: currentColor; border-radius: 2px; position: relative; }
    .burger span::before, .burger span::after { content: ''; position: absolute; left: 0; width: 22px; height: 2px; background: currentColor; border-radius: 2px; }
    .burger span::before { top: -7px; }
    .burger span::after { top: 7px; }
  `;

  /** Fija la navbar arriba al hacer scroll. */
  @property({ type: Boolean, reflect: true }) sticky = false;
  /** Fondo de cristal (translúcido + desenfoque). Combínalo con `sticky`. */
  @property({ type: Boolean, reflect: true }) glass = false;
  /** Estado del panel móvil (reflejado; controla el ion-modal). */
  @property({ type: Boolean, reflect: true }) open = false;
  /** Textos i18n (parcial; se mezclan sobre los defaults en inglés). */
  @property({ attribute: false }) labels: Partial<OkNavbarLabels> = {};

  /** Viewport móvil (≤800px): los slots se proyectan en la barra solo en desktop. */
  @state() private isMobile = false;

  private mq: MediaQueryList | null = null;
  private modal: IonModalLike | null = null;
  private linksHost: HTMLElement | null = null;
  private actionsHost: HTMLElement | null = null;
  private closeBtn: HTMLButtonElement | null = null;
  /** Nodos light-DOM movidos al panel (en orden original) para devolverlos al host. */
  private movedNodes: Element[] = [];

  private get t(): OkNavbarLabels {
    return { ...DEFAULT_LABELS, ...this.labels };
  }

  connectedCallback(): void {
    super.connectedCallback();
    this.mq = window.matchMedia(MOBILE_BREAKPOINT);
    this.isMobile = this.mq.matches;
    this.mq.addEventListener('change', this.onMqChange);
  }
  disconnectedCallback(): void {
    super.disconnectedCallback();
    this.mq?.removeEventListener('change', this.onMqChange);
    this.mq = null;
    this.restoreNodes();
    this.modal?.remove();
    this.modal = null;
  }

  protected updated(changed: Map<PropertyKey, unknown>): void {
    if (changed.has('open')) {
      if (this.open) void this.presentPanel();
      else void this.modal?.dismiss();
    }
    if (changed.has('labels')) this.closeBtn?.setAttribute('aria-label', this.t.close);
  }

  private onMqChange = (e: MediaQueryListEvent): void => {
    this.isMobile = e.matches;
    // Al pasar a desktop con el panel abierto, ciérralo (los nodos vuelven al host).
    if (!e.matches) this.open = false;
  };

  private openPanel(): void {
    this.open = true;
  }

  // ── Panel móvil (ion-modal en <body>, contenido movido imperativamente) ────────────

  private buildModal(): IonModalLike {
    const modal = document.createElement('ion-modal') as IonModalLike;
    modal.classList.add('ok-navbar-modal');

    const panel = document.createElement('div');
    panel.className = 'ok-navbar-panel';

    const head = document.createElement('div');
    head.className = 'ok-navbar-panel-head';
    this.closeBtn = document.createElement('button');
    this.closeBtn.className = 'ok-navbar-close';
    this.closeBtn.setAttribute('aria-label', this.t.close);
    this.closeBtn.appendChild(document.createElement('span'));
    this.closeBtn.addEventListener('click', () => { this.open = false; });
    head.appendChild(this.closeBtn);

    this.linksHost = document.createElement('nav');
    this.linksHost.className = 'ok-navbar-links';
    this.actionsHost = document.createElement('div');
    this.actionsHost.className = 'ok-navbar-actions';

    panel.append(head, this.linksHost, this.actionsHost);
    // Cierra el panel al pulsar un enlace (UX de drawer).
    panel.addEventListener('click', (e: Event) => {
      if ((e.target as Element)?.closest('a')) this.open = false;
    });
    modal.appendChild(panel);
    // Backdrop / Esc / gesto: Ionic dispara didDismiss — devolvemos los nodos y sincronizamos.
    modal.addEventListener('ionModalDidDismiss', () => {
      this.restoreNodes();
      this.open = false;
    });
    document.body.appendChild(modal);
    return modal;
  }

  private async presentPanel(): Promise<void> {
    if (!this.isMobile) return;
    adoptPanelSheet();
    if (!this.modal) this.modal = this.buildModal();
    // Mueve enlaces (slot default) y CTAs (slot="actions") del host al panel.
    if (this.movedNodes.length === 0 && this.linksHost && this.actionsHost) {
      for (const el of Array.from(this.children)) {
        const slot = el.getAttribute('slot');
        if (slot === 'brand') continue;
        this.movedNodes.push(el);
        (slot === 'actions' ? this.actionsHost : this.linksHost).appendChild(el);
      }
    }
    await customElements.whenDefined('ion-modal');
    await this.modal.present();
  }

  private restoreNodes(): void {
    for (const el of this.movedNodes) this.appendChild(el);
    this.movedNodes = [];
  }

  render(): unknown {
    return html`
      <nav class="bar">
        <div class="brand"><slot name="brand"></slot></div>
        <div class="spacer"></div>
        ${this.isMobile
          ? html`
              <button
                class="burger"
                aria-label=${this.t.menu}
                aria-haspopup="dialog"
                aria-expanded=${this.open ? 'true' : 'false'}
                @click=${this.openPanel}
              >
                <span></span>
              </button>
            `
          : html`
              <div class="links">
                <div class="links-inner"><slot></slot></div>
                <div class="actions"><slot name="actions"></slot></div>
              </div>
            `}
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
