import { LitElement, html, css } from 'lit';
import { property } from 'lit/decorators.js';
import { define } from '../../base/define.js';

/** Estado de la fila de archivo. */
export type OkFileItemState = 'done' | 'uploading' | 'error';

// ok-file-item — fila de subida/adjunto (compañero de ok-dropzone).
// Grid 36px|1fr|auto|auto: badge cuadrado tintado por extensión + nombre
// elipsado + meta tabular + botón fantasma de quitar/cancelar. Barra fina
// de progreso (relleno de marca) a todo el ancho mientras se sube.
export class OkFileItem extends LitElement {
  static styles = css`
    :host {
      display: block;
      width: 100%;
      /* Tokens propios estilo Ionic: --ok-* → --ion-* → hex. */
      --bg: var(--ok-surface-step-50, var(--ion-color-step-50, #f7f8fa));
      --border: var(--ok-border-color, var(--ion-border-color, #e4e7ec));
      --border-hover: var(--ok-color-step-200, var(--ion-color-step-200, #cdd1d8));
      --radius: var(--ok-radius-md, 10px);
      --radius-sm: var(--ok-radius-sm, 7px);
      --ink: var(--ok-text-color, var(--ion-text-color, #1f2933));
      --ink-2: var(--ok-color-step-600, var(--ion-color-step-600, #565a63));
      --ink-3: var(--ok-color-medium, var(--ion-color-medium, #92949c));
      --badge-bg: var(--ok-color-step-100, var(--ion-color-step-100, #eef0f3));
      --brand: var(--ok-color-primary, var(--ion-color-primary, #0091ce));
      --danger: var(--ok-color-danger, var(--ion-color-danger, #eb445a));
      --leaf: var(--ok-color-success, var(--ion-color-success, #2dd55b));
      --info: var(--ok-color-primary, var(--ion-color-primary, #0091ce));
      --warn: var(--ok-color-warning, var(--ion-color-warning, #ffc409));
      --track: var(--ok-color-step-100, var(--ion-color-step-100, #eef0f3));
    }

    .item {
      display: grid;
      grid-template-columns: 36px 1fr auto auto;
      gap: 12px;
      align-items: center;
      box-sizing: border-box;
      padding: 10px 12px;
      background: var(--bg);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      transition: border-color 0.18s ease-out;
    }
    .item:hover {
      border-color: var(--border-hover);
    }
    .item.error {
      border-color: var(--danger);
    }

    /* Badge cuadrado mono uppercase, tintado por extensión. */
    .badge {
      width: 36px;
      height: 36px;
      border-radius: var(--radius-sm);
      display: inline-flex;
      align-items: center;
      justify-content: center;
      background: var(--badge-bg);
      color: var(--ink-2);
      font-family: var(
        --ok-font-mono,
        ui-monospace,
        'SFMono-Regular',
        'Menlo',
        'Consolas',
        monospace
      );
      font-size: 10px;
      font-weight: 600;
      line-height: 1;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }
    .badge.pdf {
      background: color-mix(in srgb, var(--danger) 16%, transparent);
      color: var(--danger);
    }
    .badge.xls {
      background: color-mix(in srgb, var(--leaf) 16%, transparent);
      color: var(--leaf);
    }
    .badge.img {
      background: color-mix(in srgb, var(--info) 16%, transparent);
      color: var(--info);
    }
    .badge.zip {
      background: color-mix(in srgb, var(--warn) 22%, transparent);
      color: var(--warn);
    }

    .body {
      min-width: 0;
    }
    .name {
      font-size: 13px;
      font-weight: 500;
      color: var(--ink);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .meta {
      margin-top: 1px;
      font-size: 11.5px;
      color: var(--ink-3);
      font-variant-numeric: tabular-nums;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .meta.error {
      color: var(--danger);
    }

    /* Mini barra de progreso compacta (columna auto, al estilo attachment). */
    .progress {
      width: 80px;
      height: 4px;
      background: var(--track);
      border-radius: 999px;
      overflow: hidden;
    }
    .progress > i {
      display: block;
      height: 100%;
      background: var(--brand);
      border-radius: inherit;
      transition: width 0.4s ease-out;
    }

    /* Botón fantasma de quitar/cancelar. */
    .remove {
      width: 28px;
      height: 28px;
      border-radius: var(--radius-sm);
      background: transparent;
      border: none;
      color: var(--ink-3);
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      padding: 0;
      transition: background 0.15s ease-out, color 0.15s ease-out;
    }
    .remove:hover {
      background: var(--badge-bg);
      color: var(--danger);
    }
    .remove svg {
      width: 16px;
      height: 16px;
      display: block;
    }
  `;

  /** Nombre del archivo (se elipsa si no cabe). */
  @property() name = '';

  /** Tamaño legible ya formateado (p.ej. "2,4 MB"). */
  @property() size?: string;

  /** Extensión/tipo: pdf, xls, img, zip… → badge tintado. */
  @property() ext = '';

  /** Progreso 0–100, mostrado mientras sube. */
  @property({ type: Number }) progress = 0;

  /** Estado de la fila. */
  @property() state: OkFileItemState = 'done';

  /** Texto de error opcional (sustituye a la meta cuando state="error"). */
  @property() error?: string;

  /** Muestra el botón de quitar/cancelar. */
  @property({ type: Boolean }) removable = false;

  /** Normaliza la extensión a una de las variantes tintadas conocidas. */
  private variant(): string {
    const e = this.ext.trim().toLowerCase();
    if (!e) return '';
    if (e === 'pdf') return 'pdf';
    if (['xls', 'xlsx', 'csv', 'ods', 'numbers'].includes(e)) return 'xls';
    if (['img', 'jpg', 'jpeg', 'png', 'gif', 'webp', 'svg', 'heic', 'avif'].includes(e))
      return 'img';
    if (['zip', 'rar', '7z', 'tar', 'gz', 'bz2'].includes(e)) return 'zip';
    return '';
  }

  /** Etiqueta corta para el badge (máx 4 chars). */
  private badgeLabel(): string {
    const e = this.ext.trim();
    return (e || '?').slice(0, 4).toUpperCase();
  }

  private onRemove(): void {
    this.dispatchEvent(
      new CustomEvent('ok-remove', {
        detail: { name: this.name, ext: this.ext, state: this.state },
        bubbles: true,
        composed: true,
      })
    );
  }

  render(): unknown {
    const uploading = this.state === 'uploading';
    const isError = this.state === 'error';
    const pct = Math.max(0, Math.min(100, this.progress));

    // Meta: en error muestra el mensaje; en subida puede llevar el porcentaje.
    const metaText = isError ? this.error || 'Error al subir' : this.size;

    return html`
      <div class="item ${isError ? 'error' : ''}">
        <span class="badge ${this.variant()}" aria-hidden="true">${this.badgeLabel()}</span>

        <div class="body">
          <div class="name" title=${this.name}>${this.name}</div>
          ${metaText
            ? html`<div class="meta ${isError ? 'error' : ''}">${metaText}</div>`
            : null}
        </div>

        ${uploading
          ? html`<div
              class="progress"
              role="progressbar"
              aria-valuemin="0"
              aria-valuemax="100"
              aria-valuenow=${pct}
            >
              <i style="width:${pct}%"></i>
            </div>`
          : html`<span></span>`}

        ${this.removable
          ? html`<button
              class="remove"
              type="button"
              aria-label=${uploading ? 'Cancelar' : 'Quitar'}
              @click=${this.onRemove}
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
                stroke-linecap="round">
                <path d="M18 6 6 18M6 6l12 12" />
              </svg>
            </button>`
          : html`<span></span>`}
      </div>
    `;
  }
}

define('ok-file-item', OkFileItem);

declare global {
  interface HTMLElementTagNameMap {
    'ok-file-item': OkFileItem;
  }
}
