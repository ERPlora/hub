import { LitElement, html, css } from 'lit';
import { property, state } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// ok-error-page — plantilla full-screen para errores HTTP/arranque (403/404/500…).
// Fondo cuadriculado, ilustración por variante, código + título + mensaje,
// slots de acciones/búsqueda, tiles de atajos (array), <details> con traza,
// chip de reintento con cuenta atrás (attribute-driven) y, en modo bootstrap,
// una checklist de verificaciones de salud con iconos de estado.
// Backend-agnostic: solo props/arrays; los strings/links los pone el host.

/** Variante de acento/color de la página. */
export type OkErrorPageVariant = 'info' | 'warn' | 'danger';

/** Modo de presentación: error HTTP normal o pantalla de arranque (health-check). */
export type OkErrorPageMode = 'http' | 'bootstrap';

/** Estado de una verificación de arranque. */
export type OkErrorCheckStatus = 'ok' | 'fail' | 'pending';

/** Tile de atajo (card-link) que aparece bajo el mensaje. */
export interface OkErrorShortcut {
  /** Texto principal del tile. */
  title: string;
  /** Descripción secundaria opcional. */
  desc?: string;
  /** Destino del enlace (si se omite, se renderiza como botón sin href). */
  href?: string;
  /** Nombre de icono Ionic opcional (ion-icon name). */
  icon?: string;
}

/** Una verificación de salud en modo bootstrap. */
export interface OkErrorCheck {
  /** Nombre de la dependencia/comprobación. */
  name: string;
  /** Mensaje/detalle opcional. */
  message?: string;
  /** Estado de la comprobación. */
  status?: OkErrorCheckStatus;
  /** Tiempo/duración opcional (ej. "142 ms", "timeout"). */
  time?: string;
}

export class OkErrorPage extends LitElement {
  static styles = css`
    :host {
      display: block;
      width: 100%;
      /* Tokens propios estilo Ionic (overridables): --ok-* → --ion-* → hex. */
      --bg: var(--ok-background-color, var(--ion-background-color, #f6f7f9));
      --surface: var(--ok-surface, var(--ion-card-background, #ffffff));
      --surface-2: var(--ok-surface-2, #f1f2f4);
      --ink: var(--ok-text-color, var(--ion-text-color, #1f2933));
      --ink-2: var(--ok-color-medium-shade, #5b5f66);
      --ink-3: var(--ok-color-medium, var(--ion-color-medium, #92949c));
      --line: var(--ok-border-color, var(--ion-border-color, #e3e5e8));
      --line-2: var(--ok-border-color-shade, #c9ccd1);
      --radius: var(--ok-radius, 12px);
      --radius-pill: var(--ok-radius-pill, 999px);
      --font-mono: var(--ok-font-mono, ui-monospace, SFMono-Regular, Menlo, monospace);
      --info: var(--ok-color-primary, var(--ion-color-primary, #3880ff));
      --warn: var(--ok-color-warning, var(--ion-color-warning, #ffc409));
      --danger: var(--ok-color-danger, var(--ion-color-danger, #eb445a));
      --ok-leaf: var(--ok-color-success, var(--ion-color-success, #2dd36f));
      /* Acento resuelto por variante (se sobreescribe en :host([variant=…])). */
      --accent: var(--info);
    }

    :host([variant='warn']) { --accent: var(--warn); }
    :host([variant='danger']) { --accent: var(--danger); }

    .page {
      position: relative;
      min-height: 100vh;
      min-height: 100dvh;
      display: grid;
      place-items: center;
      padding: 2.5rem 1.25rem;
      background:
        radial-gradient(ellipse 80% 60% at 50% 0%,
          color-mix(in srgb, var(--accent) 6%, transparent), transparent 60%),
        var(--bg);
      color: var(--ink);
      overflow: hidden;
      box-sizing: border-box;
    }

    /* Rejilla de fondo con máscara radial. */
    .page::before {
      content: '';
      position: absolute;
      inset: 0;
      background-image:
        linear-gradient(to right, color-mix(in srgb, var(--line) 55%, transparent) 1px, transparent 1px),
        linear-gradient(to bottom, color-mix(in srgb, var(--line) 55%, transparent) 1px, transparent 1px);
      background-size: 48px 48px;
      -webkit-mask-image: radial-gradient(ellipse 60% 60% at 50% 50%, black, transparent 80%);
      mask-image: radial-gradient(ellipse 60% 60% at 50% 50%, black, transparent 80%);
      pointer-events: none;
      opacity: 0.6;
    }

    .inner {
      position: relative;
      z-index: 1;
      display: grid;
      gap: 1.25rem;
      text-align: center;
      max-width: 560px;
      width: 100%;
    }

    /* Ilustración circular. */
    .illu {
      display: grid;
      place-items: center;
      width: 96px;
      height: 96px;
      margin-inline: auto;
      border-radius: 50%;
      background: color-mix(in srgb, var(--accent) 9%, var(--surface));
      color: var(--accent);
      border: 1px solid color-mix(in srgb, var(--accent) 28%, transparent);
    }
    .illu svg { width: 44px; height: 44px; }

    .code {
      font-family: var(--font-mono);
      font-size: 0.875rem;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: var(--ink-3);
      margin: 0;
    }

    .title {
      font-size: clamp(1.75rem, 4vw, 2.5rem);
      font-weight: 700;
      line-height: 1.15;
      letter-spacing: -0.01em;
      margin: 0;
    }

    .msg {
      color: var(--ink-2);
      font-size: 1.0625rem;
      line-height: 1.5;
      margin: 0;
      max-width: 44ch;
      margin-inline: auto;
    }

    /* Slot de búsqueda (ej. "did you mean" en 404). */
    .search {
      max-width: 380px;
      margin: 0 auto;
      width: 100%;
    }
    .search ::slotted(*) { width: 100%; }

    /* Chip de reintento con cuenta atrás. */
    .retry {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      justify-self: center;
      padding: 6px 12px;
      border-radius: var(--radius-pill);
      background: color-mix(in srgb, var(--accent) 9%, var(--surface));
      border: 1px solid color-mix(in srgb, var(--accent) 28%, transparent);
      font-size: 0.875rem;
      color: var(--ink-2);
    }
    .retry-num {
      font-family: var(--font-mono);
      font-weight: 700;
      color: var(--accent);
      min-width: 1.5em;
      text-align: center;
    }
    .retry-bar {
      width: 100%;
      max-width: 240px;
      margin: 0 auto;
      height: 4px;
      border-radius: 2px;
      background: var(--surface-2);
      overflow: hidden;
    }
    .retry-fill {
      height: 100%;
      background: var(--accent);
      transition: width 0.25s linear;
    }

    /* Grid de tiles de atajo. */
    .shortcuts {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 0.5rem;
      max-width: 520px;
      margin: 0 auto;
      width: 100%;
    }
    .shortcut {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      padding: 12px 14px;
      border-radius: var(--radius);
      background: var(--surface);
      border: 1px solid var(--line);
      color: var(--ink);
      text-decoration: none;
      font-size: 0.875rem;
      text-align: left;
      cursor: pointer;
      font-family: inherit;
      transition: border-color 0.15s, background 0.15s, transform 0.15s;
    }
    .shortcut:hover {
      border-color: var(--line-2);
      background: var(--surface-2);
      transform: translateY(-1px);
    }
    .shortcut ion-icon {
      font-size: 18px;
      min-width: 18px;
      color: var(--ink-3);
      flex-shrink: 0;
    }
    .shortcut-body { min-width: 0; }
    .shortcut-title {
      font-weight: 600;
      color: var(--ink);
      display: block;
      line-height: 1.3;
    }
    .shortcut-desc {
      display: block;
      margin-top: 2px;
      font-size: 11px;
      color: var(--ink-3);
      line-height: 1.3;
    }

    /* Checklist de diagnóstico (modo bootstrap). */
    .diagnosis {
      display: flex;
      flex-direction: column;
      gap: 6px;
      max-width: 480px;
      margin: 0 auto;
      width: 100%;
      list-style: none;
      padding: 0;
      text-align: left;
    }
    .check {
      display: grid;
      grid-template-columns: 20px 1fr auto;
      gap: 12px;
      align-items: center;
      padding: 12px;
      border-radius: var(--radius);
      background: var(--surface);
      border: 1px solid var(--line);
      font-size: 0.875rem;
      color: var(--ink-2);
    }
    .check[data-status='ok'] { border-color: color-mix(in srgb, var(--ok-leaf) 28%, transparent); }
    .check[data-status='fail'] {
      border-color: color-mix(in srgb, var(--danger) 35%, transparent);
      background: color-mix(in srgb, var(--danger) 5%, var(--surface));
    }
    .check[data-status='pending'] { border-color: color-mix(in srgb, var(--warn) 28%, transparent); }
    .check-icon {
      width: 20px;
      height: 20px;
      display: grid;
      place-items: center;
      color: var(--ink-3);
    }
    .check-icon svg { width: 20px; height: 20px; }
    .check[data-status='ok'] .check-icon { color: var(--ok-leaf); }
    .check[data-status='fail'] .check-icon { color: var(--danger); }
    .check[data-status='pending'] .check-icon { color: var(--warn); }
    .check-body { min-width: 0; }
    .check-name { font-weight: 600; font-size: 0.875rem; color: var(--ink); }
    .check-msg { color: var(--ink-3); font-size: 12px; margin-top: 1px; }
    .check-time {
      font-family: var(--font-mono);
      font-size: 11px;
      color: var(--ink-3);
      white-space: nowrap;
    }

    /* <details> con traza técnica. */
    .details {
      max-width: 540px;
      margin: 0 auto;
      width: 100%;
      text-align: left;
      font-size: 0.875rem;
      color: var(--ink-2);
    }
    .details summary {
      cursor: pointer;
      padding: 8px 12px;
      border-radius: var(--radius);
      background: var(--surface);
      border: 1px solid var(--line);
      color: var(--ink-2);
      font-weight: 500;
      user-select: none;
      list-style: none;
    }
    .details summary::-webkit-details-marker { display: none; }
    .details summary::before {
      content: '\\25B8';
      display: inline-block;
      margin-right: 6px;
      transition: transform 0.15s;
    }
    .details[open] summary::before { transform: rotate(90deg); }
    .details summary:hover { border-color: var(--line-2); }
    .trace {
      margin: 0.5rem 0 0;
      padding: 12px 14px;
      border-radius: var(--radius);
      background: var(--surface);
      border: 1px solid var(--line);
      font-family: var(--font-mono);
      font-size: 11px;
      line-height: 1.5;
      color: var(--ink-2);
      white-space: pre-wrap;
      overflow-x: auto;
    }

    /* Acciones (slot) — el host mete sus ion-button. */
    .actions {
      display: flex;
      justify-content: center;
      gap: 0.75rem;
      flex-wrap: wrap;
      margin-top: 0.25rem;
    }
    .actions ::slotted(*) { margin: 0; }

    .meta {
      font-family: var(--font-mono);
      font-size: 12px;
      color: var(--ink-3);
    }

    @media (max-width: 600px) {
      .illu { width: 72px; height: 72px; }
      .illu svg { width: 36px; height: 36px; }
      .shortcuts { grid-template-columns: 1fr 1fr; }
    }

    @media (prefers-reduced-motion: reduce) {
      .shortcut, .retry-fill, .details summary::before { transition: none; }
    }
  `;

  /** Código del error (ej. "404", "500", "403"). En bootstrap suele omitirse. */
  @property() code?: string;

  /** Título destacado. (No opcional para no chocar con HTMLElement.title.) */
  @property() title = '';

  /** Mensaje explicativo. */
  @property() message?: string;

  /** Variante de acento. */
  @property({ reflect: true }) variant: OkErrorPageVariant = 'info';

  /** Modo: error HTTP normal o pantalla de arranque (bootstrap). */
  @property({ reflect: true }) mode: OkErrorPageMode = 'http';

  /** Tiles de atajo (home, soporte, estado…). */
  @property({ attribute: false }) shortcuts: OkErrorShortcut[] = [];

  /** Verificaciones de salud (solo modo bootstrap). */
  @property({ attribute: false }) checks: OkErrorCheck[] = [];

  /** Traza técnica opcional dentro del <details> colapsable. */
  @property() trace?: string;

  /** Texto del summary del <details>. */
  @property({ attribute: 'details-label' }) detailsLabel = 'Detalles técnicos';

  /** Línea de meta (trace id · timestamp) bajo todo. */
  @property() meta?: string;

  /** Etiqueta antes de la cuenta atrás del reintento. */
  @property({ attribute: 'retry-label' }) retryLabel = 'Reintentando en';

  /** Segundos de la cuenta atrás de reintento. Si > 0 muestra el chip + barra. */
  @property({ type: Number, attribute: 'retry-seconds' }) retrySeconds = 0;

  /** Segundos restantes (estado interno del temporizador). */
  @state() private remaining = 0;

  private timer?: ReturnType<typeof setInterval>;
  private initialSeconds = 0;

  connectedCallback(): void {
    super.connectedCallback();
    this.startCountdown();
  }

  disconnectedCallback(): void {
    super.disconnectedCallback();
    this.clearTimer();
  }

  updated(changed: Map<string, unknown>): void {
    if (changed.has('retrySeconds')) {
      this.startCountdown();
    }
  }

  private clearTimer(): void {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = undefined;
    }
  }

  // Arranca/reinicia la cuenta atrás cuando retrySeconds es positivo.
  private startCountdown(): void {
    this.clearTimer();
    const secs = Number(this.retrySeconds) || 0;
    this.initialSeconds = secs;
    this.remaining = secs;
    if (secs <= 0) return;
    this.timer = setInterval(() => {
      if (this.remaining <= 1) {
        this.remaining = 0;
        this.clearTimer();
        // Avisa al host (que decide si recargar/reintentar de verdad).
        this.dispatchEvent(
          new CustomEvent('ok-retry', { bubbles: true, composed: true }),
        );
        return;
      }
      this.remaining -= 1;
    }, 1000);
  }

  // SVG de check según estado (sin libs de iconos; dibujado a mano).
  private checkSvg(status: OkErrorCheckStatus): unknown {
    if (status === 'fail') {
      return html`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
        stroke-width="2" stroke-linecap="round"><path d="M18 6 6 18M6 6l12 12" /></svg>`;
    }
    if (status === 'pending') {
      return html`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
        stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="9" />
        <path d="M8 12h.01M12 12h.01M16 12h.01" /></svg>`;
    }
    return html`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
      stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5" /></svg>`;
  }

  private renderShortcuts(): unknown {
    if (!this.shortcuts?.length) return null;
    return html`
      <div class="shortcuts" role="list">
        ${this.shortcuts.map((s) => {
          const body = html`
            ${s.icon ? html`<ion-icon name=${s.icon} aria-hidden="true"></ion-icon>` : null}
            <span class="shortcut-body">
              <span class="shortcut-title">${s.title}</span>
              ${s.desc ? html`<span class="shortcut-desc">${s.desc}</span>` : null}
            </span>
          `;
          return s.href
            ? html`<a class="shortcut" role="listitem" href=${s.href}>${body}</a>`
            : html`<button class="shortcut" type="button" role="listitem"
                @click=${() => this.emitShortcut(s)}>${body}</button>`;
        })}
      </div>
    `;
  }

  private emitShortcut(shortcut: OkErrorShortcut): void {
    this.dispatchEvent(
      new CustomEvent('ok-shortcut', {
        detail: { shortcut },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private renderChecks(): unknown {
    if (this.mode !== 'bootstrap' || !this.checks?.length) return null;
    return html`
      <ul class="diagnosis">
        ${this.checks.map((c) => {
          const status: OkErrorCheckStatus = c.status ?? 'ok';
          return html`
            <li class="check" data-status=${status}>
              <span class="check-icon" aria-hidden="true">${this.checkSvg(status)}</span>
              <span class="check-body">
                <span class="check-name">${c.name}</span>
                ${c.message ? html`<span class="check-msg">${c.message}</span>` : null}
              </span>
              ${c.time ? html`<span class="check-time">${c.time}</span>` : null}
            </li>
          `;
        })}
      </ul>
    `;
  }

  private renderRetry(): unknown {
    if (this.initialSeconds <= 0) return null;
    const pct = this.initialSeconds > 0
      ? Math.max(0, (this.remaining / this.initialSeconds) * 100)
      : 0;
    return html`
      <div class="retry" role="status" aria-live="polite">
        <span>${this.retryLabel}</span>
        <span class="retry-num">${this.remaining}</span>
        <span>s</span>
      </div>
      <div class="retry-bar" aria-hidden="true">
        <div class="retry-fill" style="width:${pct}%"></div>
      </div>
    `;
  }

  // Ilustración por variante (triángulo de alerta para warn/danger, info en círculo).
  private renderIllu(): unknown {
    const icon = this.variant === 'info'
      ? html`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
          stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="9" /><path d="M12 11v5M12 7.5h.01" /></svg>`
      : html`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
          stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
          <path d="M10.3 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
          <path d="M12 9v4M12 17h.01" /></svg>`;
    return html`<div class="illu" aria-hidden="true">${icon}</div>`;
  }

  render(): unknown {
    return html`
      <main class="page" role="main" aria-labelledby="ok-err-title">
        <div class="inner">
          ${this.renderIllu()}
          ${this.code ? html`<p class="code">${this.code}</p>` : null}
          ${this.title ? html`<h1 class="title" id="ok-err-title">${this.title}</h1>` : null}
          ${this.message ? html`<p class="msg">${this.message}</p>` : null}

          <div class="search"><slot name="search"></slot></div>

          ${this.renderRetry()}
          ${this.renderChecks()}

          ${this.trace
            ? html`
                <details class="details">
                  <summary>${this.detailsLabel}</summary>
                  <pre class="trace">${this.trace}</pre>
                </details>
              `
            : null}

          ${this.renderShortcuts()}

          <div class="actions"><slot name="actions"></slot></div>

          ${this.meta ? html`<p class="meta">${this.meta}</p>` : null}
        </div>
      </main>
    `;
  }
}

define('ok-error-page', OkErrorPage);

declare global {
  interface HTMLElementTagNameMap {
    'ok-error-page': OkErrorPage;
  }
}
