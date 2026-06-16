import { LitElement, html, css } from 'lit';
import { property, state, query } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// ok-rich-text — editor WYSIWYG (rich text) que Ionic no trae.
// Área contenteditable con prosa completa (h1-h4, p, listas, links, code,
// pre, blockquote con borde de marca, hr, strong/em/mark), toolbar que
// envuelve, y footer con contador de palabras + formatos activos.
// Variante "minimal": sin toolbar/footer, edición inline.
// Eventos: ok-input { html } en cada cambio.

/** Tamaño del editor. `minimal` = sin toolbar/footer, edición inline. */
export type OkRichTextSize = 'sm' | 'md' | 'lg' | 'minimal';

// Definición declarativa de un botón de formato de la toolbar.
interface ToolButton {
  /** Comando de document.execCommand. */
  cmd: string;
  /** Argumento opcional del comando (p.ej. tag para formatBlock). */
  arg?: string;
  /** Clave de estado activo (queryCommandState / formatBlock). */
  active: string;
  /** Etiqueta accesible. */
  label: string;
  /** SVG inline (paths) del icono. */
  icon: unknown;
}

export class OkRichText extends LitElement {
  static styles = css`
    :host {
      display: block;
      width: 100%;
      /* Tokens propios estilo Ionic: --ok-* → --ion-* → hex. */
      --bg: var(--ok-surface, var(--ion-background-color, #fff));
      --toolbar-bg: var(--ok-toolbar-bg, var(--ion-color-light, #f4f5f8));
      --footer-bg: var(--ok-toolbar-bg, var(--ion-color-light, #f4f5f8));
      --line: var(--ok-border-color, var(--ion-border-color, #dfe1e6));
      --ink: var(--ok-text-color, var(--ion-text-color, #1f2933));
      --ink-2: var(--ok-color-medium-shade, var(--ion-color-medium-shade, #5c6470));
      --ink-muted: var(--ok-color-medium, var(--ion-color-medium, #92949c));
      --brand: var(--ok-color-primary, var(--ion-color-primary, #0091ce));
      --brand-contrast: var(--ok-color-primary-contrast, var(--ion-color-primary-contrast, #fff));
      --brand-soft: color-mix(in srgb, var(--brand) 14%, transparent);
      --warn: var(--ok-color-warning, var(--ion-color-warning, #ffc409));
      --radius: var(--ok-radius-lg, 12px);
      --radius-sm: var(--ok-radius-sm, 6px);
      --font-display: var(--ok-font-display, var(--ion-font-family, inherit));
      --font-mono: var(--ok-font-mono, ui-monospace, 'SFMono-Regular', Menlo, monospace);
      --pad: 0.75rem;
      --min-h: 200px;
    }

    .rt {
      display: flex;
      flex-direction: column;
      box-sizing: border-box;
      width: 100%;
      background: var(--bg);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      overflow: hidden;
      color: var(--ink);
      transition: border-color 0.15s ease, box-shadow 0.15s ease;
    }
    .rt.is-focus {
      border-color: var(--brand);
      box-shadow: 0 0 0 3px var(--brand-soft);
    }

    /* ── Toolbar ───────────────────────────────────────────── */
    .toolbar {
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: 0.25rem;
      padding: 0.25rem 0.5rem;
      background: var(--toolbar-bg);
      border-bottom: 1px solid var(--line);
      min-height: 38px;
    }
    .select {
      height: 26px;
      padding: 0 0.5rem;
      background: var(--bg);
      border: 1px solid var(--line);
      border-radius: var(--radius-sm);
      color: var(--ink);
      font: inherit;
      font-size: 0.75rem;
      cursor: pointer;
    }
    .select:focus-visible {
      outline: 2px solid var(--brand);
      outline-offset: 1px;
    }
    .btn {
      width: 28px;
      height: 28px;
      display: inline-grid;
      place-items: center;
      border: 0;
      background: transparent;
      border-radius: var(--radius-sm);
      color: var(--ink-2);
      cursor: pointer;
      font-family: inherit;
      transition: background 0.12s ease, color 0.12s ease, transform 0.12s ease;
    }
    .btn:hover {
      background: color-mix(in srgb, var(--ink) 8%, transparent);
      color: var(--ink);
    }
    .btn:active { transform: scale(0.96); }
    .btn:focus-visible {
      outline: 2px solid var(--brand);
      outline-offset: 1px;
    }
    .btn[aria-pressed='true'] {
      background: var(--brand-soft);
      color: var(--ink);
      box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--brand) 30%, transparent);
    }
    .btn svg {
      width: 14px;
      height: 14px;
      stroke-width: 2;
    }
    .divider {
      width: 1px;
      height: 18px;
      background: var(--line);
      margin: 0 0.25rem;
    }
    .spacer { flex: 1; }

    /* ── Área de contenido ─────────────────────────────────── */
    .content {
      min-height: var(--min-h);
      padding: var(--pad);
      outline: 0;
      font-size: 0.9375rem;
      line-height: 1.6;
      color: var(--ink);
      overflow-y: auto;
      box-sizing: border-box;
    }
    .content:empty::before {
      content: attr(data-placeholder);
      color: var(--ink-muted);
      pointer-events: none;
    }
    .content > *:first-child { margin-top: 0; }
    .content > *:last-child { margin-bottom: 0; }

    .content p { margin: 0 0 0.75rem; }
    .content h1,
    .content h2,
    .content h3,
    .content h4 {
      font-family: var(--font-display);
      letter-spacing: -0.01em;
      color: var(--ink);
      margin: 1rem 0 0.5rem;
      line-height: 1.2;
      font-weight: 600;
    }
    .content h1 { font-size: 1.625rem; }
    .content h2 { font-size: 1.375rem; }
    .content h3 { font-size: 1.15rem; }
    .content h4 { font-size: 1rem; }

    .content ul,
    .content ol {
      margin: 0 0 0.75rem;
      padding-left: 1.5rem;
    }
    .content li { margin-bottom: 0.25rem; }

    .content a {
      color: var(--brand);
      text-decoration: underline;
      text-underline-offset: 2px;
      text-decoration-color: color-mix(in srgb, var(--brand) 50%, transparent);
    }
    .content a:hover { text-decoration-color: var(--brand); }

    .content code {
      font-family: var(--font-mono);
      font-size: 0.9em;
      background: color-mix(in srgb, var(--ink) 6%, transparent);
      border: 1px solid var(--line);
      border-radius: 4px;
      padding: 1px 6px;
      color: var(--ink);
    }
    .content pre {
      font-family: var(--font-mono);
      font-size: 0.85rem;
      background: color-mix(in srgb, var(--ink) 4%, transparent);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 0.75rem 1rem;
      overflow-x: auto;
      margin: 0 0 0.75rem;
      line-height: 1.55;
    }
    .content pre code {
      background: transparent;
      border: 0;
      padding: 0;
    }
    .content blockquote {
      margin: 0 0 0.75rem;
      padding: 0.25rem 0.75rem;
      border-left: 3px solid var(--brand);
      color: var(--ink-2);
      background: color-mix(in srgb, var(--brand) 6%, transparent);
      border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
      font-style: italic;
    }
    .content hr {
      border: 0;
      border-top: 1px solid var(--line);
      margin: 1rem 0;
    }
    .content strong { font-weight: 600; color: var(--ink); }
    .content em { font-style: italic; }
    .content u { text-decoration: underline; text-underline-offset: 2px; }
    .content mark {
      background: color-mix(in srgb, var(--warn) 28%, transparent);
      color: var(--ink);
      padding: 0 2px;
      border-radius: 2px;
    }

    /* ── Footer ────────────────────────────────────────────── */
    .footer {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 0.75rem;
      padding: 0.25rem 0.75rem;
      border-top: 1px solid var(--line);
      background: var(--footer-bg);
      font-size: 0.6875rem;
      color: var(--ink-muted);
      font-family: var(--font-mono);
      font-variant-numeric: tabular-nums;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      min-height: 26px;
    }

    /* ── Tamaños ───────────────────────────────────────────── */
    :host([size='sm']) { --min-h: 120px; --pad: 0.5rem; }
    :host([size='sm']) .content { font-size: 0.875rem; }
    :host([size='lg']) { --min-h: 320px; --pad: 1.25rem; }
    :host([size='lg']) .content { font-size: 1rem; }
    :host([size='lg']) .btn { width: 32px; height: 32px; }
    :host([size='lg']) .btn svg { width: 16px; height: 16px; }

    /* ── Minimal — sin toolbar/footer, edición inline ─────── */
    :host([size='minimal']) .rt {
      background: transparent;
      border-radius: var(--radius-sm);
    }
    :host([size='minimal']) .content { min-height: auto; }
  `;

  /** Contenido HTML del editor. */
  @property() value = '';

  /** Placeholder cuando el área está vacía. */
  @property() placeholder = 'Escribe aquí…';

  /** Tamaño / modo. `minimal` oculta toolbar y footer. */
  @property({ reflect: true }) size: OkRichTextSize = 'md';

  /** Muestra la toolbar de formato (ignorado en minimal). */
  @property({ type: Boolean }) toolbar = true;

  /** Muestra el footer con contador de palabras (ignorado en minimal). */
  @property({ type: Boolean }) footer = true;

  // Estado interno de foco para el glow.
  @state() private focused = false;

  // Formatos activos según la selección actual (para aria-pressed + footer).
  @state() private activeFmts: Set<string> = new Set();

  // Bloque de cabecera activo (p, h1…h4, blockquote, pre).
  @state() private activeBlock = 'p';

  // Nº de palabras vivo.
  @state() private words = 0;

  @query('.content') private contentEl?: HTMLElement;

  // Evita sobreescribir el DOM editable mientras el usuario teclea.
  private syncingFromInput = false;

  // Iconos SVG inline (paths a mano, sin dependencias).
  private static readonly icons = {
    bold: html`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M6 4h8a4 4 0 0 1 0 8H6z"/><path d="M6 12h9a4 4 0 0 1 0 8H6z"/></svg>`,
    italic: html`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><line x1="19" y1="4" x2="10" y2="4"/><line x1="14" y1="20" x2="5" y2="20"/><line x1="15" y1="4" x2="9" y2="20"/></svg>`,
    underline: html`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M6 3v7a6 6 0 0 0 12 0V3"/><line x1="4" y1="21" x2="20" y2="21"/></svg>`,
    ul: html`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><line x1="9" y1="6" x2="20" y2="6"/><line x1="9" y1="12" x2="20" y2="12"/><line x1="9" y1="18" x2="20" y2="18"/><circle cx="4" cy="6" r="1"/><circle cx="4" cy="12" r="1"/><circle cx="4" cy="18" r="1"/></svg>`,
    ol: html`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><line x1="10" y1="6" x2="21" y2="6"/><line x1="10" y1="12" x2="21" y2="12"/><line x1="10" y1="18" x2="21" y2="18"/><path d="M4 6h1v4"/><path d="M4 10h2"/><path d="M6 16a1.5 1.5 0 1 0-2 1.5L6 19H4"/></svg>`,
    code: html`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>`,
    quote: html`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M3 11h5V6H4a1 1 0 0 0-1 1z"/><path d="M3 11v3a4 4 0 0 0 4 4"/><path d="M14 11h5V6h-4a1 1 0 0 0-1 1z"/><path d="M14 11v3a4 4 0 0 0 4 4"/></svg>`,
    link: html`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1.5 1.5"/><path d="M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1.5-1.5"/></svg>`,
    undo: html`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><polyline points="3 7 3 13 9 13"/><path d="M3 13a9 9 0 1 0 3-7"/></svg>`,
  };

  // Botones inline (no bloque) de la toolbar.
  private get inlineButtons(): ToolButton[] {
    return [
      { cmd: 'bold', active: 'bold', label: 'Negrita', icon: OkRichText.icons.bold },
      { cmd: 'italic', active: 'italic', label: 'Cursiva', icon: OkRichText.icons.italic },
      { cmd: 'underline', active: 'underline', label: 'Subrayado', icon: OkRichText.icons.underline },
    ];
  }

  private get listButtons(): ToolButton[] {
    return [
      { cmd: 'insertUnorderedList', active: 'insertUnorderedList', label: 'Lista', icon: OkRichText.icons.ul },
      { cmd: 'insertOrderedList', active: 'insertOrderedList', label: 'Lista numerada', icon: OkRichText.icons.ol },
    ];
  }

  protected firstUpdated(): void {
    this.renderValueIntoDom();
    this.recountWords();
  }

  protected updated(changed: Map<string, unknown>): void {
    // Si cambia value por fuera (no por tecleo), refrescamos el DOM editable.
    if (changed.has('value') && !this.syncingFromInput) {
      this.renderValueIntoDom();
      this.recountWords();
    }
    this.syncingFromInput = false;
  }

  // Vuelca el HTML de `value` en el área editable solo si difiere (evita
  // perder el caret mientras se teclea).
  private renderValueIntoDom(): void {
    const el = this.contentEl;
    if (el && el.innerHTML !== this.value) el.innerHTML = this.value ?? '';
  }

  private recountWords(): void {
    const text = (this.contentEl?.innerText ?? '').trim();
    this.words = text ? text.split(/\s+/).filter(Boolean).length : 0;
  }

  // Lee el estado de formato/bloque de la selección actual.
  private refreshActiveState(): void {
    const next = new Set<string>();
    const cmds = ['bold', 'italic', 'underline', 'insertUnorderedList', 'insertOrderedList'];
    for (const c of cmds) {
      try {
        if (document.queryCommandState(c)) next.add(c);
      } catch {
        /* queryCommandState puede lanzar en algunos navegadores */
      }
    }
    this.activeFmts = next;
    let block = 'p';
    try {
      const v = document.queryCommandValue('formatBlock');
      if (typeof v === 'string' && v) block = v.toLowerCase();
    } catch {
      /* noop */
    }
    this.activeBlock = block;
  }

  // Mantiene el foco/selección en el área antes de ejecutar un comando.
  private exec(cmd: string, arg?: string): void {
    this.contentEl?.focus();
    try {
      document.execCommand(cmd, false, arg);
    } catch {
      /* execCommand obsoleto pero ampliamente soportado; ignoramos fallos */
    }
    this.onInput();
    this.refreshActiveState();
  }

  private onHeadingChange(e: Event): void {
    const tag = (e.target as HTMLSelectElement).value;
    // <p> y <blockquote>/<pre> via formatBlock; el navegador envuelve el bloque.
    this.exec('formatBlock', tag === 'p' ? 'p' : tag);
  }

  private onLink(): void {
    const url = window.prompt('URL del enlace:', 'https://');
    if (url) this.exec('createLink', url);
  }

  // Cada cambio en el área editable: sincroniza value + emite ok-input.
  private onInput(): void {
    const el = this.contentEl;
    if (!el) return;
    const htmlOut = el.innerHTML;
    this.syncingFromInput = true;
    this.value = htmlOut;
    this.recountWords();
    this.dispatchEvent(
      new CustomEvent('ok-input', {
        detail: { html: htmlOut },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private onFocus(): void {
    this.focused = true;
    this.refreshActiveState();
  }

  private onBlur(): void {
    this.focused = false;
  }

  // Refresca el estado activo al mover el caret / seleccionar.
  private onSelect(): void {
    if (this.focused) this.refreshActiveState();
  }

  private toolBtn(b: ToolButton): unknown {
    const pressed = this.activeFmts.has(b.active);
    return html`
      <button
        type="button"
        class="btn"
        aria-label=${b.label}
        title=${b.label}
        aria-pressed=${pressed ? 'true' : 'false'}
        @mousedown=${(e: Event) => e.preventDefault()}
        @click=${() => this.exec(b.cmd, b.arg)}
      >
        ${b.icon}
      </button>
    `;
  }

  private renderToolbar(): unknown {
    return html`
      <div class="toolbar" role="toolbar" aria-label="Formato">
        <select
          class="select"
          aria-label="Estilo de párrafo"
          .value=${this.activeBlock === 'div' ? 'p' : this.activeBlock}
          @mousedown=${(e: Event) => e.stopPropagation()}
          @change=${this.onHeadingChange}
        >
          <option value="p">Párrafo</option>
          <option value="h1">Título 1</option>
          <option value="h2">Título 2</option>
          <option value="h3">Título 3</option>
          <option value="h4">Título 4</option>
        </select>
        <span class="divider"></span>
        ${this.inlineButtons.map((b) => this.toolBtn(b))}
        <span class="divider"></span>
        ${this.listButtons.map((b) => this.toolBtn(b))}
        <span class="divider"></span>
        <button
          type="button"
          class="btn"
          aria-label="Código"
          title="Código"
          @mousedown=${(e: Event) => e.preventDefault()}
          @click=${() => this.exec('formatBlock', 'pre')}
        >
          ${OkRichText.icons.code}
        </button>
        <button
          type="button"
          class="btn"
          aria-label="Cita"
          title="Cita"
          @mousedown=${(e: Event) => e.preventDefault()}
          @click=${() => this.exec('formatBlock', 'blockquote')}
        >
          ${OkRichText.icons.quote}
        </button>
        <button
          type="button"
          class="btn"
          aria-label="Enlace"
          title="Enlace"
          @mousedown=${(e: Event) => e.preventDefault()}
          @click=${() => this.onLink()}
        >
          ${OkRichText.icons.link}
        </button>
        <span class="spacer"></span>
        <button
          type="button"
          class="btn"
          aria-label="Deshacer"
          title="Deshacer"
          @mousedown=${(e: Event) => e.preventDefault()}
          @click=${() => this.exec('undo')}
        >
          ${OkRichText.icons.undo}
        </button>
      </div>
    `;
  }

  private renderFooter(): unknown {
    const fmts: string[] = [];
    if (this.activeBlock && this.activeBlock !== 'p' && this.activeBlock !== 'div')
      fmts.push(this.activeBlock);
    if (this.activeFmts.has('bold')) fmts.push('negrita');
    if (this.activeFmts.has('italic')) fmts.push('cursiva');
    if (this.activeFmts.has('underline')) fmts.push('subrayado');
    if (this.activeFmts.has('insertUnorderedList')) fmts.push('lista');
    if (this.activeFmts.has('insertOrderedList')) fmts.push('lista num.');
    const wordLabel = `${this.words} ${this.words === 1 ? 'palabra' : 'palabras'}`;
    return html`
      <div class="footer">
        <span>${wordLabel}</span>
        <span>${fmts.length ? `formato: ${fmts.join(', ')}` : 'sin formato'}</span>
      </div>
    `;
  }

  render(): unknown {
    const isMinimal = this.size === 'minimal';
    const showToolbar = !isMinimal && this.toolbar;
    const showFooter = !isMinimal && this.footer;
    return html`
      <div class="rt ${this.focused ? 'is-focus' : ''}">
        ${showToolbar ? this.renderToolbar() : null}
        <div
          class="content"
          contenteditable="true"
          role="textbox"
          aria-multiline="true"
          aria-label=${this.placeholder}
          data-placeholder=${this.placeholder}
          @input=${this.onInput}
          @focus=${this.onFocus}
          @blur=${this.onBlur}
          @keyup=${this.onSelect}
          @mouseup=${this.onSelect}
        ></div>
        ${showFooter ? this.renderFooter() : null}
      </div>
    `;
  }
}

define('ok-rich-text', OkRichText);

declare global {
  interface HTMLElementTagNameMap {
    'ok-rich-text': OkRichText;
  }
}
