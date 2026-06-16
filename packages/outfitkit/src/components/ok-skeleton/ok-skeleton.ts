import { LitElement, html, css } from 'lit';
import { property } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// Variantes de forma del skeleton (un bloque "shimmer" con dimensiones predefinidas).
export type OkSkeletonVariant =
  | 'text'
  | 'title'
  | 'circle'
  | 'avatar'
  | 'button'
  | 'chip'
  | 'card'
  | 'row';

// Presets compuestos: scaffolds de placeholder para UIs comunes.
export type OkSkeletonPreset = 'none' | 'card' | 'table' | 'chart';

// ok-skeleton — placeholder de carga (shimmer) con variantes de forma, stack de
// líneas con anchos decrecientes (92/78/60%) y presets compuestos (card/table/chart).
// Respeta prefers-reduced-motion deshabilitando la animación.
// El preset "table" replica la rejilla de ok-data-table.
export class OkSkeleton extends LitElement {
  static styles = css`
    :host {
      display: block;
      width: 100%;
      /* Tokens propios estilo Ionic (overridables): --ok-* → --ion-* → hex. */
      --skel-from: var(--ok-skeleton-base, var(--ion-color-step-100, #e9edf2));
      --skel-to: var(--ok-skeleton-highlight, var(--ion-color-step-200, #d3dae2));
      --surface: var(--ok-surface, var(--ion-card-background, var(--ion-background-color, #fff)));
      --line: var(--ok-border-color, var(--ion-border-color, #e2e8f0));
      --radius-sm: var(--ok-radius-sm, 4px);
      --radius-md: var(--ok-radius-md, 8px);
      --radius-lg: var(--ok-radius-lg, 12px);
      --radius-xl: var(--ok-radius-xl, 16px);
      --radius-pill: var(--ok-radius-pill, 999px);
      --speed: var(--ok-skeleton-speed, 1.4s);
    }

    /* Bloque base con shimmer horizontal. */
    .skel {
      display: block;
      background: linear-gradient(
        90deg,
        var(--skel-from) 0%,
        var(--skel-to) 50%,
        var(--skel-from) 100%
      );
      background-size: 200% 100%;
      animation: skel-shimmer var(--speed) linear infinite;
      border-radius: var(--radius-sm);
    }

    @keyframes skel-shimmer {
      0% {
        background-position: 200% 0;
      }
      100% {
        background-position: -200% 0;
      }
    }

    /* Variantes de forma. */
    .v-text {
      height: 12px;
      width: 100%;
      border-radius: 4px;
    }
    .v-title {
      height: 18px;
      width: 60%;
      border-radius: 4px;
    }
    .v-circle {
      border-radius: 50%;
      aspect-ratio: 1;
    }
    .v-avatar {
      width: 36px;
      height: 36px;
      border-radius: 50%;
    }
    .v-button {
      height: 32px;
      width: 96px;
      border-radius: var(--radius-md);
    }
    .v-chip {
      height: 22px;
      width: 72px;
      border-radius: var(--radius-pill);
    }
    .v-card {
      height: 120px;
      border-radius: var(--radius-lg);
    }
    .v-row {
      height: 44px;
      border-radius: var(--radius-md);
    }

    /* Stack de líneas de texto con anchos decrecientes (92/78/60%). */
    .stack {
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .stack .line:nth-child(2) {
      width: 92%;
    }
    .stack .line:nth-child(3) {
      width: 78%;
    }
    .stack .line:nth-child(n + 4) {
      width: 60%;
    }

    /* Preset: card. */
    .preset-card {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: var(--radius-xl);
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 12px;
      box-sizing: border-box;
    }
    .preset-card .head {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .preset-card .head .meta {
      flex: 1;
      display: flex;
      flex-direction: column;
      gap: 6px;
    }

    /* Preset: table (replica la rejilla de ok-data-table). */
    .preset-table {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: var(--radius-xl);
      padding: 6px 14px;
      box-sizing: border-box;
    }
    .preset-table .trow {
      display: grid;
      gap: 16px;
      padding: 14px 0;
      border-bottom: 1px solid var(--line);
      align-items: center;
    }
    .preset-table .trow:last-child {
      border-bottom: none;
    }
    .preset-table .trow.head .skel {
      opacity: 0.55;
      height: 10px;
    }

    /* Preset: chart (barras con shimmer vertical). */
    .preset-chart {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: var(--radius-xl);
      padding: 16px;
      height: 180px;
      display: flex;
      align-items: flex-end;
      gap: 6px;
      box-sizing: border-box;
    }
    .preset-chart .bar {
      flex: 1;
      border-radius: var(--radius-sm);
      background: linear-gradient(
        180deg,
        var(--skel-from) 0%,
        var(--skel-to) 50%,
        var(--skel-from) 100%
      );
      background-size: 100% 200%;
      animation: skel-shimmer-v var(--speed) linear infinite;
    }

    @keyframes skel-shimmer-v {
      0% {
        background-position: 0 200%;
      }
      100% {
        background-position: 0 -200%;
      }
    }

    /* Accesibilidad: sin movimiento si el usuario lo pide. */
    @media (prefers-reduced-motion: reduce) {
      .skel,
      .preset-chart .bar {
        animation: none;
      }
    }
  `;

  /** Variante de forma del bloque individual. */
  @property() variant: OkSkeletonVariant = 'text';

  /** Nº de líneas apiladas (solo aplica a variant="text"/"title"; >1 activa el stack). */
  @property({ type: Number }) lines = 1;

  /** Ancho CSS explícito (override de la variante), p.ej. "120px" o "40%". */
  @property() width?: string;

  /** Alto CSS explícito (override de la variante). */
  @property() height?: string;

  /** Radio de borde CSS explícito (override de la variante). */
  @property() radius?: string;

  /** Preset compuesto: scaffold de placeholder. */
  @property() preset: OkSkeletonPreset = 'none';

  /** Nº de filas del preset table (incluye la cabecera). */
  @property({ type: Number }) rows = 5;

  /** Nº de columnas del preset table / nº de barras del preset chart. */
  @property({ type: Number }) cols = 4;

  /** Estilos inline (width/height/radius) aplicados al bloque. */
  private blockStyle(): string {
    const parts: string[] = [];
    if (this.width) parts.push(`width:${this.width}`);
    if (this.height) parts.push(`height:${this.height}`);
    if (this.radius) parts.push(`border-radius:${this.radius}`);
    return parts.join(';');
  }

  /** Bloque base con la clase de variante. */
  private renderBlock(variant: OkSkeletonVariant = this.variant): unknown {
    return html`
      <div
        class="skel v-${variant}"
        style=${this.blockStyle()}
        part="block"
      ></div>
    `;
  }

  /** Stack de líneas con anchos decrecientes (la 1ª al 100%). */
  private renderStack(): unknown {
    const n = Math.max(1, this.lines);
    const cls = this.variant === 'title' ? 'v-title' : 'v-text';
    return html`
      <div class="stack">
        ${Array.from(
          { length: n },
          () => html`<div class="skel line ${cls}" part="line"></div>`
        )}
      </div>
    `;
  }

  /** Preset card: avatar + dos líneas de meta + bloque de cuerpo + acciones. */
  private renderPresetCard(): unknown {
    return html`
      <div class="preset-card" part="card">
        <div class="head">
          <div class="skel v-avatar"></div>
          <div class="meta">
            <div class="skel v-title" style="width:50%"></div>
            <div class="skel v-text" style="width:80%"></div>
          </div>
        </div>
        <div class="skel v-card" style="height:80px"></div>
        <div class="head" style="justify-content:flex-end">
          <div class="skel v-button"></div>
          <div class="skel v-button" style="width:72px"></div>
        </div>
      </div>
    `;
  }

  /** Preset table: replica la rejilla de ok-data-table (cabecera + filas). */
  private renderPresetTable(): unknown {
    const cols = Math.max(1, this.cols);
    const rows = Math.max(1, this.rows);
    // Plantilla de columnas con anchos tipo data-table: 1ª más ancha, última estrecha.
    const template = Array.from({ length: cols }, (_, i) => {
      if (i === 0) return '1.6fr';
      if (i === cols - 1) return '0.6fr';
      return '1fr';
    }).join(' ');
    const rowStyle = `grid-template-columns:${template}`;
    const cell = () => html`<div class="skel v-text"></div>`;
    return html`
      <div class="preset-table" part="table">
        <div class="trow head" style=${rowStyle}>
          ${Array.from({ length: cols }, cell)}
        </div>
        ${Array.from(
          { length: rows },
          () => html`<div class="trow" style=${rowStyle}>
            ${Array.from({ length: cols }, cell)}
          </div>`
        )}
      </div>
    `;
  }

  /** Preset chart: barras con alturas pseudo-variadas. */
  private renderPresetChart(): unknown {
    const n = Math.max(1, this.cols);
    // Alturas deterministas (no random) para un look creíble sin saltos en re-render.
    const heights = [40, 70, 55, 90, 35, 65, 80, 50, 75, 45, 60, 85];
    return html`
      <div class="preset-chart" part="chart">
        ${Array.from(
          { length: n },
          (_, i) => html`<div
            class="bar"
            style="height:${heights[i % heights.length]}%"
          ></div>`
        )}
      </div>
    `;
  }

  render(): unknown {
    let content: unknown;
    switch (this.preset) {
      case 'card':
        content = this.renderPresetCard();
        break;
      case 'table':
        content = this.renderPresetTable();
        break;
      case 'chart':
        content = this.renderPresetChart();
        break;
      default:
        content =
          this.lines > 1 ? this.renderStack() : this.renderBlock();
    }
    return html`
      <div role="status" aria-busy="true" aria-live="polite">${content}</div>
    `;
  }
}

define('ok-skeleton', OkSkeleton);

declare global {
  interface HTMLElementTagNameMap {
    'ok-skeleton': OkSkeleton;
  }
}
