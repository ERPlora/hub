import { LitElement, html, css } from 'lit';
import { property, state, query } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// ok-dropzone — subida de archivos por arrastrar-y-soltar (drag & drop) + click.
// AUTOCONTENIDO: CSS propio en el shadow (sin Ionic salvo `ion-icon` para iconos de la zona y
// del botón de quitar archivo). Esconde un `<input type="file" hidden>` que se dispara al hacer
// click en la zona; arrastrar resalta el borde (dragover). Cada archivo se valida por tipo
// (`accept`) y tamaño (`max-size`); los inválidos no se añaden y se reporta el error inline.
//   • prop `accept`    → filtro de tipos, p.ej. '.csv,image/*' (vacío = cualquiera)
//   • prop `multiple`  → permite seleccionar/soltar varios archivos
//   • prop `max-size`  → tamaño máximo por archivo en bytes (opcional)
//   • prop `hint`      → texto de ayuda bajo el icono (opcional)
// Eventos (bubbles + composed):
//   • `ok-change`  detail { files: File[] }   → lista actual de archivos válidos
//   • `ok-error`   detail { message: string } → archivo rechazado (tipo o tamaño)

// Textos i18n del componente (default inglés). Pásalos vía la prop `.labels`.
export interface OkDropzoneLabels {
  /** Texto principal de la zona. Usa {browse} como ancla del enlace "selecciónalos". */
  title: string;
  /** Texto del enlace (la palabra resaltada dentro de `title`). */
  browse: string;
  /** Error de tipo no admitido. Variable: {name}. */
  errorType: string;
  /** Error de tamaño excedido. Variables: {name}, {size}. */
  errorSize: string;
  /** aria-label del botón de quitar un archivo. Variable: {name}. */
  removeLabel: string;
}

const DEFAULT_LABELS: OkDropzoneLabels = {
  title: 'Drag & drop files here or {browse}',
  browse: 'browse',
  errorType: '“{name}” is not an accepted file type.',
  errorSize: '“{name}” exceeds the maximum size ({size}).',
  removeLabel: 'Remove {name}',
};

export class OkDropzone extends LitElement {
  static styles = css`
    :host {
      /* Vars overridable (estilo Ionic), default = cadena --ok-* → --ion-* → hex */
      --color: var(--ok-text, var(--ion-text-color, #1c1b17));
      --color-muted: var(--ok-text-muted, rgba(var(--ion-text-color-rgb, 28, 27, 23), 0.55));
      --primary-color: var(--ok-primary, var(--ion-color-primary, #3880ff));
      --primary-tint: var(--ok-primary-tint, var(--ion-color-primary-tint, #4c8dff));
      --danger-color: var(--ok-danger, var(--ion-color-danger, #c5000f));
      --border-color: var(--ok-border, rgba(var(--ion-text-color-rgb, 28, 27, 23), 0.22));
      --hover-bg: var(--ok-hover, rgba(var(--ion-text-color-rgb, 28, 27, 23), 0.04));
      --primary-bg: var(--ok-primary-soft, rgba(var(--ion-color-primary-rgb, 56, 128, 255), 0.08));
      --surface: var(--ok-surface, var(--ion-card-background, #ffffff));
      --border-radius: var(--ok-radius, 10px);
      --font: var(--ok-font, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif);

      /* Responsive: ocupa el ancho del contenedor con un tope legible. */
      display: block;
      width: 100%;
      max-width: var(--ok-dropzone-max-width, 480px);
      color: var(--color);
      font-family: var(--font);
      font-size: 0.95rem;
    }
    .zone {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 0.4rem;
      box-sizing: border-box;
      width: 100%;
      padding: 1.5rem 1rem;
      text-align: center;
      border: 2px dashed var(--border-color);
      border-radius: var(--border-radius);
      background: var(--surface);
      cursor: pointer;
      transition: background-color var(--ok-transition, 150ms ease),
        color var(--ok-transition, 150ms ease),
        border-color var(--ok-transition, 150ms ease),
        box-shadow var(--ok-transition, 150ms ease), transform 120ms ease;
    }
    @media (hover: hover) {
      .zone:hover {
        background: var(--hover-bg);
      }
    }
    .zone:active {
      transform: scale(var(--ok-press-scale, 0.97));
    }
    /* Estado mientras se arrastra un fichero por encima. */
    .zone.dragging {
      border-color: var(--primary-color);
      background: var(--primary-bg);
    }
    @media (prefers-reduced-motion: reduce) {
      .zone:active,
      .file .remove:active {
        transform: none;
      }
    }
    .zone .big-icon {
      font-size: 2rem;
      color: var(--primary-color);
    }
    .zone .title {
      font-weight: 600;
    }
    .zone .title .link {
      color: var(--primary-color);
      text-decoration: underline;
    }
    .zone .hint {
      font-size: 0.82rem;
      color: var(--color-muted);
    }
    /* Lista de archivos elegidos. */
    .files {
      list-style: none;
      margin: 0.7rem 0 0;
      padding: 0;
      display: flex;
      flex-direction: column;
      gap: 0.4rem;
    }
    .file {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      box-sizing: border-box;
      padding: 0.4rem 0.6rem;
      border: 1px solid var(--border-color);
      border-radius: var(--border-radius);
      background: var(--surface);
    }
    .file .file-icon {
      flex: 0 0 auto;
      font-size: 1.15rem;
      color: var(--color-muted);
    }
    .file .meta {
      flex: 1 1 auto;
      min-width: 0;
      display: flex;
      flex-direction: column;
    }
    .file .name {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .file .size {
      font-size: 0.78rem;
      color: var(--color-muted);
    }
    .file .remove {
      flex: 0 0 auto;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 26px;
      height: 26px;
      padding: 0;
      border: 0;
      background: none;
      color: var(--color-muted);
      cursor: pointer;
      border-radius: 50%;
      transition: background-color var(--ok-transition, 150ms ease),
        color var(--ok-transition, 150ms ease),
        border-color var(--ok-transition, 150ms ease),
        box-shadow var(--ok-transition, 150ms ease), transform 120ms ease;
    }
    @media (hover: hover) {
      .file .remove:hover {
        background: var(--hover-bg);
        color: var(--danger-color);
      }
    }
    .file .remove:active {
      transform: scale(var(--ok-press-scale, 0.97));
    }
    /* Error inline (tipo/tamaño no admitido). */
    .error {
      display: flex;
      align-items: center;
      gap: 0.4rem;
      margin-top: 0.5rem;
      color: var(--danger-color);
      font-size: 0.82rem;
    }
    input[type='file'] {
      display: none;
    }
  `;

  /** Filtro de tipos aceptados (igual que el atributo `accept` nativo). Vacío = cualquiera. */
  @property() accept = '';
  /** Permite seleccionar/soltar varios archivos. */
  @property({ type: Boolean }) multiple = false;
  /** Tamaño máximo por archivo en bytes (opcional). */
  @property({ type: Number, attribute: 'max-size' }) maxSize?: number;
  /** Texto de ayuda mostrado bajo el icono. */
  @property() hint?: string;
  /** Textos i18n (default inglés); pasa solo las claves que quieras sobreescribir. */
  @property({ attribute: false }) labels: Partial<OkDropzoneLabels> = {};

  // Textos efectivos: defaults inglés sobreescritos por los pasados desde fuera.
  private get t(): OkDropzoneLabels {
    return { ...DEFAULT_LABELS, ...this.labels };
  }

  // Archivos válidos acumulados.
  @state() private files: File[] = [];
  // Estado visual de arrastre.
  @state() private dragging = false;
  // Mensaje de error inline (vacío = sin error).
  @state() private error = '';

  @query('input[type="file"]') private input!: HTMLInputElement;

  // Formatea bytes a una etiqueta legible (B, KB, MB…).
  private formatSize(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    const units = ['KB', 'MB', 'GB', 'TB'];
    let value = bytes / 1024;
    let i = 0;
    while (value >= 1024 && i < units.length - 1) {
      value /= 1024;
      i += 1;
    }
    return `${value.toFixed(value >= 10 || i === 0 ? 0 : 1)} ${units[i]}`;
  }

  // Comprueba si un archivo casa con `accept` (extensiones, mime exacto o `tipo/*`).
  private matchesAccept(file: File): boolean {
    if (!this.accept.trim()) return true;
    const tokens = this.accept
      .split(',')
      .map((t) => t.trim().toLowerCase())
      .filter(Boolean);
    const name = file.name.toLowerCase();
    const mime = file.type.toLowerCase();
    return tokens.some((token) => {
      if (token.startsWith('.')) return name.endsWith(token);
      if (token.endsWith('/*')) return mime.startsWith(token.slice(0, -1));
      return mime === token;
    });
  }

  // Emite `ok-error` con el mensaje dado y lo guarda para mostrarlo inline.
  private reportError(message: string): void {
    this.error = message;
    this.dispatchEvent(
      new CustomEvent('ok-error', {
        detail: { message },
        bubbles: true,
        composed: true,
      }),
    );
  }

  // Emite `ok-change` con la lista actual de archivos válidos.
  private emitChange(): void {
    this.dispatchEvent(
      new CustomEvent('ok-change', {
        detail: { files: this.files },
        bubbles: true,
        composed: true,
      }),
    );
  }

  // Procesa un FileList (de input o de drop), valida y añade los aceptados.
  private ingest(list: FileList | null): void {
    if (!list || !list.length) return;
    this.error = '';
    const incoming = Array.from(list);
    // En modo single solo se queda el último válido.
    const next = this.multiple ? [...this.files] : [];
    for (const file of incoming) {
      if (!this.matchesAccept(file)) {
        this.reportError(this.t.errorType.replace('{name}', file.name));
        continue;
      }
      if (this.maxSize != null && file.size > this.maxSize) {
        this.reportError(
          this.t.errorSize
            .replace('{name}', file.name)
            .replace('{size}', this.formatSize(this.maxSize)),
        );
        continue;
      }
      // Evita duplicados (mismo nombre + tamaño) en modo multiple.
      const dup = next.some((f) => f.name === file.name && f.size === file.size);
      if (!dup) next.push(file);
      if (!this.multiple) break;
    }
    this.files = next;
    this.emitChange();
  }

  // Quita un archivo de la lista por índice y re-emite el cambio.
  private removeAt(index: number): void {
    this.files = this.files.filter((_, i) => i !== index);
    this.error = '';
    this.emitChange();
  }

  private openPicker(): void {
    this.input?.click();
  }

  private onInputChange(e: Event): void {
    const target = e.target as HTMLInputElement;
    this.ingest(target.files);
    // Permite volver a elegir el mismo archivo (resetea el input nativo).
    target.value = '';
  }

  private onDragOver(e: DragEvent): void {
    e.preventDefault();
    this.dragging = true;
  }

  private onDragLeave(e: DragEvent): void {
    e.preventDefault();
    this.dragging = false;
  }

  private onDrop(e: DragEvent): void {
    e.preventDefault();
    this.dragging = false;
    this.ingest(e.dataTransfer?.files ?? null);
  }

  render(): unknown {
    // El título lleva el enlace "browse" embebido vía marcador {browse}: lo partimos.
    const [titleBefore, titleAfter = ''] = this.t.title.split('{browse}');
    return html`
      <div
        class=${`zone ${this.dragging ? 'dragging' : ''}`.trim()}
        role="button"
        tabindex="0"
        @click=${this.openPicker}
        @keydown=${(e: KeyboardEvent) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            this.openPicker();
          }
        }}
        @dragover=${this.onDragOver}
        @dragleave=${this.onDragLeave}
        @drop=${this.onDrop}
      >
        <ion-icon class="big-icon" name="cloud-upload-outline"></ion-icon>
        <span class="title">
          ${titleBefore}<span class="link">${this.t.browse}</span>${titleAfter}
        </span>
        ${this.hint ? html`<span class="hint">${this.hint}</span>` : ''}
      </div>

      <input
        type="file"
        ?multiple=${this.multiple}
        accept=${this.accept || ''}
        @change=${this.onInputChange}
      />

      ${this.error ? html`<div class="error"><ion-icon name="alert-circle-outline"></ion-icon>${this.error}</div>` : ''}

      ${this.files.length
        ? html`<ul class="files">
            ${this.files.map(
              (file, i) => html`<li class="file">
                <ion-icon class="file-icon" name="document-outline"></ion-icon>
                <span class="meta">
                  <span class="name">${file.name}</span>
                  <span class="size">${this.formatSize(file.size)}</span>
                </span>
                <button
                  type="button"
                  class="remove"
                  aria-label=${this.t.removeLabel.replace('{name}', file.name)}
                  @click=${(e: Event) => {
                    e.stopPropagation();
                    this.removeAt(i);
                  }}
                >
                  <ion-icon name="close-outline"></ion-icon>
                </button>
              </li>`,
            )}
          </ul>`
        : ''}
    `;
  }
}

define('ok-dropzone', OkDropzone);

declare global {
  interface HTMLElementTagNameMap {
    'ok-dropzone': OkDropzone;
  }
}
