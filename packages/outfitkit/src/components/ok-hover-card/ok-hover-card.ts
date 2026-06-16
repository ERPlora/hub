import { LitElement, html, css, nothing } from 'lit';
import { property, state, query } from 'lit/decorators.js';
import { define } from '../../base/define.js';
import { computeAnchor } from '../../base/anchor.js';

// Una estadística de la fila de 3 cifras tabulares (pie de la tarjeta).
export interface OkHoverCardStat {
  /** Cifra destacada (negrita, tabular). */
  value: string;
  /** Etiqueta muted bajo la cifra. */
  label: string;
}

// Un botón del pie de la tarjeta (máx. 2). El primero es secundario; marca `brand` para el realce.
export interface OkHoverCardAction {
  /** Identificador del botón (se emite en `ok-action`). */
  id: string;
  /** Texto del botón. */
  label: string;
  /** Si está, al hacer click navega a esta URL en lugar de emitir evento. */
  href?: string;
  /** Realce de marca (botón primario). */
  brand?: boolean;
}

// Colocación preferida del popover respecto al disparador.
export type OkHoverCardPlacement = 'bottom' | 'top';

// ok-hover-card — popover RICA de previsualización anclada al hover/focus de un disparador inline.
// Pensado para @menciones / referencias cruzadas de entidades (perfiles, documentos): al pasar el
// ratón o enfocar el texto-ancla aparece una tarjeta con avatar, título + badge, @handle, cuerpo,
// una fila de 3 cifras tabulares y un pie de hasta 2 botones.
//
// AUTOCONTENIDO y CSP-safe: el disparador va en el slot por defecto; el contenido es declarativo por
// props (con `slot="content"` opcional para sobrescribir el cuerpo). El panel es `position:absolute`
// relativo al host (NUNCA `fixed`, para no romperse bajo ancestros con `transform`) y usa
// `computeAnchor` para voltear arriba/derecha según el espacio del viewport.
//
// Revelado al hover o focus-within con fade + translate-in; se oculta al salir tras `closeDelay`
// (cancela si el ratón vuelve a entrar en el disparador o en la propia tarjeta).
//
// Eventos (bubbles + composed):
//   • `ok-action` detail { id, action } — click en un botón del pie (sin `href`)
//   • `ok-open`   detail { open }       — la tarjeta se mostró/ocultó

// Textos traducibles (default inglés). Pásalos vía la prop `labels`.
export interface OkHoverCardLabels {
  /** aria-label de la tarjeta (cuando no hay título). */
  card: string;
}

const DEFAULT_LABELS: OkHoverCardLabels = {
  card: 'Preview',
};

export class OkHoverCard extends LitElement {
  static styles = css`
    :host {
      /* Tokens propios estilo Ionic, default = cadena --ok-* → --ion-* → hex. */
      --color: var(--ok-text-color, var(--ion-text-color, #1c1b17));
      --color-muted: var(--ok-color-medium, var(--ion-color-medium, #6b6b76));
      --color-faint: var(--ok-color-medium, var(--ion-color-step-450, #92949c));
      --panel-bg: var(--ok-surface, var(--ion-card-background, var(--ion-background-color, #ffffff)));
      --avatar-bg: var(--ok-hover, rgba(var(--ion-text-color-rgb, 28, 27, 23), 0.06));
      --border-color: var(--ok-border, rgba(var(--ion-text-color-rgb, 28, 27, 23), 0.12));
      --border-soft: var(--ok-border-soft, rgba(var(--ion-text-color-rgb, 28, 27, 23), 0.08));
      --primary-color: var(--ok-primary, var(--ion-color-primary, #3880ff));
      --primary-contrast: var(--ok-primary-contrast, var(--ion-color-primary-contrast, #ffffff));
      --primary-shade: var(--ok-primary-shade, var(--ion-color-primary-shade, #3171e0));
      --action-bg: var(--ok-hover, rgba(var(--ion-text-color-rgb, 28, 27, 23), 0.05));
      --action-bg-hover: var(--ok-hover-strong, rgba(var(--ion-text-color-rgb, 28, 27, 23), 0.1));
      --radius: var(--ok-radius, 12px);
      --radius-sm: var(--ok-radius-sm, 7px);
      --shadow: var(--ok-shadow, 0 12px 32px rgba(0, 0, 0, 0.16));
      --font: var(--ok-font, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif);
      --font-mono: var(--ok-font-mono, ui-monospace, 'SF Mono', 'Menlo', monospace);
      --width: var(--ok-hover-card-width, 280px);

      /* INLINE: el host envuelve solo el disparador en línea con el texto. */
      display: inline;
      position: relative;
      font-family: var(--font);
    }

    /* Ancla: contenedor inline del disparador (slot por defecto). */
    .trigger {
      display: inline;
      position: relative;
    }

    /* Panel flotante. position:absolute relativo al host (no fixed). */
    .card {
      position: absolute;
      top: 100%;
      left: 0;
      z-index: 1000;
      width: var(--width);
      max-width: calc(100vw - 24px);
      margin-top: 8px;
      box-sizing: border-box;
      padding: 14px;
      background: var(--panel-bg);
      border: 1px solid var(--border-color);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
      font-size: 0.8125rem;
      color: var(--color-muted);
      line-height: 1.5;
      text-align: left;
      cursor: default;
      /* Estado oculto: invisible y no interactivo, listo para animar. */
      opacity: 0;
      transform: translateY(4px);
      pointer-events: none;
      transition: opacity var(--ok-transition, 160ms ease), transform var(--ok-transition, 160ms ease);
    }
    /* Abre hacia la izquierda (alinea borde derecho con el del disparador). */
    .card.end {
      left: auto;
      right: 0;
    }
    /* Abre hacia arriba. */
    .card.above {
      top: auto;
      bottom: 100%;
      margin-top: 0;
      margin-bottom: 8px;
      transform: translateY(-4px);
    }
    .card.shown {
      opacity: 1;
      transform: translateY(0);
      pointer-events: auto;
    }
    @media (prefers-reduced-motion: reduce) {
      .card {
        transition: opacity 120ms ease;
        transform: none;
      }
      .card.above {
        transform: none;
      }
    }

    /* Cabecera: avatar + título/handle. */
    .head {
      display: flex;
      align-items: flex-start;
      gap: 10px;
      margin-bottom: 8px;
    }
    .avatar {
      width: 38px;
      height: 38px;
      flex-shrink: 0;
      border-radius: 10px;
      background: var(--avatar-bg);
      display: grid;
      place-items: center;
      overflow: hidden;
      font-weight: 600;
      font-size: 13px;
      color: var(--color);
    }
    .avatar img {
      width: 100%;
      height: 100%;
      object-fit: cover;
    }
    .title {
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: 6px;
      font-weight: 600;
      font-size: 0.9375rem;
      letter-spacing: -0.01em;
      color: var(--color);
    }
    /* Badge inline junto al título (estilo brand). */
    .badge {
      display: inline-flex;
      align-items: center;
      padding: 1px 7px;
      border-radius: 999px;
      font-size: 0.6875rem;
      font-weight: 600;
      line-height: 1.4;
      background: var(--primary-color);
      color: var(--primary-contrast);
    }
    .handle {
      margin-top: 1px;
      font-family: var(--font-mono);
      font-size: 0.6875rem;
      color: var(--color-faint);
    }

    .body {
      font-size: 0.8125rem;
      color: var(--color-muted);
      line-height: 1.5;
    }
    ::slotted([slot='content']) {
      font-size: 0.8125rem;
      color: var(--color-muted);
      line-height: 1.5;
    }

    /* Fila de 3 cifras tabulares. */
    .stats {
      display: flex;
      gap: 14px;
      margin-top: 10px;
      padding-top: 10px;
      border-top: 1px solid var(--border-soft);
      font-size: 0.6875rem;
      color: var(--color-faint);
    }
    .stat b {
      display: block;
      font-size: 0.875rem;
      font-weight: 600;
      color: var(--color);
      font-variant-numeric: tabular-nums;
    }

    /* Pie: hasta 2 botones (el realce brand). */
    .footer {
      display: flex;
      gap: 6px;
      margin-top: 10px;
    }
    .action {
      flex: 1;
      height: 28px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      padding: 0 8px;
      border: 1px solid var(--border-color);
      border-radius: var(--radius-sm);
      background: var(--action-bg);
      color: var(--color);
      font: inherit;
      font-size: 0.6875rem;
      font-weight: 500;
      text-decoration: none;
      cursor: pointer;
      transition: background-color var(--ok-transition, 150ms ease),
        border-color var(--ok-transition, 150ms ease);
    }
    @media (hover: hover) {
      .action:hover {
        background: var(--action-bg-hover);
      }
    }
    .action.brand {
      background: var(--primary-color);
      border-color: var(--primary-color);
      color: var(--primary-contrast);
    }
    @media (hover: hover) {
      .action.brand:hover {
        background: var(--primary-shade);
        border-color: var(--primary-shade);
      }
    }
  `;

  /** Nombre mostrado (título de la tarjeta). */
  @property() name?: string;
  /** Badge opcional junto al título (p. ej. rol). */
  @property() badge?: string;
  /** @handle / línea secundaria (mono, muted). */
  @property() handle?: string;
  /** Iniciales o texto del avatar (si no hay `avatarSrc`). */
  @property() avatar?: string;
  /** URL de imagen del avatar (sobrescribe `avatar`). */
  @property({ attribute: 'avatar-src' }) avatarSrc?: string;
  /** Texto del cuerpo (si no se usa `slot="content"`). */
  @property() body?: string;
  /** Fila de cifras tabulares (hasta 3). */
  @property({ attribute: false }) stats: OkHoverCardStat[] = [];
  /** Botones del pie (hasta 2). */
  @property({ attribute: false }) actions: OkHoverCardAction[] = [];
  /** Colocación preferida (se voltea si no cabe). */
  @property() placement: OkHoverCardPlacement = 'bottom';
  /** Retardo (ms) antes de abrir al entrar el hover. */
  @property({ type: Number, attribute: 'open-delay' }) openDelay = 220;
  /** Retardo (ms) antes de cerrar al salir el hover. */
  @property({ type: Number, attribute: 'close-delay' }) closeDelay = 180;
  /** Textos traducibles (merge sobre los defaults en inglés). */
  @property({ attribute: false }) labels: Partial<OkHoverCardLabels> = {};

  // Tarjeta montada (en el DOM, aún quizá oculta para animar la salida).
  @state() private open = false;
  // Tarjeta visible (clase que dispara la transición de entrada).
  @state() private shown = false;
  // Lados resueltos por computeAnchor.
  @state() private end = false;
  @state() private above = false;

  @query('.card') private cardEl?: HTMLElement;
  @query('.trigger') private triggerEl?: HTMLElement;

  private openTimer?: number;
  private closeTimer?: number;

  // Textos efectivos: defaults en inglés + overrides del consumidor.
  private get t(): OkHoverCardLabels {
    return { ...DEFAULT_LABELS, ...this.labels };
  }

  disconnectedCallback(): void {
    super.disconnectedCallback();
    this.clearTimers();
  }

  private clearTimers(): void {
    if (this.openTimer) window.clearTimeout(this.openTimer);
    if (this.closeTimer) window.clearTimeout(this.closeTimer);
    this.openTimer = undefined;
    this.closeTimer = undefined;
  }

  // Programa la apertura tras `openDelay` (cancela cualquier cierre pendiente).
  private scheduleOpen(): void {
    if (this.closeTimer) {
      window.clearTimeout(this.closeTimer);
      this.closeTimer = undefined;
    }
    if (this.open) return;
    if (this.openTimer) return;
    this.openTimer = window.setTimeout(() => {
      this.openTimer = undefined;
      this.show();
    }, Math.max(0, this.openDelay));
  }

  // Programa el cierre tras `closeDelay` (cancela cualquier apertura pendiente).
  private scheduleClose(): void {
    if (this.openTimer) {
      window.clearTimeout(this.openTimer);
      this.openTimer = undefined;
    }
    if (!this.open) return;
    if (this.closeTimer) return;
    this.closeTimer = window.setTimeout(() => {
      this.closeTimer = undefined;
      this.hide();
    }, Math.max(0, this.closeDelay));
  }

  private show(): void {
    if (this.open) return;
    this.open = true;
    this.dispatchEvent(
      new CustomEvent('ok-open', { detail: { open: true }, bubbles: true, composed: true }),
    );
    // Tras montar la tarjeta: medir/anclar y, en el siguiente frame, activar la clase de entrada.
    requestAnimationFrame(() => {
      this.anchor();
      requestAnimationFrame(() => (this.shown = true));
    });
  }

  private hide(): void {
    if (!this.open) return;
    // Animamos la salida: quitamos la clase y desmontamos al terminar la transición.
    this.shown = false;
    const card = this.cardEl;
    const finish = (): void => {
      this.open = false;
    };
    if (card && !this.prefersReducedMotion()) {
      card.addEventListener('transitionend', finish, { once: true });
    } else {
      finish();
    }
    this.dispatchEvent(
      new CustomEvent('ok-open', { detail: { open: false }, bubbles: true, composed: true }),
    );
  }

  // Resuelve los lados (derecha/arriba) con computeAnchor; respeta la `placement` preferida.
  private anchor(): void {
    const trigger = this.triggerEl;
    const card = this.cardEl;
    if (!trigger || !card) return;
    const { end, above } = computeAnchor(trigger, card, { gap: 8, margin: 12 });
    this.end = end;
    // Si se prefiere arriba, abre arriba salvo que computeAnchor diga que no cabe (devuelve above
    // solo cuando no hay sitio debajo y sí encima). Para preferir-arriba forzamos cuando cabe.
    this.above = this.placement === 'top' ? !this.fitsBelow() || above : above;
  }

  // ¿Cabe la tarjeta debajo del disparador dentro del viewport?
  private fitsBelow(): boolean {
    const trigger = this.triggerEl;
    const card = this.cardEl;
    if (!trigger || !card) return true;
    const t = trigger.getBoundingClientRect();
    const p = card.getBoundingClientRect();
    return t.bottom + 8 + p.height <= window.innerHeight - 12;
  }

  private prefersReducedMotion(): boolean {
    return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;
  }

  // Esc oculta inmediatamente (accesibilidad de teclado).
  private readonly onKeydown = (e: KeyboardEvent): void => {
    if (e.key === 'Escape' && this.open) {
      this.clearTimers();
      this.hide();
    }
  };

  // Click en un botón del pie: si tiene `href` navega; si no, emite `ok-action`. Cierra siempre.
  private runAction(action: OkHoverCardAction): void {
    if (action.href) {
      window.location.href = action.href;
      return;
    }
    this.dispatchEvent(
      new CustomEvent('ok-action', {
        detail: { id: action.id, action },
        bubbles: true,
        composed: true,
      }),
    );
    this.clearTimers();
    this.hide();
  }

  private renderAvatar(): unknown {
    if (this.avatarSrc) {
      return html`<img src=${this.avatarSrc} alt="" />`;
    }
    return this.avatar ?? '';
  }

  render(): unknown {
    const hasStats = this.stats.length > 0;
    const hasActions = this.actions.length > 0;
    const cardCls = `card${this.shown ? ' shown' : ''}${this.end ? ' end' : ''}${
      this.above ? ' above' : ''
    }`;
    return html`
      <span
        class="trigger"
        @mouseenter=${() => this.scheduleOpen()}
        @mouseleave=${() => this.scheduleClose()}
        @focusin=${() => this.scheduleOpen()}
        @focusout=${() => this.scheduleClose()}
        @keydown=${this.onKeydown}
      >
        <slot></slot>
        ${this.open
          ? html`
              <span
                class=${cardCls}
                role="dialog"
                aria-label=${this.name ?? this.t.card}
                @mouseenter=${() => this.scheduleOpen()}
                @mouseleave=${() => this.scheduleClose()}
              >
                <span class="head">
                  <span class="avatar">${this.renderAvatar()}</span>
                  <span>
                    ${this.name
                      ? html`<span class="title"
                          >${this.name}${this.badge
                            ? html`<span class="badge">${this.badge}</span>`
                            : nothing}</span
                        >`
                      : nothing}
                    ${this.handle ? html`<span class="handle">${this.handle}</span>` : nothing}
                  </span>
                </span>
                <slot name="content"
                  >${this.body ? html`<span class="body">${this.body}</span>` : nothing}</slot
                >
                ${hasStats
                  ? html`<span class="stats">
                      ${this.stats.slice(0, 3).map(
                        (s) => html`<span class="stat"><b>${s.value}</b>${s.label}</span>`,
                      )}
                    </span>`
                  : nothing}
                ${hasActions
                  ? html`<span class="footer">
                      ${this.actions.slice(0, 2).map((a) =>
                        a.href
                          ? html`<a
                              class="action${a.brand ? ' brand' : ''}"
                              href=${a.href}
                              @click=${() => this.clearTimers()}
                              >${a.label}</a
                            >`
                          : html`<button
                              type="button"
                              class="action${a.brand ? ' brand' : ''}"
                              @click=${() => this.runAction(a)}
                            >
                              ${a.label}
                            </button>`,
                      )}
                    </span>`
                  : nothing}
              </span>
            `
          : nothing}
      </span>
    `;
  }
}

define('ok-hover-card', OkHoverCard);

declare global {
  interface HTMLElementTagNameMap {
    'ok-hover-card': OkHoverCard;
  }
}
