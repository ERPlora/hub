import { LitElement, html, css } from 'lit';
import { property, state } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// ok-language-select — selector de idioma para la web pública (el hueco que Ionic no cubre:
// un dropdown de idiomas con globo, pensado para escalar a MUCHOS idiomas). Los idiomas se
// pasan como ENLACES en light DOM (SEO-crawlable + funciona sin JS + CSP-safe: la navegación
// es un href normal). El componente muestra un trigger (globo + idioma actual + chevron) y
// despliega la lista.
//
//   <ok-language-select value="es">
//     <a data-lang="en" href="/i18n/setlang/?language=en&next=/">English</a>
//     <a data-lang="es" href="/i18n/setlang/?language=es&next=/">Español</a>
//   </ok-language-select>
//
// `value` = código del idioma activo. Si no se pasa, se autoselecciona el idioma del
// NAVEGADOR (navigator.language) cuando coincide con uno de los enlaces; si no, el primero.

// Textos i18n (default inglés). Pásalos desde fuera con `.labels`.
export interface OkLanguageSelectLabels {
  /** aria-label del trigger que abre el desplegable de idiomas. */
  language: string;
}

const DEFAULT_LABELS: OkLanguageSelectLabels = {
  language: 'Language',
};

export class OkLanguageSelect extends LitElement {
  static styles = css`
    :host {
      display: inline-block;
      position: relative;
      --color: var(--ok-text, var(--ion-text-color, #18181b));
      --muted: var(--ok-muted, rgba(var(--ion-text-color-rgb, 24, 24, 27), 0.6));
      --surface: var(--ok-surface, var(--ion-card-background, var(--ion-background-color, #fff)));
      --border: var(--ok-border, rgba(var(--ion-text-color-rgb, 24, 24, 27), 0.14));
      --primary: var(--ok-primary, var(--ion-color-primary, #1496d6));
      --radius: var(--ok-radius, 12px);
      font-family: var(--ok-font, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif);
    }
    .trigger {
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      padding: 0.4rem 0.6rem;
      border: 1px solid var(--border);
      border-radius: 999px;
      background: transparent;
      color: var(--color);
      font: inherit;
      font-size: 0.85rem;
      cursor: pointer;
      transition: background-color var(--ok-transition, 150ms ease), border-color var(--ok-transition, 150ms ease);
    }
    @media (hover: hover) {
      .trigger:hover { border-color: color-mix(in oklab, var(--primary) 45%, var(--border)); }
    }
    .globe, .chev { width: 1rem; height: 1rem; flex: none; }
    .cur { font-weight: 600; }
    .chev { transition: transform var(--ok-transition, 180ms ease); color: var(--muted); }
    :host([open]) .chev { transform: rotate(180deg); }

    .panel {
      position: absolute;
      top: calc(100% + 0.4rem);
      right: 0;
      min-width: 11rem;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      box-shadow: 0 18px 44px -18px rgba(0, 0, 0, 0.28);
      padding: 0.35rem;
      z-index: 60;
      opacity: 0;
      transform: translateY(-6px);
      pointer-events: none;
      transition: opacity var(--ok-transition, 160ms ease), transform var(--ok-transition, 160ms ease);
    }
    :host([open]) .panel { opacity: 1; transform: none; pointer-events: auto; }
    @media (prefers-reduced-motion: reduce) {
      .panel, .chev { transition: none; }
    }

    /* Los <a> de idioma (light DOM) se estilan como ítems de menú. */
    ::slotted(a) {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      padding: 0.55rem 0.7rem;
      border-radius: 8px;
      color: var(--color);
      text-decoration: none;
      font-size: 0.9rem;
      transition: background-color var(--ok-transition, 120ms ease);
    }
    @media (hover: hover) {
      ::slotted(a:hover) { background: color-mix(in oklab, var(--primary) 12%, transparent); }
    }
    ::slotted(a.ok-lang-current) {
      color: var(--primary);
      font-weight: 600;
      background: color-mix(in oklab, var(--primary) 10%, transparent);
    }
  `;

  /** Código del idioma activo (p.ej. "es"). Si vacío, se usa el del navegador. */
  @property() value = '';
  /** Estado del desplegable (reflejado para :host([open])). */
  @property({ type: Boolean, reflect: true }) open = false;
  /** Textos i18n (parcial; se mezclan sobre los defaults en inglés). */
  @property({ attribute: false }) labels: Partial<OkLanguageSelectLabels> = {};

  private get t(): OkLanguageSelectLabels {
    return { ...DEFAULT_LABELS, ...this.labels };
  }

  @state() private currentLabel = '';

  connectedCallback(): void {
    super.connectedCallback();
    document.addEventListener('click', this.onDocClick);
    document.addEventListener('keydown', this.onKeydown);
  }
  disconnectedCallback(): void {
    super.disconnectedCallback();
    document.removeEventListener('click', this.onDocClick);
    document.removeEventListener('keydown', this.onKeydown);
  }

  firstUpdated(): void {
    this.resolveCurrent();
  }

  /** Decide el idioma activo: value → navegador → primero; marca el <a> y guarda su etiqueta. */
  private resolveCurrent(): void {
    const anchors = [...this.querySelectorAll<HTMLAnchorElement>('a[data-lang]')];
    if (!anchors.length) return;
    let code = this.value;
    if (!code) {
      const nav = (navigator.language || '').slice(0, 2).toLowerCase();
      if (anchors.some((a) => a.dataset.lang === nav)) code = nav;
    }
    if (!code) code = anchors[0].dataset.lang ?? '';
    for (const a of anchors) {
      const isCur = a.dataset.lang === code;
      a.classList.toggle('ok-lang-current', isCur);
      if (isCur) this.currentLabel = (a.textContent || code).trim();
    }
    if (!this.currentLabel) this.currentLabel = code.toUpperCase();
  }

  private toggle = (e: Event): void => {
    e.stopPropagation();
    this.open = !this.open;
  };
  private onDocClick = (e: MouseEvent): void => {
    if (this.open && !e.composedPath().includes(this)) this.open = false;
  };
  private onKeydown = (e: KeyboardEvent): void => {
    if (e.key === 'Escape' && this.open) this.open = false;
  };
  // Al pulsar un enlace, cierra (la navegación la hace el href nativo).
  private onPanelClick = (e: Event): void => {
    if ((e.target as Element)?.closest('a')) this.open = false;
  };

  render(): unknown {
    return html`
      <button
        class="trigger"
        type="button"
        aria-label=${this.t.language}
        aria-haspopup="listbox"
        aria-expanded=${this.open ? 'true' : 'false'}
        @click=${this.toggle}
      >
        <svg class="globe" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <circle cx="12" cy="12" r="10" /><path d="M2 12h20" />
          <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
        </svg>
        <span class="cur">${this.currentLabel || this.value.toUpperCase()}</span>
        <svg class="chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="m6 9 6 6 6-6" />
        </svg>
      </button>
      <div class="panel" role="listbox" @click=${this.onPanelClick}>
        <slot @slotchange=${() => this.resolveCurrent()}></slot>
      </div>
    `;
  }
}

define('ok-language-select', OkLanguageSelect);

declare global {
  interface HTMLElementTagNameMap {
    'ok-language-select': OkLanguageSelect;
  }
}
