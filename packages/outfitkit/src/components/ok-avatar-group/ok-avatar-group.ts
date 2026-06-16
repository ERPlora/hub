import { LitElement, html, css } from 'lit';
import { property } from 'lit/decorators.js';
import { define } from '../../base/define.js';

/** Tonos de color para un avatar (afecta solo al fondo cuando no hay imagen). */
export type OkAvatarTone = 'neutral' | 'brand' | 'success' | 'warning' | 'danger' | 'info';

/** Tamaños del stack (espejo del ux-avatar original). */
export type OkAvatarGroupSize = 'xs' | 'sm' | 'md' | 'lg';

/** Descriptor declarativo de un avatar dentro del grupo. */
export interface OkAvatarItem {
  /** URL de imagen; si falta se muestran las iniciales. */
  src?: string;
  /** Iniciales (1-3 chars) cuando no hay imagen. */
  initials?: string;
  /** Tono de fondo cuando se pintan iniciales. */
  tone?: OkAvatarTone;
  /** Texto accesible (title/alt). Por defecto las iniciales. */
  label?: string;
}

// ok-avatar-group — pila de avatares solapados (stack) presentacional.
// Cada avatar no-primero lleva margen-izq negativo y un ring de 2px del color
// del fondo (box-shadow), y un último globo "+N" cuando se excede `max`.
export class OkAvatarGroup extends LitElement {
  static styles = css`
    :host {
      display: inline-flex;
      width: auto;
      /* Tokens propios estilo Ionic (overridables): --ok-* → --ion-* → hex. */
      --size: 28px;
      --font-size: 11px;
      --overlap: 8px;

      --avatar-bg: var(--ok-color-step-150, var(--ion-color-step-150, #e9edf1));
      --avatar-fg: var(--ok-color-step-650, var(--ion-color-step-650, #4a5560));
      --avatar-line: var(--ok-border-color, var(--ion-border-color, #d7dde3));
      /* El ring usa el color de fondo del contenedor para "recortar" el solape. */
      --ring-color: var(--ok-background-color, var(--ion-background-color, #ffffff));

      --brand-bg: var(--ok-color-primary, var(--ion-color-primary, #3880ff));
      --brand-fg: var(--ok-color-primary-contrast, var(--ion-color-primary-contrast, #fff));
      --success-bg: var(--ok-color-success, var(--ion-color-success, #2dd36f));
      --success-fg: var(--ok-color-success-contrast, var(--ion-color-success-contrast, #fff));
      --warning-bg: var(--ok-color-warning, var(--ion-color-warning, #ffc409));
      --warning-fg: var(--ok-color-warning-contrast, var(--ion-color-warning-contrast, #000));
      --danger-bg: var(--ok-color-danger, var(--ion-color-danger, #eb445a));
      --danger-fg: var(--ok-color-danger-contrast, var(--ion-color-danger-contrast, #fff));
      --info-bg: var(--ok-color-tertiary, var(--ion-color-tertiary, #5260ff));
      --info-fg: var(--ok-color-tertiary-contrast, var(--ion-color-tertiary-contrast, #fff));
    }

    .stack {
      display: inline-flex;
      align-items: center;
    }

    .avatar {
      box-sizing: border-box;
      display: inline-grid;
      place-items: center;
      width: var(--size);
      height: var(--size);
      border-radius: 50%;
      background: var(--avatar-bg);
      color: var(--avatar-fg);
      font-size: var(--font-size);
      font-weight: 600;
      line-height: 1;
      letter-spacing: -0.02em;
      overflow: hidden;
      flex-shrink: 0;
      border: 1px solid var(--avatar-line);
      user-select: none;
    }

    .avatar:not(:first-child) {
      margin-left: calc(-1 * var(--overlap));
      /* Ring del color de fondo para separar visualmente los solapes. */
      box-shadow: 0 0 0 2px var(--ring-color);
    }

    .avatar img {
      width: 100%;
      height: 100%;
      object-fit: cover;
      display: block;
    }

    /* Tonos (solo aplican cuando se pintan iniciales). */
    .avatar.tone-brand { background: var(--brand-bg); color: var(--brand-fg); border-color: transparent; }
    .avatar.tone-success { background: var(--success-bg); color: var(--success-fg); border-color: transparent; }
    .avatar.tone-warning { background: var(--warning-bg); color: var(--warning-fg); border-color: transparent; }
    .avatar.tone-danger { background: var(--danger-bg); color: var(--danger-fg); border-color: transparent; }
    .avatar.tone-info { background: var(--info-bg); color: var(--info-fg); border-color: transparent; }

    /* Globo de overflow "+N": reusa el look de avatar con fondo neutro. */
    .more {
      font-variant-numeric: tabular-nums;
      cursor: default;
    }
  `;

  /** Lista declarativa de avatares. */
  @property({ attribute: false }) avatars: OkAvatarItem[] = [];

  /** Máximo de avatares visibles antes de colapsar en "+N". 0 = sin límite. */
  @property({ type: Number }) max = 0;

  /** Tamaño del stack. */
  @property({ reflect: true }) size: OkAvatarGroupSize = 'md';

  /** Solape en px entre avatares (margen-izq negativo). Por defecto según tamaño. */
  @property({ type: Number }) overlap?: number;

  /** Métricas por tamaño: [diámetro, font-size, solape por defecto]. */
  private static readonly SIZES: Record<OkAvatarGroupSize, [number, number, number]> = {
    xs: [20, 9, 6],
    sm: [24, 10, 7],
    md: [28, 11, 8],
    lg: [36, 13, 10],
  };

  /** Devuelve las iniciales normalizadas (máx 3 chars, mayúsculas). */
  private initialsOf(item: OkAvatarItem): string {
    return (item.initials ?? '').trim().slice(0, 3).toUpperCase();
  }

  private renderAvatar(item: OkAvatarItem) {
    const label = item.label ?? item.initials ?? '';
    const toneClass = item.tone && item.tone !== 'neutral' ? `tone-${item.tone}` : '';
    return html`
      <span class="avatar ${toneClass}" role="img" aria-label=${label || 'avatar'} title=${label}>
        ${item.src
          ? html`<img src=${item.src} alt=${label} loading="lazy" />`
          : this.initialsOf(item)}
      </span>
    `;
  }

  render(): unknown {
    const [dim, font, defOverlap] = OkAvatarGroup.SIZES[this.size] ?? OkAvatarGroup.SIZES.md;
    const overlap = this.overlap ?? defOverlap;

    // Estilo inline solo para las medidas dinámicas (tokens del :host).
    const vars =
      `--size:${dim}px;--font-size:${font}px;--overlap:${overlap}px`;

    const list = Array.isArray(this.avatars) ? this.avatars : [];
    const limit = this.max > 0 ? this.max : list.length;
    const visible = list.slice(0, limit);
    const hidden = list.length - visible.length;

    return html`
      <div class="stack" style=${vars} role="group" aria-label="Grupo de avatares">
        ${visible.map((a) => this.renderAvatar(a))}
        ${hidden > 0
          ? html`<span
              class="avatar more"
              role="img"
              aria-label=${`${hidden} más`}
              title=${`${hidden} más`}
              >+${hidden}</span
            >`
          : null}
      </div>
    `;
  }
}

define('ok-avatar-group', OkAvatarGroup);

declare global {
  interface HTMLElementTagNameMap {
    'ok-avatar-group': OkAvatarGroup;
  }
}
