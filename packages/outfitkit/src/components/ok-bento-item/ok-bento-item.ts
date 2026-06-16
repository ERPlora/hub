import { LitElement, html, css } from 'lit';
import { property } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// ok-bento-item — celda de una <ok-bento>. Ocupa `cols`×`rows` de la rejilla. Panel con
// superficie, borde y radio; opcionalmente "glass" (cristal esmerilado, acento 2026),
// tinte de color (`tone`) y elevación al hover (`interactive`). Encabezado opcional
// (eyebrow/heading/icon) + slot default para el contenido. En móvil ocupa el ancho total.
//
//   <ok-bento-item cols="4" rows="2" glass icon="lucide:zap" heading="Bridge"> … </ok-bento-item>
type Tone = 'default' | 'primary' | 'success' | 'warning' | 'danger';

export class OkBentoItem extends LitElement {
  static styles = css`
    :host {
      display: block;
      grid-column: span var(--cols, 2);
      grid-row: span var(--rows, 1);
      min-width: 0;
      --color: var(--ok-text, var(--ion-text-color, #18181b));
      --muted: var(--ok-muted, rgba(var(--ion-text-color-rgb, 24, 24, 27), 0.6));
      --surface: var(--ok-surface, var(--ion-card-background, var(--ion-background-color, #fff)));
      --border: var(--ok-border, rgba(var(--ion-text-color-rgb, 24, 24, 27), 0.1));
      --radius: var(--ok-radius, 16px);
      --accent: var(--ion-color-primary, #1496d6);
      font-family: var(--ok-font, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif);
    }
    @media (max-width: 560px) {
      :host { grid-column: 1 / -1; grid-row: auto; }
    }
    .cell {
      box-sizing: border-box;
      height: 100%;
      display: flex;
      flex-direction: column;
      gap: 0.6rem;
      padding: var(--pad, clamp(1.1rem, 2vw, 1.6rem));
      color: var(--color);
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      overflow: hidden;
      position: relative;
      transition: transform var(--ok-transition, 160ms ease), box-shadow var(--ok-transition, 160ms ease),
        border-color var(--ok-transition, 160ms ease);
    }
    /* Tinte de acento por tono */
    :host([tone='primary']) { --accent: var(--ion-color-primary, #1496d6); }
    :host([tone='success']) { --accent: var(--ion-color-success, #2dd36f); }
    :host([tone='warning']) { --accent: var(--ion-color-warning, #ffc409); }
    :host([tone='danger']) { --accent: var(--ion-color-danger, #eb445a); }
    :host([tone]:not([tone='default'])) .cell {
      background: color-mix(in oklab, var(--accent) 7%, var(--surface));
      border-color: color-mix(in oklab, var(--accent) 22%, var(--border));
    }
    /* Cristal esmerilado (acento, no toda la UI) */
    :host([glass]) .cell {
      background: color-mix(in oklab, var(--surface) 62%, transparent);
      -webkit-backdrop-filter: blur(14px) saturate(1.4);
      backdrop-filter: blur(14px) saturate(1.4);
      border-color: color-mix(in oklab, var(--color) 12%, transparent);
      box-shadow: inset 0 1px 0 color-mix(in oklab, #fff 14%, transparent);
    }
    :host([interactive]) .cell { cursor: pointer; }
    :host([interactive]) .cell:hover {
      transform: translateY(-3px);
      border-color: color-mix(in oklab, var(--accent) 45%, var(--border));
      box-shadow: 0 18px 40px -22px color-mix(in oklab, var(--accent) 60%, transparent);
    }
    a.cell { text-decoration: none; color: inherit; }
    .ico {
      display: inline-grid;
      place-items: center;
      width: 2.5rem;
      height: 2.5rem;
      border-radius: 12px;
      color: var(--accent);
      background: color-mix(in oklab, var(--accent) 14%, transparent);
      font-size: 1.25rem;
    }
    /* Glifo via máscara CSS sobre la SVG del API de Iconify (funciona en Shadow DOM). */
    .glyph {
      width: 1.35rem;
      height: 1.35rem;
      background-color: currentColor;
      -webkit-mask: var(--u) center / contain no-repeat;
      mask: var(--u) center / contain no-repeat;
    }
    .eyebrow {
      font-size: 0.7rem;
      font-weight: 600;
      letter-spacing: 0.05em;
      text-transform: uppercase;
      color: var(--muted);
    }
    .title {
      margin: 0;
      font-size: clamp(1.05rem, 0.95rem + 0.5vw, 1.35rem);
      font-weight: 620;
      letter-spacing: -0.015em;
      line-height: 1.2;
    }
    ::slotted(p) { margin: 0; color: var(--muted); line-height: 1.55; }
  `;

  /** Columnas que ocupa en la rejilla (def 2). */
  @property({ type: Number }) cols = 2;
  /** Filas que ocupa (def 1). */
  @property({ type: Number }) rows = 1;
  /** Tono de acento. */
  @property({ reflect: true }) tone: Tone = 'default';
  /** Cristal esmerilado. */
  @property({ type: Boolean, reflect: true }) glass = false;
  /** Eleva al hover (y cursor pointer / link si hay href). */
  @property({ type: Boolean, reflect: true }) interactive = false;
  /** Si se pasa, toda la celda es un enlace. */
  @property() href?: string;
  /** Icono (nombre iconify, p.ej. "lucide:zap"). Para otro icono usa slot="icon". */
  @property() icon?: string;
  /** Eyebrow opcional sobre el título. */
  @property() eyebrow?: string;
  /** Título opcional. */
  @property() heading?: string;

  updated(): void {
    this.style.setProperty('--cols', String(this.cols));
    this.style.setProperty('--rows', String(this.rows));
  }

  /** "lucide:box" → "https://api.iconify.design/lucide/box.svg". */
  private iconUrl(name: string): string {
    const i = name.indexOf(':');
    const prefix = i === -1 ? 'lucide' : name.slice(0, i);
    const icon = i === -1 ? name : name.slice(i + 1);
    return `https://api.iconify.design/${prefix}/${icon}.svg`;
  }

  private body(): unknown {
    return html`
      ${this.icon ? html`<span class="ico"><i class="glyph" style="--u:url('${this.iconUrl(this.icon)}')"></i></span>` : null}
      ${this.eyebrow ? html`<span class="eyebrow">${this.eyebrow}</span>` : null}
      ${this.heading ? html`<h3 class="title">${this.heading}</h3>` : null}
      <slot></slot>
    `;
  }

  render(): unknown {
    return this.href
      ? html`<a class="cell" href=${this.href}>${this.body()}</a>`
      : html`<div class="cell">${this.body()}</div>`;
  }
}

define('ok-bento-item', OkBentoItem);

declare global {
  interface HTMLElementTagNameMap {
    'ok-bento-item': OkBentoItem;
  }
}
