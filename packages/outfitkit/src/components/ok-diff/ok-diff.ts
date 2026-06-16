import { LitElement, html, css } from 'lit';
import { property } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// ok-diff — visor de diff unificado línea a línea (estilo audit/version view).
// Construye lo que Ionic no trae: una rejilla monoespaciada con dos columnas de
// numeración (old/new) + contenido, líneas add tintadas en "leaf" y del en
// "danger" (color-mix 8%), glifos +/− vía ::before, y cabeceras de hunk en cursiva.
//   • prop `.lines` → OkDiffLine[] (datos declarativos; se asigna desde JS)
//   • prop `raw`    → string de diff unificado que se PARSEA a líneas
// Puramente presentacional: no emite eventos.

/** Tipo de línea de un diff unificado. */
export type OkDiffLineType = 'add' | 'del' | 'ctx' | 'hunk';

/** Una línea del visor de diff. */
export interface OkDiffLine {
  /** add = añadida, del = eliminada, ctx = contexto, hunk = cabecera @@…@@. */
  type: OkDiffLineType;
  /** Texto de la línea (sin el glifo +/−; el glifo lo pinta el componente). */
  content: string;
  /** Número de línea en el fichero original (old). */
  oldNo?: number;
  /** Número de línea en el fichero nuevo (new). */
  newNo?: number;
}

export class OkDiff extends LitElement {
  static styles = css`
    :host {
      display: block;
      width: 100%;
      /* Tokens propios estilo Ionic (overridables): cadena --ok-* → --ion-* → hex. */
      --bg: var(--ok-surface, var(--ion-background-color, #ffffff));
      --bg-hunk: var(--ok-surface-2, var(--ion-color-step-100, #f3f4f6));
      --border: var(--ok-border-color, var(--ion-border-color, #e2e4e8));
      --text: var(--ok-text-color, var(--ion-text-color, #1f2933));
      --text-muted: var(--ok-color-medium, var(--ion-color-medium, #92949c));
      --num: var(--ok-color-medium, var(--ion-color-medium, #92949c));
      /* "leaf" = verde de adición; "danger" = rojo de eliminación. */
      --add: var(--ok-success, var(--ion-color-success, #2dd36f));
      --del: var(--ok-danger, var(--ion-color-danger, #eb445a));
      --radius: var(--ok-radius-md, 8px);
      --mono: var(
        --ok-font-mono,
        ui-monospace,
        SFMono-Regular,
        'SF Mono',
        Menlo,
        Consolas,
        monospace
      );
    }

    .diff {
      font-family: var(--mono);
      font-size: 12.5px;
      line-height: 1.6;
      background: var(--bg);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      overflow: hidden;
      box-sizing: border-box;
      color: var(--text);
    }

    .line {
      display: grid;
      grid-template-columns: 44px 44px 1fr;
      padding: 0 12px 0 0;
    }

    .num {
      text-align: right;
      padding: 0 8px;
      color: var(--num);
      user-select: none;
      font-size: 11px;
      white-space: nowrap;
    }

    .content {
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      color: inherit;
    }

    /* Línea añadida: tinte leaf 8% + numeración verdosa + glifo "+". */
    .line--add {
      background: color-mix(in srgb, var(--add) 8%, transparent);
    }
    .line--add .num {
      color: color-mix(in srgb, var(--add) 70%, var(--num));
    }
    .line--add .content::before {
      content: '+ ';
      color: var(--add);
    }

    /* Línea eliminada: tinte danger 8% + numeración rojiza + glifo "−". */
    .line--del {
      background: color-mix(in srgb, var(--del) 8%, transparent);
    }
    .line--del .num {
      color: color-mix(in srgb, var(--del) 70%, var(--num));
    }
    .line--del .content::before {
      content: '− ';
      color: var(--del);
    }

    /* Cabecera de hunk (@@ … @@): fondo elevado, cursiva, ocupa todo el ancho. */
    .line--hunk {
      grid-template-columns: 1fr;
      background: var(--bg-hunk);
      color: var(--text-muted);
      font-style: italic;
    }
    .line--hunk .content {
      padding-left: 12px;
    }
    .line--hunk .content::before {
      content: '';
    }
  `;

  /** Series de líneas declarativas (tiene prioridad sobre `raw`). */
  @property({ attribute: false }) lines: OkDiffLine[] = [];

  /** Diff unificado en crudo; se parsea a líneas si no se aportó `.lines`. */
  @property() raw = '';

  /** Devuelve las líneas a renderizar: `.lines` si existe, si no parsea `raw`. */
  private resolveLines(): OkDiffLine[] {
    if (this.lines && this.lines.length) return this.lines;
    if (this.raw) return OkDiff.parseUnified(this.raw);
    return [];
  }

  /**
   * Parsea un diff unificado (texto) a OkDiffLine[]. CSP-safe (sin eval):
   * solo recorre líneas y lleva la cuenta de oldNo/newNo según las cabeceras
   * de hunk `@@ -a,b +c,d @@`. Ignora cabeceras de fichero (---, +++).
   */
  static parseUnified(raw: string): OkDiffLine[] {
    const out: OkDiffLine[] = [];
    let oldNo = 0;
    let newNo = 0;
    const hunkRe = /^@@\s+-(\d+)(?:,\d+)?\s+\+(\d+)(?:,\d+)?\s+@@/;

    for (const line of raw.replace(/\r\n?/g, '\n').split('\n')) {
      // Saltar cabeceras de fichero (no aportan al cuerpo del diff).
      if (line.startsWith('+++') || line.startsWith('---') || line.startsWith('diff ')) {
        continue;
      }
      const hunk = hunkRe.exec(line);
      if (hunk) {
        oldNo = Number(hunk[1]);
        newNo = Number(hunk[2]);
        out.push({ type: 'hunk', content: line });
        continue;
      }
      const head = line.charAt(0);
      if (head === '+') {
        out.push({ type: 'add', content: line.slice(1), newNo });
        newNo += 1;
      } else if (head === '-') {
        out.push({ type: 'del', content: line.slice(1), oldNo });
        oldNo += 1;
      } else {
        // Línea de contexto (empieza por espacio o vacía).
        const content = head === ' ' ? line.slice(1) : line;
        out.push({ type: 'ctx', content, oldNo, newNo });
        oldNo += 1;
        newNo += 1;
      }
    }
    return out;
  }

  /** Texto de la columna numérica (vacío si no hay número). */
  private static numText(n?: number): string {
    return n === undefined || n === null ? '' : String(n);
  }

  private renderLine(line: OkDiffLine): unknown {
    if (line.type === 'hunk') {
      return html`
        <div class="line line--hunk" role="row">
          <div class="content" role="cell">${line.content}</div>
        </div>
      `;
    }
    return html`
      <div class="line line--${line.type}" role="row">
        <span class="num" role="cell" aria-hidden="true">${OkDiff.numText(line.oldNo)}</span>
        <span class="num" role="cell" aria-hidden="true">${OkDiff.numText(line.newNo)}</span>
        <span class="content" role="cell">${line.content}</span>
      </div>
    `;
  }

  render(): unknown {
    const lines = this.resolveLines();
    return html`
      <div class="diff" role="table" aria-label="Diff de líneas">
        ${lines.map((l) => this.renderLine(l))}
      </div>
    `;
  }
}

define('ok-diff', OkDiff);

declare global {
  interface HTMLElementTagNameMap {
    'ok-diff': OkDiff;
  }
}
