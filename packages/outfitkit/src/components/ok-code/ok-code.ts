import { LitElement, html, css } from 'lit';
import { property, state } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// ok-code — visor de código sin resaltado de sintaxis.
// Bloque: superficie monospace bordeada, scroll horizontal, whitespace preservado,
// etiqueta de lenguaje opcional y botón de copiar (navigator.clipboard).
// Variante inline: pill sobre bg-3 (para `code` dentro de texto).
// Porta el diseño .ux-code / .ux-code--inline de la librería CSS antigua.
export class OkCode extends LitElement {
  static styles = css`
    :host {
      display: block;
      width: 100%;
      /* Tokens propios estilo Ionic (overridables): --ok-* → --ion-* → hex. */
      --bg: var(--ok-surface, var(--ion-background-color, #f5f6f8));
      --inline-bg: var(--ok-surface-3, var(--ion-color-light, #e6e8ec));
      --border-color: var(--ok-border-color, var(--ion-border-color, #d7dbe0));
      --color: var(--ok-text-color, var(--ion-text-color, #1f2933));
      --label-color: var(--ok-color-medium, var(--ion-color-medium, #92949c));
      --radius: 8px;
      --inline-radius: 4px;
      --mono: var(
        --ok-font-mono,
        ui-monospace,
        'SF Mono',
        'SFMono-Regular',
        'Menlo',
        'Consolas',
        monospace
      );
    }

    /* La variante inline no debe ocupar todo el ancho. */
    :host([inline]) {
      display: inline;
      width: auto;
    }

    .wrap {
      position: relative;
      width: 100%;
      box-sizing: border-box;
    }

    /* Bloque de código: superficie bordeada con scroll horizontal. */
    .block {
      display: block;
      margin: 0;
      background: var(--bg);
      border: 1px solid var(--border-color);
      border-radius: var(--radius);
      padding: 14px 16px;
      font-family: var(--mono);
      font-size: 12.5px;
      line-height: 1.6;
      color: var(--color);
      overflow-x: auto;
      white-space: pre;
      tab-size: 2;
    }

    /* Hueco a la derecha cuando hay botón de copiar, para no solapar. */
    .block.has-copy {
      padding-right: 44px;
    }

    /* Cabecera opcional con la etiqueta de lenguaje. */
    .head {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      padding: 0 0 6px;
    }

    .lang {
      font-family: var(--mono);
      font-size: 11px;
      font-weight: 600;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      color: var(--label-color);
    }

    /* Botón de copiar flotante (esquina superior derecha del bloque). */
    .copy {
      position: absolute;
      top: 6px;
      right: 6px;
      --padding-start: 6px;
      --padding-end: 6px;
      --padding-top: 4px;
      --padding-bottom: 4px;
      margin: 0;
      height: 28px;
      font-size: 11px;
    }

    /* Variante inline: pill sobre bg-3, sin borde. */
    .inline {
      display: inline;
      padding: 1px 6px;
      font-family: var(--mono);
      font-size: 12px;
      line-height: inherit;
      color: var(--color);
      background: var(--inline-bg);
      border-radius: var(--inline-radius);
      white-space: pre-wrap;
      word-break: break-word;
    }
  `;

  /** Texto de código a mostrar. */
  @property() code = '';

  /** Variante inline (pill dentro de texto) en vez de bloque. */
  @property({ type: Boolean, reflect: true }) inline = false;

  /** Etiqueta del lenguaje (solo informativa, no hay resaltado). */
  @property() language = '';

  /** Muestra el botón de copiar (solo en variante bloque). */
  @property({ type: Boolean }) copy = false;

  /** Estado transitorio tras copiar (feedback visual). */
  @state() private copied = false;

  private async handleCopy(): Promise<void> {
    try {
      // Usa la Clipboard API nativa (sin dependencias).
      await navigator.clipboard.writeText(this.code);
      this.copied = true;
      window.setTimeout(() => {
        this.copied = false;
      }, 1600);
      this.dispatchEvent(
        new CustomEvent<OkCodeCopyDetail>('ok-copy', {
          detail: { code: this.code, ok: true },
          bubbles: true,
          composed: true,
        }),
      );
    } catch {
      // Falla silenciosa (p.ej. contexto no seguro): notificamos ok:false.
      this.dispatchEvent(
        new CustomEvent<OkCodeCopyDetail>('ok-copy', {
          detail: { code: this.code, ok: false },
          bubbles: true,
          composed: true,
        }),
      );
    }
  }

  render(): unknown {
    // Variante inline: simple pill, sin cabecera ni copiar.
    if (this.inline) {
      return html`<code class="inline">${this.code}</code>`;
    }

    const showCopy = this.copy;

    return html`
      <div class="wrap">
        ${this.language ? html`<div class="head"><span class="lang">${this.language}</span></div>` : null}
        <pre class="block ${showCopy ? 'has-copy' : ''}"><code>${this.code}</code></pre>
        ${showCopy
          ? html`<ion-button
              class="copy"
              size="small"
              fill="solid"
              color="medium"
              aria-label="Copiar código"
              @click=${this.handleCopy}
              >${this.copied ? 'Copiado' : 'Copiar'}</ion-button
            >`
          : null}
      </div>
    `;
  }
}

/** Detalle del evento `ok-copy`. */
export interface OkCodeCopyDetail {
  /** Código que se intentó copiar. */
  code: string;
  /** Si la copia al portapapeles tuvo éxito. */
  ok: boolean;
}

define('ok-code', OkCode);

declare global {
  interface HTMLElementTagNameMap {
    'ok-code': OkCode;
  }
}
