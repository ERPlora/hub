import { LitElement, html, css } from 'lit';
import { property, state } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// ok-avatar — avatar de iniciales/imagen (el hueco que ion-avatar no cubre: ion-avatar es solo un
// contenedor redondo para <img>, sin iniciales, ni tamaños, ni color derivado). Inline.
//   • prop `name`    → nombre completo; deriva las iniciales (1ª letra de las dos primeras palabras)
//   • prop `email`   → fallback para iniciales y `title`
//   • prop `src`     → URL de imagen; si carga sustituye a las iniciales (fallback a iniciales en error)
//   • prop `size`    → 'xs' | 'sm' | 'md' | 'lg' (def 'md', ~32px) — o `--ok-avatar-size` libre
//   • prop `shape`   → 'circle' | 'rounded' (def 'circle')
//   • prop `tone`    → 'primary' | 'auto' (def 'primary'); auto = color estable por hash del nombre
//   • prop `status`  → 'online' | 'offline' | 'busy' — punto de estado opcional
//   • prop `href`    → lo envuelve en <a> (p.ej. topbar → perfil)
// Slot default → override del contenido (p.ej. un icono). Sin eventos propios (click nativo / <a>).
// Theming: cadena estándar --ok-* → --ion-* → hex (`--ok-avatar-bg` def color-mix primary 18%,
// `--ok-avatar-color` def primary).
export type OkAvatarSize = 'xs' | 'sm' | 'md' | 'lg';
export type OkAvatarShape = 'circle' | 'rounded';
export type OkAvatarTone = 'primary' | 'auto';
export type OkAvatarStatus = 'online' | 'offline' | 'busy';

export class OkAvatar extends LitElement {
  static styles = css`
    :host {
      /* Vars overridable (estilo Ionic), default = cadena --ok-* → --ion-* → hex.
         --tone-color se reasigna por JS (CSSOM) cuando tone='auto'. */
      --tone-color: var(--ok-primary, var(--ion-color-primary, #3880ff));
      --background: var(--ok-avatar-bg, color-mix(in srgb, var(--tone-color) 18%, transparent));
      --color: var(--ok-avatar-color, var(--tone-color));
      --size: var(--ok-avatar-size, 32px);
      --border-radius: 50%;
      --font: var(--ok-font, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif);

      /* Inline: el avatar es un elemento de línea (topbar, celdas de tabla, listados). */
      display: inline-flex;
      vertical-align: middle;
      font-family: var(--font);
      box-sizing: border-box;
    }

    /* Tamaños predefinidos (--ok-avatar-size libre los sobrescribe). */
    :host([size='xs']) { --size: var(--ok-avatar-size, 20px); }
    :host([size='sm']) { --size: var(--ok-avatar-size, 24px); }
    :host([size='md']) { --size: var(--ok-avatar-size, 32px); }
    :host([size='lg']) { --size: var(--ok-avatar-size, 44px); }

    :host([shape='rounded']) {
      --border-radius: var(--ok-radius, var(--ion-border-radius, 8px));
    }

    .wrap {
      position: relative;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: var(--size);
      height: var(--size);
      border-radius: var(--border-radius);
      background: var(--background);
      color: var(--color);
      font-size: calc(var(--size) * 0.4);
      font-weight: 600;
      letter-spacing: 0.02em;
      line-height: 1;
      text-decoration: none;
      user-select: none;
      overflow: visible; /* el punto de estado sobresale; la imagen recorta por su propio radius */
    }
    a.wrap { cursor: pointer; }
    a.wrap:focus-visible {
      outline: 2px solid var(--tone-color);
      outline-offset: 2px;
    }

    .initials {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 100%;
      height: 100%;
      border-radius: inherit;
      overflow: hidden;
    }

    img {
      display: block;
      width: 100%;
      height: 100%;
      border-radius: inherit;
      object-fit: cover;
    }

    /* Punto de estado (abajo-derecha), con anillo del color de la superficie. */
    .status {
      position: absolute;
      right: 0;
      bottom: 0;
      width: calc(var(--size) * 0.28);
      height: calc(var(--size) * 0.28);
      border-radius: 50%;
      box-shadow: 0 0 0 2px var(--ok-surface, var(--ion-background-color, #fff));
      background: var(--ok-medium, var(--ion-color-medium, #5f5f5f));
    }
    :host([status='online']) .status { background: var(--ok-success, var(--ion-color-success, #2dd55b)); }
    :host([status='busy'])   .status { background: var(--ok-danger, var(--ion-color-danger, #c5000f)); }
    /* offline → medium (default ya aplicado arriba). */
  `;

  /** Nombre completo; deriva las iniciales (1ª letra de las dos primeras palabras). */
  @property({ type: String }) name = '';
  /** Email: fallback para las iniciales y para el title. */
  @property({ type: String }) email?: string;
  /** URL de imagen; si carga sustituye a las iniciales (vuelve a iniciales si falla). */
  @property({ type: String }) src?: string;
  /** Tamaño predefinido (o usa --ok-avatar-size para tamaño libre). */
  @property({ type: String, reflect: true }) size: OkAvatarSize = 'md';
  /** Forma: círculo o esquinas redondeadas. */
  @property({ type: String, reflect: true }) shape: OkAvatarShape = 'circle';
  /** Color: primary fijo o derivado estable por hash del nombre (útil en listados). */
  @property({ type: String, reflect: true }) tone: OkAvatarTone = 'primary';
  /** Punto de estado opcional. */
  @property({ type: String, reflect: true }) status?: OkAvatarStatus;
  /** Si se indica, el avatar se envuelve en un <a href>. */
  @property({ type: String }) href?: string;

  /** La imagen falló al cargar → se vuelve a las iniciales. */
  @state() private imgFailed = false;

  // Iniciales: 1ª letra de las dos primeras palabras del nombre; fallback 1ª letra del email.
  private initials(): string {
    const words = (this.name ?? '').trim().split(/\s+/).filter(Boolean);
    if (words.length >= 2) return (words[0][0] + words[1][0]).toUpperCase();
    if (words.length === 1) return words[0][0].toUpperCase();
    const mail = (this.email ?? '').trim();
    return mail ? mail[0].toUpperCase() : '?';
  }

  // Hash estable (djb2) → tono HSL determinista por nombre/email (para tone='auto').
  private autoHue(): number {
    const key = (this.name || this.email || '').trim().toLowerCase();
    let h = 5381;
    for (let i = 0; i < key.length; i++) h = ((h << 5) + h + key.charCodeAt(i)) | 0;
    return Math.abs(h) % 360;
  }

  protected override willUpdate(changed: Map<PropertyKey, unknown>): void {
    // Reintenta la imagen si cambia el src.
    if (changed.has('src')) this.imgFailed = false;
    // tone='auto': color estable derivado por hash (vía CSSOM — CSP-safe, sin atributo style).
    if (changed.has('tone') || changed.has('name') || changed.has('email')) {
      if (this.tone === 'auto') {
        this.style.setProperty('--tone-color', `hsl(${this.autoHue()} 55% 42%)`);
      } else {
        this.style.removeProperty('--tone-color');
      }
    }
  }

  private onImgError = (): void => {
    this.imgFailed = true;
  };

  render(): unknown {
    const label = this.name || this.email || '';
    const showImg = !!this.src && !this.imgFailed;
    // Slot default = override del contenido (p.ej. un icono); fallback = imagen o iniciales.
    const content = html`
      <slot>
        ${showImg
          ? html`<img src=${this.src!} alt=${label} @error=${this.onImgError} />`
          : html`<span class="initials" aria-hidden="true">${this.initials()}</span>`}
      </slot>
      ${this.status ? html`<span class="status" part="status"></span>` : null}
    `;
    return this.href
      ? html`<a class="wrap" part="avatar" href=${this.href} title=${label} aria-label=${label}>${content}</a>`
      : html`<span class="wrap" part="avatar" role="img" title=${label} aria-label=${label}>${content}</span>`;
  }
}

define('ok-avatar', OkAvatar);

declare global {
  interface HTMLElementTagNameMap {
    'ok-avatar': OkAvatar;
  }
}
