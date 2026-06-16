import { LitElement, html, css } from 'lit';
import { property, state } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// ok-json-viewer — árbol JSON tipado y colapsable, autocontenido (CSS propio en el shadow).
// Renderiza recursivamente cualquier valor JSON (objeto/array/escalar) coloreando por tipo:
//   key=info · string=leaf · number=warn · bool=brand · null=ink itálico.
// Las filas con hijos (objetos/arrays) llevan un chevron que rota y, al colapsar, muestran un
// badge "N keys" / "N items". Guías de indentación con borde izquierdo. Monoespaciado tabular.
//   • prop `.data`           → objeto/array/valor, o un string JSON (se parsea)
//   • prop `size`            → compact | default | lg
//   • prop `expanded-depth`  → profundidad inicial expandida (default 1; -1 = todo)
// Evento (bubbles + composed):
//   • `ok-toggle`  detail { path, expanded }

/** Tamaño visual del visor. */
export type OkJsonViewerSize = 'compact' | 'default' | 'lg';

/** Valor JSON cualquiera (recursivo). */
export type OkJsonValue =
  | string
  | number
  | boolean
  | null
  | OkJsonValue[]
  | { [key: string]: OkJsonValue };

export class OkJsonViewer extends LitElement {
  static styles = css`
    :host {
      /* Tokens propios estilo Ionic (overridables): --ok-* → --ion-* → hex. */
      --bg: var(--ok-surface, var(--ion-background-color, #ffffff));
      --border: var(--ok-border, rgba(var(--ion-text-color-rgb, 28, 27, 23), 0.12));
      --guide: var(--ok-border-soft, rgba(var(--ion-text-color-rgb, 28, 27, 23), 0.1));
      --ink: var(--ok-text, var(--ion-text-color, #1c1b17));
      --ink-muted: var(--ok-text-muted, rgba(var(--ion-text-color-rgb, 28, 27, 23), 0.55));
      --ink-faint: var(--ok-text-faint, rgba(var(--ion-text-color-rgb, 28, 27, 23), 0.4));
      --hover-bg: var(--ok-hover, rgba(var(--ion-text-color-rgb, 28, 27, 23), 0.06));
      --radius: var(--ok-radius, 8px);
      /* Colores por tipo (cada uno con su cadena de fallback). */
      --key-color: var(--ok-json-key, var(--ion-color-primary, #3880ff));
      --string-color: var(--ok-json-string, var(--ion-color-success, #2dd36f));
      --number-color: var(--ok-json-number, var(--ion-color-warning, #ffc409));
      --bool-color: var(--ok-json-bool, var(--ion-color-secondary, #6030ff));
      --null-color: var(--ok-json-null, var(--ink-faint));
      --font-mono: var(--ok-font-mono, ui-monospace, 'SFMono-Regular', 'Menlo', 'Consolas', monospace);

      display: block;
      width: 100%;
    }

    .json {
      box-sizing: border-box;
      width: 100%;
      font-family: var(--font-mono);
      font-size: 0.8125rem;
      font-variant-numeric: tabular-nums;
      line-height: 1.55;
      color: var(--ink);
      background: var(--bg);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 0.625rem 0.875rem;
      overflow: auto;
    }
    /* Tamaños: ajustan fuente, padding e indentación. */
    .json.compact {
      font-size: 0.75rem;
      padding: 0.5rem 0.625rem;
      --indent: 14px;
    }
    .json.default {
      --indent: 18px;
    }
    .json.lg {
      font-size: 0.9375rem;
      padding: 0.875rem 1.125rem;
      --indent: 22px;
    }

    .group {
      margin: 0;
      padding: 0 0 0 var(--indent);
      list-style: none;
      /* Guía de indentación a la izquierda. */
      border-left: 1px solid var(--guide);
      margin-left: 6px;
    }

    .row {
      display: flex;
      align-items: flex-start;
      gap: 4px;
      white-space: pre;
      border-radius: 4px;
    }
    .row.has-children {
      cursor: pointer;
    }
    @media (hover: hover) {
      .row.has-children:hover {
        background: var(--hover-bg);
      }
    }

    /* Chevron: botón que rota 90deg al expandir. Reserva hueco en las hojas. */
    .caret {
      flex: 0 0 auto;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 14px;
      height: 1.55em;
      padding: 0;
      border: 0;
      background: none;
      color: var(--ink-muted);
      cursor: pointer;
      border-radius: 3px;
      transition: transform 0.18s ease, color 0.15s ease;
    }
    .caret.open {
      transform: rotate(90deg);
    }
    .caret.leaf {
      visibility: hidden;
      cursor: default;
    }
    .caret svg {
      width: 9px;
      height: 9px;
      display: block;
    }

    /* Colores por tipo. */
    .key {
      color: var(--key-color);
      font-weight: 500;
    }
    .key::after {
      content: ': ';
      color: var(--ink-faint);
    }
    .idx {
      color: var(--ink-faint);
    }
    .idx::after {
      content: ': ';
    }
    .string {
      color: var(--string-color);
      white-space: pre-wrap;
      word-break: break-word;
    }
    .string::before,
    .string::after {
      content: '"';
      opacity: 0.7;
    }
    .number {
      color: var(--number-color);
    }
    .bool {
      color: var(--bool-color);
      font-weight: 500;
    }
    .null {
      color: var(--null-color);
      font-style: italic;
    }
    .bracket,
    .comma {
      color: var(--ink-faint);
    }

    /* Badge de recuento al colapsar ("3 keys" / "5 items"). */
    .count {
      color: var(--ink-faint);
      font-style: italic;
      font-size: 0.875em;
      margin-left: 6px;
    }

    @media (prefers-reduced-motion: reduce) {
      .caret {
        transition: none;
      }
    }
  `;

  /** Datos a visualizar: valor JSON, o un string JSON que se parsea. */
  @property({ attribute: false }) data: OkJsonValue | string = null;
  /** Tamaño visual: compact | default | lg. */
  @property() size: OkJsonViewerSize = 'default';
  /** Profundidad inicial expandida (default 1; usa -1 para expandir todo). */
  @property({ type: Number, attribute: 'expanded-depth' }) expandedDepth = 1;

  // Estado interno: paths colapsados por el usuario (override sobre la profundidad inicial).
  @state() private collapsed = new Set<string>();

  // Parsea `data` si viene como string JSON; si falla, devuelve el string crudo.
  private get value(): OkJsonValue {
    const d = this.data;
    if (typeof d === 'string') {
      try {
        return JSON.parse(d) as OkJsonValue;
      } catch {
        return d;
      }
    }
    return d as OkJsonValue;
  }

  // ¿Es un contenedor (objeto/array no vacío) que se puede colapsar?
  private static hasChildren(v: OkJsonValue): boolean {
    if (Array.isArray(v)) return v.length > 0;
    return v !== null && typeof v === 'object' && Object.keys(v).length > 0;
  }

  // Decide si un path está expandido: el override del usuario manda; si no, la profundidad inicial.
  private isExpanded(path: string, depth: number): boolean {
    if (this.collapsed.has(path)) return false;
    if (this.expandedDepth < 0) return true;
    return depth < this.expandedDepth;
  }

  // Alterna expansión de un contenedor y emite `ok-toggle`.
  private toggle(path: string, depth: number): void {
    const next = new Set(this.collapsed);
    const wasExpanded = this.isExpanded(path, depth);
    if (wasExpanded) next.add(path);
    else next.delete(path);
    this.collapsed = next;
    this.dispatchEvent(
      new CustomEvent('ok-toggle', {
        detail: { path, expanded: !wasExpanded },
        bubbles: true,
        composed: true,
      }),
    );
  }

  // Chevron SVG inline (sin dependencias).
  private static caretSvg(): unknown {
    return html`<svg viewBox="0 0 10 10" aria-hidden="true">
      <path d="M3 1.5 L7 5 L3 8.5" fill="none" stroke="currentColor" stroke-width="1.6"
        stroke-linecap="round" stroke-linejoin="round"></path>
    </svg>`;
  }

  // Render del valor "hoja" (string/number/bool/null) con su clase de color.
  private static renderLeaf(v: OkJsonValue): unknown {
    if (v === null) return html`<span class="null">null</span>`;
    switch (typeof v) {
      case 'string':
        return html`<span class="string">${v}</span>`;
      case 'number':
        return html`<span class="number">${String(v)}</span>`;
      case 'boolean':
        return html`<span class="bool">${v ? 'true' : 'false'}</span>`;
      default:
        return html`<span class="string">${String(v)}</span>`;
    }
  }

  // Texto del badge de recuento de un contenedor colapsado.
  private static countLabel(v: OkJsonValue): string {
    if (Array.isArray(v)) {
      return `${v.length} ${v.length === 1 ? 'item' : 'items'}`;
    }
    const n = Object.keys(v as object).length;
    return `${n} ${n === 1 ? 'key' : 'keys'}`;
  }

  // Render recursivo de una fila. `keyLabel` es la clave de objeto o el índice de array (o null
  // para la raíz); `path` identifica la fila; `depth` controla la expansión inicial.
  private renderRow(
    keyLabel: { kind: 'key' | 'idx'; text: string } | null,
    v: OkJsonValue,
    path: string,
    depth: number,
    trailingComma: boolean,
  ): unknown {
    const children = OkJsonViewer.hasChildren(v);
    const isArr = Array.isArray(v);
    const open = children && this.isExpanded(path, depth);

    const label = keyLabel
      ? keyLabel.kind === 'key'
        ? html`<span class="key">${keyLabel.text}</span>`
        : html`<span class="idx">${keyLabel.text}</span>`
      : null;

    const comma = trailingComma ? html`<span class="comma">,</span>` : null;

    // Hoja: clave + valor + coma.
    if (!children) {
      // Contenedor vacío: se muestra como {} / [] (no colapsable).
      if (v !== null && typeof v === 'object') {
        return html`<div class="row">
          <span class="caret leaf">${OkJsonViewer.caretSvg()}</span>
          ${label}<span class="bracket">${isArr ? '[]' : '{}'}</span>${comma}
        </div>`;
      }
      return html`<div class="row">
        <span class="caret leaf">${OkJsonViewer.caretSvg()}</span>
        ${label}${OkJsonViewer.renderLeaf(v)}${comma}
      </div>`;
    }

    // Contenedor: cabecera con chevron + corchete de apertura (+ badge si está cerrado).
    const entries: Array<[{ kind: 'key' | 'idx'; text: string }, OkJsonValue]> = isArr
      ? (v as OkJsonValue[]).map((item, i) => [{ kind: 'idx' as const, text: String(i) }, item])
      : Object.entries(v as { [k: string]: OkJsonValue }).map(([k, item]) => [
          { kind: 'key' as const, text: k },
          item,
        ]);

    const openB = isArr ? '[' : '{';
    const closeB = isArr ? ']' : '}';

    return html`<div>
      <div
        class="row has-children"
        role="button"
        tabindex="0"
        aria-expanded=${String(open)}
        @click=${() => this.toggle(path, depth)}
        @keydown=${(e: KeyboardEvent) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            this.toggle(path, depth);
          }
        }}
      >
        <span class=${`caret ${open ? 'open' : ''}`}>${OkJsonViewer.caretSvg()}</span>
        ${label}<span class="bracket">${openB}</span>
        ${open ? null : html`<span class="count">${OkJsonViewer.countLabel(v)}</span>`}
        ${open ? null : html`<span class="bracket">${closeB}</span>`}${open ? null : comma}
      </div>
      ${open
        ? html`<div class="group" role="group">
              ${entries.map(([kl, item], i) =>
                this.renderRow(kl, item, `${path}/${kl.text}`, depth + 1, i < entries.length - 1),
              )}
            </div>
            <div class="row">
              <span class="caret leaf">${OkJsonViewer.caretSvg()}</span>
              <span class="bracket">${closeB}</span>${comma}
            </div>`
        : null}
    </div>`;
  }

  render(): unknown {
    const size = (['compact', 'default', 'lg'] as const).includes(this.size)
      ? this.size
      : 'default';
    return html`<div class=${`json ${size}`} role="tree">
      ${this.renderRow(null, this.value, '$', 0, false)}
    </div>`;
  }
}

define('ok-json-viewer', OkJsonViewer);

declare global {
  interface HTMLElementTagNameMap {
    'ok-json-viewer': OkJsonViewer;
  }
}
