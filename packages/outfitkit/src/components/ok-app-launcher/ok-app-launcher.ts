import { LitElement, html, css, render, nothing } from 'lit';
import { property, state } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// App (entrada de la rejilla). La aporta el consumidor vía la prop `.apps`.
export interface OkLauncherApp {
  /** Identificador único de la app (clave de selección). */
  id: string;
  /** Texto visible bajo el icono. */
  label: string;
  /**
   * Icono mostrado grande sobre el label. Acepta dos formas:
   *   • el NOMBRE de un ionicon (p. ej. `cube-outline`) → se pinta vía `ion-icon name`;
   *   • un SVG ya resuelto (string `<svg…>` o `data:` URI) → se pinta vía `ion-icon icon`,
   *     útil en hosts con iconos horneados/offline (sin red ni CDN).
   */
  icon?: string;
  /** Si está presente, al hacer click navega a esta URL (en lugar de emitir evento). */
  href?: string;
  /** Color de fondo del cuadro del icono (cualquier valor CSS); default = primary. */
  color?: string;
}

// ok-app-launcher — botón estilo "Google apps": un disparador con icono de rejilla 3×3
// (`apps-outline`) que abre una HOJA DE ACCIÓN (action sheet) anclada a la parte INFERIOR de la
// pantalla con una REJILLA de apps (icono grande + label), al estilo del sheet modal de Ionic.
// AUTOCONTENIDO: scrim + hoja deslizante propios (sin Ionic salvo `ion-icon`, que registra el host)
// y cumple CSP. El overlay se PORTA a `document.body` (shadow propio con la misma hoja de estilos)
// para escapar de cualquier ancestro con `transform`/`filter`/`contain` —p. ej. el `ion-buttons`
// del toolbar de Ionic— que, si no, capturaría el `position:fixed` y descolocaría la hoja.
//   • prop `.apps` → Array<OkLauncherApp>
// El disparador es INLINE (ocupa solo lo que mide el botón); la hoja es full-width abajo.
// Click en una app: si tiene `href` navega; si no, emite `ok-app-select`. Cierra al click en el
// scrim, al pulsar el icono de cerrar o con Esc.
// Eventos (bubbles + composed):
//   • `ok-app-select` detail { id, app }
//   • `ok-open`        detail { open }

// Textos traducibles (default inglés). Pásalos desde fuera vía la prop `labels`.
export interface OkAppLauncherLabels {
  /** aria-label del botón disparador y título de la hoja. */
  apps: string;
  /** Texto mostrado cuando no hay apps. */
  empty: string;
  /** aria-label del botón de cerrar. */
  close: string;
}

const DEFAULT_LABELS: OkAppLauncherLabels = {
  apps: 'Apps',
  empty: 'No apps',
  close: 'Close',
};

export class OkAppLauncher extends LitElement {
  static styles = css`
    :host {
      /* Vars overridable (estilo Ionic), default = cadena --ok-* → --ion-* → hex */
      --color: var(--ok-text, var(--ion-text-color, #1c1b17));
      --color-muted: var(--ok-text-muted, rgba(var(--ion-text-color-rgb, 28, 27, 23), 0.6));
      --primary-color: var(--ok-primary, var(--ion-color-primary, #3880ff));
      --primary-contrast: var(--ok-primary-contrast, var(--ion-color-primary-contrast, #ffffff));
      --hover-bg: var(--ok-hover, rgba(var(--ion-text-color-rgb, 28, 27, 23), 0.06));
      --panel-bg: var(--ok-surface, var(--ion-card-background, var(--ion-background-color, #ffffff)));
      --border-color: var(--ok-border, rgba(var(--ion-text-color-rgb, 28, 27, 23), 0.12));
      --border-radius: var(--ok-radius, 12px);
      --shadow: var(--ok-shadow, 0 -8px 28px rgba(0, 0, 0, 0.18));
      --font: var(--ok-font, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif);
      --scrim: var(--ok-scrim, rgba(0, 0, 0, 0.4));

      /* INLINE: solo lo que mide el botón. */
      display: inline-block;
      position: relative;
      color: var(--color);
      font-family: var(--font);
    }
    /* Disparador: botón con icono de rejilla. */
    .trigger {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 40px;
      height: 40px;
      padding: 0;
      border: 0;
      background: none;
      color: inherit;
      cursor: pointer;
      border-radius: 50%;
      transition: background-color var(--ok-transition, 150ms ease), color var(--ok-transition, 150ms ease),
        border-color var(--ok-transition, 150ms ease), box-shadow var(--ok-transition, 150ms ease),
        transform 120ms ease;
    }
    @media (hover: hover) {
      .trigger:hover {
        background: var(--hover-bg);
      }
    }
    .trigger:active {
      transform: scale(var(--ok-press-scale, 0.97));
    }
    .trigger ion-icon {
      font-size: 1.4rem;
    }

    /* Scrim a pantalla completa tras la hoja. */
    .scrim {
      position: fixed;
      inset: 0;
      z-index: 1000;
      background: var(--scrim);
      opacity: 0;
      transition: opacity var(--ok-transition, 200ms ease);
    }
    .scrim.shown {
      opacity: 1;
    }

    /* Hoja de acción: anclada abajo, full-width, esquinas superiores redondeadas, desliza hacia
       arriba. position:fixed para cubrir el viewport con independencia de los ancestros. */
    .sheet {
      position: fixed;
      left: 0;
      right: 0;
      bottom: 0;
      z-index: 1001;
      max-height: 85vh;
      overflow-y: auto;
      padding: 0.5rem 1rem calc(1rem + env(safe-area-inset-bottom, 0px));
      background: var(--panel-bg);
      border-top-left-radius: var(--ok-sheet-radius, 16px);
      border-top-right-radius: var(--ok-sheet-radius, 16px);
      box-shadow: var(--shadow);
      box-sizing: border-box;
      transform: translateY(100%);
      transition: transform var(--ok-transition, 260ms cubic-bezier(0.32, 0.72, 0, 1));
    }
    .sheet.shown {
      transform: translateY(0);
    }
    @media (prefers-reduced-motion: reduce) {
      .scrim,
      .sheet {
        transition: none;
      }
    }
    /* Barra/agarre superior, decorativa (estilo sheet modal de Ionic). */
    .handle {
      width: 36px;
      height: 5px;
      margin: 0.25rem auto 0.5rem;
      border-radius: 999px;
      background: var(--border-color);
    }
    /* Cabecera de la hoja: título + botón cerrar. */
    .head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 0.5rem;
      padding: 0 0.25rem 0.5rem;
    }
    .head .title {
      font-size: 0.95rem;
      font-weight: 600;
      color: var(--color);
    }
    .close-btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 34px;
      height: 34px;
      padding: 0;
      border: 0;
      background: none;
      color: var(--color-muted);
      cursor: pointer;
      border-radius: 50%;
      transition: background-color var(--ok-transition, 150ms ease);
    }
    @media (hover: hover) {
      .close-btn:hover {
        background: var(--hover-bg);
      }
    }
    .close-btn ion-icon {
      font-size: 1.3rem;
    }

    /* Rejilla de apps: auto-fit en función del ancho (más columnas en pantallas anchas). */
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(84px, 1fr));
      gap: 0.5rem;
      padding-bottom: 0.25rem;
    }
    .app {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 0.4rem;
      padding: 0.75rem 0.3rem;
      border: 0;
      background: none;
      color: inherit;
      font: inherit;
      cursor: pointer;
      border-radius: 12px;
      text-align: center;
      text-decoration: none;
      transition: background-color var(--ok-transition, 150ms ease), color var(--ok-transition, 150ms ease),
        border-color var(--ok-transition, 150ms ease), box-shadow var(--ok-transition, 150ms ease),
        transform 120ms ease;
    }
    @media (hover: hover) {
      .app:hover {
        background: var(--hover-bg);
        transform: translateY(-1px);
      }
    }
    .app:active {
      transform: scale(var(--ok-press-scale, 0.97));
    }
    @media (prefers-reduced-motion: reduce) {
      .trigger:hover,
      .trigger:active,
      .app:hover,
      .app:active {
        transform: none;
      }
    }
    /* Cuadro del icono grande (color de la app o primary por defecto). */
    .app .box {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 52px;
      height: 52px;
      border-radius: 14px;
      background: var(--app-color, var(--primary-color));
      color: var(--primary-contrast);
    }
    .app .box ion-icon {
      font-size: 1.7rem;
    }
    .app .label {
      font-size: 0.78rem;
      line-height: 1.2;
      color: var(--color-muted);
      max-width: 100%;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .empty {
      padding: 1.5rem 0.75rem;
      font-size: 0.85rem;
      color: var(--color-muted);
      text-align: center;
    }
  `;

  /** Apps a mostrar en la rejilla. */
  @property({ attribute: false }) apps: OkLauncherApp[] = [];
  /** Textos traducibles (merge sobre los defaults en inglés). */
  @property({ attribute: false }) labels: Partial<OkAppLauncherLabels> = {};

  // Textos efectivos: defaults en inglés + overrides del consumidor.
  private get t(): OkAppLauncherLabels {
    return { ...DEFAULT_LABELS, ...this.labels };
  }

  // Estado interno: hoja montada en el DOM.
  @state() private open = false;
  // Estado interno: hoja visible (clase para disparar la transición de entrada/salida).
  @state() private shown = false;

  // Handler de tecla (Esc cierra).
  private readonly onKeydown = (e: KeyboardEvent): void => {
    if (e.key === 'Escape') this.close();
  };

  // Portal del overlay en `document.body` (shadow propio). El scrim + la hoja se renderizan AQUÍ,
  // no en el shadow del host, para que el `position:fixed` se ancle al viewport y no a un ancestro
  // transformado (Ionic pone `transform` en `ion-buttons`/`ion-router-outlet`).
  private portalRoot: ShadowRoot | null = null;

  disconnectedCallback(): void {
    super.disconnectedCallback();
    this.unbind();
    // Limpia el portal del body (si quedó montado) para no dejar nodos huérfanos.
    const host = this.portalRoot?.host;
    this.portalRoot = null;
    if (host && host.parentNode) host.parentNode.removeChild(host);
  }

  // Crea (una vez) el portal: un div en `document.body` con shadow propio que ADOPTA la misma hoja
  // de estilos del componente, de modo que `.scrim`/`.sheet`/`.app` se ven idénticos fuera del host.
  private ensurePortal(): ShadowRoot {
    if (this.portalRoot) return this.portalRoot;
    const host = document.createElement('div');
    host.setAttribute('data-ok-app-launcher-portal', '');
    document.body.appendChild(host);
    const root = host.attachShadow({ mode: 'open' });
    const styles = (this.constructor as typeof OkAppLauncher).elementStyles ?? [];
    root.adoptedStyleSheets = styles
      .map((s) => (s instanceof CSSStyleSheet ? s : s.styleSheet))
      .filter((s): s is CSSStyleSheet => !!s);
    this.portalRoot = root;
    return root;
  }

  // Renderiza el overlay (o nada) en el portal. Se llama tras cada update del host. No crea el
  // portal hasta la primera apertura (evita divs vacíos en el body por cada launcher montado).
  protected updated(): void {
    if (!this.open && !this.portalRoot) return;
    render(this.open ? this.overlayTemplate() : nothing, this.ensurePortal());
  }

  private bind(): void {
    document.addEventListener('keydown', this.onKeydown);
  }

  private unbind(): void {
    document.removeEventListener('keydown', this.onKeydown);
  }

  private toggle(): void {
    this.open ? this.close() : this.openSheet();
  }

  private openSheet(): void {
    if (this.open) return;
    this.open = true;
    this.bind();
    // Tras montar la hoja, en el siguiente frame activamos la clase para deslizarla hacia arriba.
    requestAnimationFrame(() => requestAnimationFrame(() => (this.shown = true)));
    this.dispatchEvent(
      new CustomEvent('ok-open', { detail: { open: true }, bubbles: true, composed: true }),
    );
  }

  private close(): void {
    if (!this.open) return;
    this.unbind();
    // Animamos la salida: quitamos la clase y desmontamos al terminar la transición.
    this.shown = false;
    const sheet = this.portalRoot?.querySelector('.sheet') as HTMLElement | null;
    const finish = (): void => {
      this.open = false;
    };
    if (sheet && !this.prefersReducedMotion()) {
      sheet.addEventListener('transitionend', finish, { once: true });
    } else {
      finish();
    }
    this.dispatchEvent(
      new CustomEvent('ok-open', { detail: { open: false }, bubbles: true, composed: true }),
    );
  }

  private prefersReducedMotion(): boolean {
    return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;
  }

  // Selecciona una app: si tiene `href` navega; si no, emite `ok-app-select`. Siempre cierra.
  private selectApp(app: OkLauncherApp): void {
    if (app.href) {
      this.close();
      window.location.href = app.href;
      return;
    }
    this.dispatchEvent(
      new CustomEvent('ok-app-select', {
        detail: { id: app.id, app },
        bubbles: true,
        composed: true,
      }),
    );
    this.close();
  }

  // Un icono es «SVG ya resuelto» si es un string `<svg…>` o un `data:` URI; entonces va a la
  // prop `icon` de ion-icon (no a `name`), que es como los hosts con iconos horneados/offline
  // los pintan sin tocar la red.
  private isResolvedSvg(icon: string): boolean {
    return /^\s*</.test(icon) || icon.startsWith('data:');
  }

  private renderApp(app: OkLauncherApp): unknown {
    const boxStyle = app.color ? `--app-color:${app.color}` : '';
    const icon = app.icon ?? 'apps-outline';
    return html`<button
      type="button"
      class="app"
      style=${boxStyle}
      role="menuitem"
      @click=${() => this.selectApp(app)}
    >
      <span class="box">
        ${this.isResolvedSvg(icon)
          ? html`<ion-icon .icon=${icon}></ion-icon>`
          : html`<ion-icon .name=${icon}></ion-icon>`}
      </span>
      <span class="label">${app.label}</span>
    </button>`;
  }

  render(): unknown {
    // Solo el disparador vive en el shadow del host; el overlay se renderiza en el portal del body.
    return html`
      <button
        type="button"
        class="trigger"
        aria-haspopup="menu"
        aria-expanded=${this.open ? 'true' : 'false'}
        aria-label=${this.t.apps}
        @click=${() => this.toggle()}
      >
        <ion-icon name="apps-outline"></ion-icon>
      </button>
    `;
  }

  // Overlay (scrim + hoja inferior). Se renderiza en el portal de `document.body` vía `updated()`.
  private overlayTemplate(): unknown {
    return html`
      <div class="scrim ${this.shown ? 'shown' : ''}" @click=${() => this.close()}></div>
      <div class="sheet ${this.shown ? 'shown' : ''}" role="menu" aria-label=${this.t.apps}>
        <div class="handle"></div>
        <div class="head">
          <span class="title">${this.t.apps}</span>
          <button
            type="button"
            class="close-btn"
            aria-label=${this.t.close}
            @click=${() => this.close()}
          >
            <ion-icon name="close-outline"></ion-icon>
          </button>
        </div>
        ${this.apps.length
          ? html`<div class="grid">${this.apps.map((app) => this.renderApp(app))}</div>`
          : html`<div class="empty">${this.t.empty}</div>`}
      </div>
    `;
  }
}

define('ok-app-launcher', OkAppLauncher);

declare global {
  interface HTMLElementTagNameMap {
    'ok-app-launcher': OkAppLauncher;
  }
}
