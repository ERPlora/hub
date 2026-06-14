import { LitElement, html, css } from 'lit';
import { property, state, query } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// ok-file-manager — widget de gestor de archivos AUTOCONTENIDO y BACKEND-AGNÓSTICO.
// Solo RENDERIZA (árbol de carpetas + meter de espacio + breadcrumb + toolbar con búsqueda,
// toggle grid/lista y subida + rejilla/lista de archivos) y EMITE eventos `ok-*`; el host
// cablea el almacenamiento (Local en disco o Cloud S3). No trae datos demo dentro: todo
// llega por props. CSS propio en el shadow; solo usa `ion-icon`/`ion-searchbar`/`ion-segment`/
// `ion-button` NATIVOS que registra el host (no se importa Ionic aquí).
//
// Layout: 2 columnas (árbol ~260px + main); bajo 768px el árbol colapsa a un <select> de
// carpetas y el área de archivos se apila. El área principal es además una zona de
// arrastrar-y-soltar (dragover resalta) al estilo de ok-dropzone.

/** Carpeta del árbol lateral (recursiva). La aporta el host vía `.folders`. */
export interface OkFmFolder {
  /** Identificador único de la carpeta (clave de navegación/selección). */
  id: string;
  /** Texto visible de la carpeta. */
  label: string;
  /** Nombre de un ionicon opcional, mostrado antes del label. */
  icon?: string;
  /** Recuento de elementos, alineado a la derecha en la fila. */
  count?: number;
  /** Sub-carpetas; si las hay, se dibuja el caret expandible. */
  children?: OkFmFolder[];
}

/** Archivo del contenido de la carpeta actual. Lo aporta el host vía `.files`. */
export interface OkFmFile {
  /** Identificador único del archivo. */
  id: string;
  /** Nombre del archivo (se elipsa si no cabe). */
  name: string;
  /** Extensión/tipo (pdf, xls, png…) → badge tintado. Si falta, se deriva del nombre. */
  ext?: string;
  /** Etiqueta de categoría opcional (no usada para el color; informativa). */
  kind?: string;
  /** Tamaño ya formateado y legible (p.ej. "218 KB"). */
  sizeLabel?: string;
  /** Fecha de modificación ya formateada (p.ej. "2026-05-08 09:14"). */
  modified?: string;
  /** URL de descarga/abrir opcional (se pasa en `ok-download`). */
  url?: string;
  /** URL de miniatura opcional (imágenes); si está, se muestra en lugar del icono. */
  thumb?: string;
}

/** Migaja del breadcrumb (de raíz a carpeta actual). */
export interface OkFmCrumb {
  /** Id de la carpeta a la que navega al hacer click. */
  id: string;
  /** Texto visible de la migaja. */
  label: string;
}

/** Medidor de espacio de almacenamiento (bajo el árbol). */
export interface OkFmQuota {
  /** Etiqueta del espacio usado (p.ej. "1,8 GB usados"). */
  usedLabel: string;
  /** Etiqueta del espacio total (p.ej. "5 GB"). Opcional: ausente ⇒ modo "sin límite". */
  totalLabel?: string;
  /** Fracción ocupada 0–1 (ancho de la barra). Ignorada en modo "sin límite". */
  fraction?: number;
  /** Sin cuota dura (p.ej. bucket S3 por hub): muestra solo lo usado, sin barra. */
  unlimited?: boolean;
}

/** Modo de visualización del área de archivos. */
export type OkFmView = 'grid' | 'list';

/** Textos i18n del componente (defaults en español). */
export interface OkFmLabels {
  /** Botón primario de subida. */
  upload: string;
  /** Botón de importar. */
  import: string;
  /** Placeholder del buscador. */
  search: string;
  /** Eyebrow del árbol de carpetas. */
  folders: string;
  /** Eyebrow del medidor de espacio. */
  space: string;
  /** Estado vacío (sin archivos). */
  empty: string;
  /** Acción de fila: descargar. */
  download: string;
  /** Acción de fila: eliminar. */
  delete: string;
  /** Acción de fila: abrir. */
  open: string;
  /** Botón de nueva carpeta. */
  newFolder: string;
  /** Caption del medidor cuando no hay cuota dura. */
  noLimit: string;
}

const DEFAULT_LABELS: OkFmLabels = {
  upload: 'Subir archivo',
  import: 'Importar',
  search: 'Buscar archivos…',
  folders: 'Carpetas',
  space: 'Espacio',
  empty: 'Sin archivos',
  download: 'Descargar',
  delete: 'Eliminar',
  open: 'Abrir',
  newFolder: 'Nueva carpeta',
  noLimit: 'Sin límite',
};

export class OkFileManager extends LitElement {
  static styles = css`
    :host {
      /* Tokens propios estilo Ionic: cadena --ok-* → --ion-* → hex. */
      --bg: var(--ok-surface, var(--ion-background-color, #ffffff));
      --bg-2: var(--ok-surface-step-50, var(--ion-color-step-50, #f7f8fa));
      --border: var(--ok-border-color, var(--ion-border-color, #e4e7ec));
      --border-hover: var(--ok-color-step-200, var(--ion-color-step-200, #cdd1d8));
      --radius: var(--ok-radius-md, 12px);
      --radius-sm: var(--ok-radius-sm, 8px);
      --ink: var(--ok-text-color, var(--ion-text-color, #1f2933));
      --ink-2: var(--ok-color-step-600, var(--ion-color-step-600, #565a63));
      --ink-3: var(--ok-color-medium, var(--ion-color-medium, #92949c));
      --badge-bg: var(--ok-color-step-100, var(--ion-color-step-100, #eef0f3));
      --hover-bg: var(--ok-hover, rgba(var(--ion-text-color-rgb, 28, 27, 23), 0.05));
      --brand: var(--ok-color-primary, var(--ion-color-primary, #0091ce));
      --brand-rgb: var(--ok-color-primary-rgb, var(--ion-color-primary-rgb, 0, 145, 206));
      --danger: var(--ok-color-danger, var(--ion-color-danger, #eb445a));
      --leaf: var(--ok-color-success, var(--ion-color-success, #2dd55b));
      --info: var(--ok-color-primary, var(--ion-color-primary, #0091ce));
      --warn: var(--ok-color-warning, var(--ion-color-warning, #ffc409));
      --doc: var(--ok-color-primary, var(--ion-color-primary, #0091ce));
      --track: var(--ok-color-step-100, var(--ion-color-step-100, #eef0f3));
      --tree-width: var(--ok-fm-tree-width, 260px);
      --font: var(--ok-font, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif);

      display: block;
      width: 100%;
      color: var(--ink);
      font-family: var(--font);
      font-size: 0.95rem;
    }

    /* Disposición en 2 columnas: árbol + main. */
    .wrap {
      display: grid;
      grid-template-columns: var(--tree-width) 1fr;
      gap: 16px;
      align-items: start;
    }

    .panel {
      background: var(--bg-2);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      box-sizing: border-box;
    }

    /* ---- Árbol lateral ---- */
    .aside {
      padding: 12px;
      position: sticky;
      top: 0;
    }
    .eyebrow {
      font-size: 11px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: var(--ink-3);
      padding: 4px 8px 8px;
    }
    [role='tree'],
    [role='group'] {
      margin: 0;
      padding: 0;
      list-style: none;
    }
    [role='group'] {
      margin-left: 14px;
      padding-left: 8px;
      border-left: 1px solid var(--border);
    }
    .trow {
      display: flex;
      align-items: center;
      gap: 6px;
      width: 100%;
      box-sizing: border-box;
      padding: 7px 8px;
      border-radius: var(--radius-sm);
      cursor: pointer;
      user-select: none;
      color: var(--ink-2);
      transition: background 0.15s ease, color 0.15s ease;
    }
    @media (hover: hover) {
      .trow:hover {
        background: var(--hover-bg);
      }
    }
    .trow.active {
      background: color-mix(in srgb, var(--brand) 14%, transparent);
      color: var(--brand);
      font-weight: 600;
    }
    .caret {
      flex: 0 0 auto;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 18px;
      height: 18px;
      padding: 0;
      border: 0;
      background: none;
      color: inherit;
      cursor: pointer;
      border-radius: 4px;
    }
    .caret.leaf {
      visibility: hidden;
    }
    .caret ion-icon {
      font-size: 0.95rem;
      transition: transform 0.18s ease;
    }
    .caret.open ion-icon {
      transform: rotate(90deg);
    }
    .ticon {
      flex: 0 0 auto;
      display: inline-flex;
      align-items: center;
      font-size: 1.05rem;
      color: var(--ink-3);
    }
    .trow.active .ticon {
      color: inherit;
    }
    .tlabel {
      flex: 1 1 auto;
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .tcount {
      flex: 0 0 auto;
      font-size: 11.5px;
      font-variant-numeric: tabular-nums;
      color: var(--ink-3);
    }
    .trow.active .tcount {
      color: inherit;
    }

    /* Medidor de espacio. */
    .quota {
      margin-top: 12px;
      padding: 12px 8px 4px;
      border-top: 1px solid var(--border);
    }
    .meter {
      height: 8px;
      background: var(--track);
      border-radius: 999px;
      overflow: hidden;
    }
    .meter > i {
      display: block;
      height: 100%;
      background: var(--brand);
      border-radius: inherit;
      transition: width 0.4s ease-out;
    }
    .quota-meta {
      display: flex;
      justify-content: space-between;
      margin-top: 6px;
      font-size: 11.5px;
      color: var(--ink-3);
      font-variant-numeric: tabular-nums;
    }

    /* Selector de carpeta para móvil (oculto en desktop). */
    .folder-select {
      display: none;
    }

    /* ---- Main ---- */
    .main {
      overflow: hidden;
      position: relative;
    }
    .main.dragging::after {
      content: '';
      position: absolute;
      inset: 0;
      pointer-events: none;
      border: 2px dashed var(--brand);
      border-radius: var(--radius);
      background: rgba(var(--brand-rgb), 0.08);
      z-index: 2;
    }

    /* Toolbar. */
    .toolbar {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 8px;
      padding: 12px;
      border-bottom: 1px solid var(--border);
    }
    .crumbs {
      display: flex;
      align-items: center;
      gap: 4px;
      flex: 1 1 200px;
      min-width: 0;
      font-size: 12px;
      color: var(--ink-3);
      flex-wrap: wrap;
    }
    .fm-title {
      flex: 0 0 100%;
      font-size: 14px;
      font-weight: 600;
      color: var(--ink);
      margin-bottom: 2px;
    }
    .crumb {
      background: none;
      border: 0;
      padding: 0;
      cursor: pointer;
      color: var(--brand);
      font: inherit;
      text-decoration: none;
    }
    .crumb:hover {
      text-decoration: underline;
    }
    .crumb.current {
      color: var(--ink);
      font-weight: 500;
      cursor: default;
    }
    .crumb.current:hover {
      text-decoration: none;
    }
    .crumb-sep {
      display: inline-flex;
      color: var(--ink-3);
      font-size: 0.8rem;
    }
    .search {
      flex: 0 1 240px;
      min-width: 140px;
    }
    /* Buscador plano: sin borde ni sombra, se funde con la toolbar. */
    ion-searchbar {
      --background: transparent;
      --border-radius: var(--radius-sm);
      --box-shadow: none;
      --border-width: 0;
      padding: 0;
      min-height: 36px;
    }
    .view-toggle {
      display: inline-flex;
      gap: 2px;
      background: var(--badge-bg);
      border-radius: var(--radius-sm);
      padding: 2px;
    }
    .view-btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 30px;
      height: 30px;
      padding: 0;
      border: 0;
      background: none;
      color: var(--ink-3);
      cursor: pointer;
      border-radius: 6px;
      transition: background 0.15s ease, color 0.15s ease;
    }
    .view-btn[aria-pressed='true'] {
      background: var(--bg);
      color: var(--brand);
      box-shadow: 0 1px 2px rgba(0, 0, 0, 0.08);
    }
    .view-btn svg {
      width: 17px;
      height: 17px;
    }
    .tbtn {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      height: 34px;
      padding: 0 12px;
      border: 1px solid var(--border);
      border-radius: var(--radius-sm);
      background: var(--bg);
      color: var(--ink-2);
      font: inherit;
      font-size: 13px;
      font-weight: 500;
      cursor: pointer;
      transition: border-color 0.15s ease, background 0.15s ease;
    }
    .tbtn:hover {
      border-color: var(--border-hover);
    }
    .tbtn.primary {
      background: var(--brand);
      border-color: var(--brand);
      color: var(--ok-color-primary-contrast, var(--ion-color-primary-contrast, #fff));
    }
    .tbtn.primary:hover {
      filter: brightness(0.95);
    }
    .tbtn svg {
      width: 16px;
      height: 16px;
    }
    /* Variante solo-icono: botón cuadrado, sin texto (a11y vía aria-label/title). */
    .tbtn.icon {
      width: 34px;
      padding: 0;
      gap: 0;
      justify-content: center;
    }

    /* Badge cuadrado tintado por extensión (mismo idioma visual que ok-file-item). */
    .badge {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      border-radius: var(--radius-sm);
      background: var(--badge-bg);
      color: var(--ink-2);
      font-family: var(--ok-font-mono, ui-monospace, 'SFMono-Regular', 'Menlo', monospace);
      font-weight: 600;
      line-height: 1;
      text-transform: uppercase;
      letter-spacing: 0.03em;
      overflow: hidden;
    }
    .badge img {
      width: 100%;
      height: 100%;
      object-fit: cover;
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
    .badge.doc {
      background: color-mix(in srgb, var(--doc) 16%, transparent);
      color: var(--doc);
    }

    /* ---- Vista grid: cards auto-fill ---- */
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
      gap: 12px;
      padding: 14px;
    }
    .card {
      position: relative;
      display: flex;
      flex-direction: column;
      gap: 8px;
      box-sizing: border-box;
      padding: 12px;
      background: var(--bg);
      border: 1px solid var(--border);
      border-radius: var(--radius-sm);
      cursor: pointer;
      transition: border-color 0.15s ease, box-shadow 0.15s ease;
    }
    .card:hover {
      border-color: var(--border-hover);
      box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
    }
    .card .badge {
      width: 42px;
      height: 42px;
      font-size: 11px;
    }
    .card-name {
      font-size: 13px;
      font-weight: 500;
      color: var(--ink);
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .card-meta {
      font-size: 11.5px;
      color: var(--ink-3);
      font-variant-numeric: tabular-nums;
    }
    /* Acciones flotantes (aparecen al hover). */
    .card-actions {
      position: absolute;
      top: 8px;
      right: 8px;
      display: flex;
      gap: 2px;
      opacity: 0;
      transition: opacity 0.15s ease;
    }
    .card:hover .card-actions,
    .card:focus-within .card-actions {
      opacity: 1;
    }

    /* ---- Vista lista: filas ---- */
    .list {
      display: flex;
      flex-direction: column;
    }
    .lrow {
      display: grid;
      grid-template-columns: 36px 1fr auto auto auto;
      gap: 12px;
      align-items: center;
      box-sizing: border-box;
      padding: 10px 14px;
      border-bottom: 1px solid var(--border);
      cursor: pointer;
      transition: background 0.12s ease;
    }
    .lrow:hover {
      background: var(--hover-bg);
    }
    .lrow:last-child {
      border-bottom: 0;
    }
    .lrow .badge {
      width: 34px;
      height: 34px;
      font-size: 10px;
    }
    .lname {
      min-width: 0;
      font-size: 13px;
      font-weight: 500;
      color: var(--ink);
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .lsize {
      font-size: 12px;
      color: var(--ink-2);
      font-variant-numeric: tabular-nums;
      text-align: right;
      white-space: nowrap;
    }
    .lmod {
      font-size: 12px;
      color: var(--ink-3);
      font-variant-numeric: tabular-nums;
      white-space: nowrap;
    }
    .lactions {
      display: flex;
      gap: 2px;
      justify-content: flex-end;
    }

    /* Botón de acción de fila/card (fantasma). */
    .action {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 28px;
      height: 28px;
      padding: 0;
      border: 0;
      background: var(--bg);
      color: var(--ink-3);
      cursor: pointer;
      border-radius: 6px;
      transition: background 0.15s ease, color 0.15s ease;
    }
    .action:hover {
      background: var(--badge-bg);
      color: var(--ink);
    }
    .action.danger:hover {
      color: var(--danger);
    }
    .action svg {
      width: 15px;
      height: 15px;
    }

    /* Estado vacío. */
    .empty {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 10px;
      padding: 48px 16px;
      color: var(--ink-3);
      text-align: center;
    }
    .empty ion-icon {
      font-size: 2.4rem;
      color: var(--ink-3);
      opacity: 0.6;
    }

    /* Esqueletos de carga. */
    .skeleton {
      padding: 14px;
      display: flex;
      flex-direction: column;
      gap: 10px;
    }
    .sk-row {
      height: 48px;
      border-radius: var(--radius-sm);
      background: linear-gradient(
        90deg,
        var(--badge-bg) 25%,
        var(--track) 37%,
        var(--badge-bg) 63%
      );
      background-size: 400% 100%;
      animation: sk 1.4s ease infinite;
    }
    @keyframes sk {
      0% {
        background-position: 100% 50%;
      }
      100% {
        background-position: 0 50%;
      }
    }
    @media (prefers-reduced-motion: reduce) {
      .sk-row {
        animation: none;
      }
    }

    input[type='file'] {
      display: none;
    }

    /* ---- Responsive ≤768px: el árbol colapsa a un select y el main se apila ---- */
    @media (max-width: 768px) {
      .wrap {
        grid-template-columns: 1fr;
      }
      .aside {
        position: static;
      }
      .tree-host {
        display: none;
      }
      .folder-select {
        display: block;
      }
      .folder-select select {
        width: 100%;
        box-sizing: border-box;
        height: 40px;
        padding: 0 10px;
        border: 1px solid var(--border);
        border-radius: var(--radius-sm);
        background: var(--bg);
        color: var(--ink);
        font: inherit;
      }
      .grid {
        grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
      }
      .lrow {
        grid-template-columns: 34px 1fr auto;
      }
      .lmod {
        display: none;
      }
      .lsize {
        display: none;
      }
    }
  `;

  /** Árbol de carpetas (recursivo vía `children`). */
  @property({ attribute: false }) folders: OkFmFolder[] = [];
  /** Contenido de la carpeta actual. */
  @property({ attribute: false }) files: OkFmFile[] = [];
  /** Breadcrumb de raíz a carpeta actual. */
  @property({ attribute: false }) path: OkFmCrumb[] = [];
  /** Id de la carpeta activa/seleccionada. */
  @property() selected = '';
  /** Modo de visualización del área de archivos. */
  @property() view: OkFmView = 'grid';
  /** Medidor de espacio opcional bajo el árbol. */
  @property({ attribute: false }) quota?: OkFmQuota;
  /** Título opcional sobre la toolbar (informativo). Vacío = sin título. */
  @property() title = '';
  /** Muestra el buscador en la toolbar. */
  @property({ type: Boolean }) searchable = true;
  /** Muestra el botón primario de subida y habilita drag&drop. */
  @property({ type: Boolean }) uploadable = true;
  /** Muestra esqueletos de carga en lugar del contenido. */
  @property({ type: Boolean }) loading = false;
  /** Textos i18n (merge sobre los defaults en español). */
  @property({ attribute: false }) labels: Partial<OkFmLabels> = {};

  // Textos efectivos.
  private get t(): OkFmLabels {
    return { ...DEFAULT_LABELS, ...this.labels };
  }

  // Estado de expansión del árbol por id (todas abiertas por defecto la 1ª vez).
  @state() private expandedIds = new Set<string>();
  // Resaltado visual mientras se arrastra un fichero sobre el main.
  @state() private dragging = false;
  private seeded = false;

  @query('input[type="file"]') private fileInput!: HTMLInputElement;

  // Temporizador del debounce de búsqueda.
  private searchTimer?: ReturnType<typeof setTimeout>;

  // Siembra: expande todas las carpetas con hijos la primera vez.
  private seedExpanded(folders: OkFmFolder[]): void {
    for (const f of folders) {
      if (f.children?.length) {
        this.expandedIds.add(f.id);
        this.seedExpanded(f.children);
      }
    }
  }

  // ---- Emisores de eventos ----
  private emit<T>(name: string, detail: T): void {
    this.dispatchEvent(new CustomEvent<T>(name, { detail, bubbles: true, composed: true }));
  }

  private navigate(id: string): void {
    this.emit('ok-navigate', { id });
  }

  private open(id: string): void {
    this.emit('ok-open', { id });
  }

  private download(file: OkFmFile): void {
    this.emit('ok-download', { id: file.id, url: file.url });
  }

  private deleteFile(id: string): void {
    this.emit('ok-delete', { id });
  }

  private createFolder(): void {
    this.emit('ok-create-folder', { parent: this.selected });
  }

  private changeView(view: OkFmView): void {
    if (view === this.view) return;
    this.view = view;
    this.emit('ok-view-change', { view });
  }

  // Búsqueda con debounce (250ms).
  private onSearch(e: Event): void {
    const value = (e.target as HTMLInputElement | null)?.value ?? '';
    if (this.searchTimer) clearTimeout(this.searchTimer);
    this.searchTimer = setTimeout(() => {
      this.emit('ok-search', { query: value });
    }, 250);
  }

  // ---- Subida ----
  private openPicker(): void {
    this.fileInput?.click();
  }

  private onPicked(e: Event): void {
    const input = e.target as HTMLInputElement;
    const files = input.files ? Array.from(input.files) : [];
    if (files.length) this.emit('ok-upload', { files });
    input.value = '';
  }

  private toggle(folder: OkFmFolder): void {
    const next = new Set(this.expandedIds);
    if (next.has(folder.id)) next.delete(folder.id);
    else next.add(folder.id);
    this.expandedIds = next;
  }

  // ---- Drag & drop sobre el main ----
  private onDragOver(e: DragEvent): void {
    if (!this.uploadable) return;
    e.preventDefault();
    this.dragging = true;
  }

  private onDragLeave(e: DragEvent): void {
    if (!this.uploadable) return;
    e.preventDefault();
    this.dragging = false;
  }

  private onDrop(e: DragEvent): void {
    if (!this.uploadable) return;
    e.preventDefault();
    this.dragging = false;
    const files = e.dataTransfer?.files ? Array.from(e.dataTransfer.files) : [];
    if (files.length) this.emit('ok-upload', { files });
  }

  // Deriva la extensión: usa `ext` o la cola del nombre.
  private extOf(file: OkFmFile): string {
    if (file.ext) return file.ext.trim().toLowerCase();
    const dot = file.name.lastIndexOf('.');
    return dot >= 0 ? file.name.slice(dot + 1).toLowerCase() : '';
  }

  // Normaliza la extensión a una de las variantes tintadas conocidas.
  private variant(ext: string): string {
    if (!ext) return '';
    if (ext === 'pdf') return 'pdf';
    if (['xls', 'xlsx', 'csv', 'ods', 'numbers'].includes(ext)) return 'xls';
    if (['img', 'jpg', 'jpeg', 'png', 'gif', 'webp', 'svg', 'heic', 'avif'].includes(ext))
      return 'img';
    if (['zip', 'rar', '7z', 'tar', 'gz', 'bz2'].includes(ext)) return 'zip';
    if (['doc', 'docx', 'odt', 'rtf', 'txt', 'md'].includes(ext)) return 'doc';
    return '';
  }

  // Etiqueta corta del badge (máx 4 chars).
  private badgeLabel(ext: string): string {
    return (ext || '?').slice(0, 4).toUpperCase();
  }

  // Render del badge tintado (miniatura si hay thumb de imagen).
  private renderBadge(file: OkFmFile): unknown {
    const ext = this.extOf(file);
    const v = this.variant(ext);
    if (file.thumb && v === 'img') {
      return html`<span class="badge ${v}"><img src=${file.thumb} alt="" /></span>`;
    }
    return html`<span class="badge ${v}" aria-hidden="true">${this.badgeLabel(ext)}</span>`;
  }

  // ---- Render del árbol (recursivo) ----
  private renderFolder(folder: OkFmFolder): unknown {
    const hasChildren = !!folder.children?.length;
    const expanded = hasChildren && this.expandedIds.has(folder.id);
    const active = folder.id === this.selected;

    return html`<li role="treeitem" aria-selected=${active ? 'true' : 'false'} aria-expanded=${
      hasChildren ? String(expanded) : ''
    }>
      <div class=${`trow ${active ? 'active' : ''}`.trim()} @click=${() => this.navigate(folder.id)}>
        <button
          type="button"
          class=${`caret ${hasChildren ? '' : 'leaf'} ${expanded ? 'open' : ''}`.trim()}
          tabindex=${hasChildren ? '0' : '-1'}
          aria-hidden=${hasChildren ? 'false' : 'true'}
          aria-label=${expanded ? 'Colapsar' : 'Expandir'}
          @click=${(e: Event) => {
            e.stopPropagation();
            this.toggle(folder);
          }}
        >
          <ion-icon name="chevron-forward-outline"></ion-icon>
        </button>
        <span class="ticon"
          ><ion-icon name=${folder.icon || 'folder-outline'}></ion-icon
        ></span>
        <span class="tlabel" title=${folder.label}>${folder.label}</span>
        ${folder.count != null
          ? html`<span class="tcount">${folder.count}</span>`
          : ''}
      </div>
      ${expanded
        ? html`<ul role="group">
            ${folder.children!.map((c) => this.renderFolder(c))}
          </ul>`
        : ''}
    </li>`;
  }

  // Aplana el árbol para el <select> de móvil (con sangría por nivel).
  private flatFolders(folders: OkFmFolder[], depth = 0, out: { f: OkFmFolder; d: number }[] = []) {
    for (const f of folders) {
      out.push({ f, d: depth });
      if (f.children?.length) this.flatFolders(f.children, depth + 1, out);
    }
    return out;
  }

  // ---- Render del medidor de espacio ----
  private renderQuota(): unknown {
    if (!this.quota) return '';
    // Modo "sin límite" (p.ej. bucket S3 por hub): solo lo usado, sin barra de fracción.
    const unlimited = this.quota.unlimited || this.quota.totalLabel == null;
    if (unlimited) {
      return html`<div class="quota">
        <div class="eyebrow" style="padding:0 0 6px;">${this.t.space}</div>
        <div class="quota-meta">
          <span>${this.quota.usedLabel}</span><span>${this.t.noLimit}</span>
        </div>
      </div>`;
    }
    const pct = Math.max(0, Math.min(100, (this.quota.fraction ?? 0) * 100));
    return html`<div class="quota">
      <div class="eyebrow" style="padding:0 0 6px;">${this.t.space}</div>
      <div
        class="meter"
        role="progressbar"
        aria-valuemin="0"
        aria-valuemax="100"
        aria-valuenow=${Math.round(pct)}
      >
        <i style="width:${pct}%"></i>
      </div>
      <div class="quota-meta">
        <span>${this.quota.usedLabel}</span><span>${this.quota.totalLabel}</span>
      </div>
    </div>`;
  }

  // ---- Render de la toolbar ----
  private renderToolbar(): unknown {
    const crumbs = this.path;
    return html`<div class="toolbar">
      <nav class="crumbs" aria-label="Ruta">
        ${this.title ? html`<span class="fm-title">${this.title}</span>` : ''}
        ${crumbs.map((c, i) => {
          const isLast = i === crumbs.length - 1;
          return html`${i > 0
              ? html`<span class="crumb-sep" aria-hidden="true"
                  ><ion-icon name="chevron-forward-outline"></ion-icon
                ></span>`
              : ''}<button
              type="button"
              class=${`crumb ${isLast ? 'current' : ''}`.trim()}
              aria-current=${isLast ? 'page' : 'false'}
              @click=${() => !isLast && this.navigate(c.id)}
            >
              ${c.label}
            </button>`;
        })}
      </nav>

      ${this.searchable
        ? html`<div class="search">
            <ion-searchbar
              placeholder=${this.t.search}
              debounce="0"
              @ionInput=${(e: Event) => this.onSearch(e)}
            ></ion-searchbar>
          </div>`
        : ''}

      <div class="view-toggle" role="group" aria-label="Vista">
        <button
          type="button"
          class="view-btn"
          aria-pressed=${this.view === 'list'}
          aria-label="Vista lista"
          title="Lista"
          @click=${() => this.changeView('list')}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
            stroke-linecap="round"><path d="M3 6h18M3 12h18M3 18h18" /></svg>
        </button>
        <button
          type="button"
          class="view-btn"
          aria-pressed=${this.view === 'grid'}
          aria-label="Vista cuadrícula"
          title="Cuadrícula"
          @click=${() => this.changeView('grid')}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="3" y="3" width="7" height="7" /><rect x="14" y="3" width="7" height="7" />
            <rect x="3" y="14" width="7" height="7" /><rect x="14" y="14" width="7" height="7" />
          </svg>
        </button>
      </div>

      <button
        type="button"
        class="tbtn icon"
        aria-label=${this.t.newFolder}
        title=${this.t.newFolder}
        @click=${() => this.createFolder()}
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
          stroke-linecap="round" stroke-linejoin="round">
          <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
          <path d="M12 11v6M9 14h6" />
        </svg>
      </button>

      ${this.uploadable
        ? html`<button
            type="button"
            class="tbtn primary icon"
            aria-label=${this.t.upload}
            title=${this.t.upload}
            @click=${() => this.openPicker()}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
              stroke-linecap="round" stroke-linejoin="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="17 8 12 3 7 8" /><line x1="12" y1="3" x2="12" y2="15" />
            </svg>
          </button>`
        : ''}
    </div>`;
  }

  // SVG reutilizables de las acciones de fila.
  private get iconOpen() {
    return html`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
      stroke-linecap="round" stroke-linejoin="round">
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" /><circle cx="12" cy="12" r="3" />
    </svg>`;
  }
  private get iconDownload() {
    return html`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
      stroke-linecap="round" stroke-linejoin="round">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <polyline points="7 10 12 15 17 10" /><line x1="12" y1="15" x2="12" y2="3" />
    </svg>`;
  }
  private get iconDelete() {
    return html`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
      stroke-linecap="round" stroke-linejoin="round">
      <path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
    </svg>`;
  }

  // Acciones de un archivo (abrir/descargar/eliminar), reutilizadas en grid y lista.
  private fileActions(file: OkFmFile): unknown {
    return html`<button
        type="button"
        class="action"
        aria-label=${this.t.open}
        title=${this.t.open}
        @click=${(e: Event) => {
          e.stopPropagation();
          this.open(file.id);
        }}
      >
        ${this.iconOpen}
      </button>
      <button
        type="button"
        class="action"
        aria-label=${this.t.download}
        title=${this.t.download}
        @click=${(e: Event) => {
          e.stopPropagation();
          this.download(file);
        }}
      >
        ${this.iconDownload}
      </button>
      <button
        type="button"
        class="action danger"
        aria-label=${this.t.delete}
        title=${this.t.delete}
        @click=${(e: Event) => {
          e.stopPropagation();
          this.deleteFile(file.id);
        }}
      >
        ${this.iconDelete}
      </button>`;
  }

  // ---- Render del contenido (grid/lista/vacío/loading) ----
  private renderContent(): unknown {
    if (this.loading) {
      return html`<div class="skeleton">
        ${[0, 1, 2, 3, 4].map(() => html`<div class="sk-row"></div>`)}
      </div>`;
    }
    if (!this.files.length) {
      return html`<div class="empty">
        <ion-icon name="folder-open-outline"></ion-icon>
        <span>${this.t.empty}</span>
      </div>`;
    }
    return this.view === 'grid' ? this.renderGrid() : this.renderList();
  }

  private renderGrid(): unknown {
    return html`<div class="grid">
      ${this.files.map(
        (file) => html`<article
          class="card"
          tabindex="0"
          @dblclick=${() => this.open(file.id)}
          @keydown=${(e: KeyboardEvent) => {
            if (e.key === 'Enter') this.open(file.id);
          }}
        >
          <div class="card-actions">${this.fileActions(file)}</div>
          ${this.renderBadge(file)}
          <div class="card-name" title=${file.name}>${file.name}</div>
          <div class="card-meta">
            ${[file.sizeLabel, file.modified].filter(Boolean).join(' · ')}
          </div>
        </article>`
      )}
    </div>`;
  }

  private renderList(): unknown {
    return html`<div class="list" role="list">
      ${this.files.map(
        (file) => html`<div
          class="lrow"
          role="listitem"
          tabindex="0"
          @dblclick=${() => this.open(file.id)}
          @keydown=${(e: KeyboardEvent) => {
            if (e.key === 'Enter') this.open(file.id);
          }}
        >
          ${this.renderBadge(file)}
          <span class="lname" title=${file.name}>${file.name}</span>
          <span class="lsize">${file.sizeLabel ?? ''}</span>
          <span class="lmod">${file.modified ?? ''}</span>
          <div class="lactions">${this.fileActions(file)}</div>
        </div>`
      )}
    </div>`;
  }

  render(): unknown {
    // Siembra perezosa de la expansión a partir de los datos.
    if (!this.seeded && this.folders.length) {
      this.seedExpanded(this.folders);
      this.seeded = true;
    }

    const flat = this.flatFolders(this.folders);

    return html`<div class="wrap">
      <aside class="panel aside">
        <!-- Árbol (desktop) -->
        <div class="tree-host">
          <div class="eyebrow">${this.t.folders}</div>
          <ul role="tree" aria-label=${this.t.folders}>
            ${this.folders.map((f) => this.renderFolder(f))}
          </ul>
        </div>

        <!-- Selector de carpeta (móvil) -->
        <div class="folder-select">
          <div class="eyebrow">${this.t.folders}</div>
          <select
            aria-label=${this.t.folders}
            @change=${(e: Event) => this.navigate((e.target as HTMLSelectElement).value)}
          >
            ${flat.map(
              ({ f, d }) => html`<option value=${f.id} ?selected=${f.id === this.selected}>
                ${'  '.repeat(d)}${f.label}${f.count != null ? ` (${f.count})` : ''}
              </option>`
            )}
          </select>
        </div>

        ${this.renderQuota()}
      </aside>

      <section
        class=${`panel main ${this.dragging ? 'dragging' : ''}`.trim()}
        @dragover=${this.onDragOver}
        @dragleave=${this.onDragLeave}
        @drop=${this.onDrop}
      >
        ${this.renderToolbar()} ${this.renderContent()}
      </section>
    </div>

    <input type="file" multiple @change=${this.onPicked} />`;
  }
}

define('ok-file-manager', OkFileManager);

declare global {
  interface HTMLElementTagNameMap {
    'ok-file-manager': OkFileManager;
  }
}
