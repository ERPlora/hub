import { LitElement, html, css } from 'lit';
import { property } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// ok-select-card — fila/tarjeta seleccionable con borde que envuelve un checkbox/radio nativo
// de Ionic. Toda la fila es zona de click. Cuando está marcada ([data-checked]) la tarjeta pinta
// borde de marca + fondo brand-soft. Porta el patrón `.ux-check-row` de la lib CSS antigua.
//
// Diseño: borde 1px line, radius-md, padding, hover bg-3; marcado → brand-soft + borde brand.
// Modo radio: agrupa por `name`; al marcar uno se desmarcan los hermanos del mismo grupo.
// Evento: ok-change { checked, value }.

export interface OkSelectCardChangeDetail {
  /** Si la tarjeta queda marcada tras el cambio. */
  checked: boolean;
  /** Valor asociado a la tarjeta. */
  value: string;
}

export class OkSelectCard extends LitElement {
  static styles = css`
    :host {
      display: block;
      width: 100%;
      /* Tokens propios estilo Ionic (overridables): --ok-* → --ion-* → hex. */
      --bg: var(--ok-surface, var(--ion-background-color, #ffffff));
      --bg-hover: var(--ok-surface-hover, var(--ion-color-step-50, #f2f3f5));
      --border-color: var(--ok-border-color, var(--ion-border-color, #d7d8da));
      --radius: var(--ok-radius-md, 12px);
      --text-color: var(--ok-text-color, var(--ion-text-color, #1f2933));
      --muted-color: var(--ok-color-medium, var(--ion-color-medium, #92949c));
      --brand: var(--ok-color-primary, var(--ion-color-primary, #3880ff));
      /* Fondo suave de marca: si no hay token, se deriva del brand con transparencia. */
      --brand-soft: var(--ok-color-primary-soft, var(--ion-color-primary-tint, rgba(56, 128, 255, 0.1)));
      --gap: 0.75rem;
      --pad: 0.875rem;
    }

    :host([disabled]) {
      opacity: 0.5;
      pointer-events: none;
    }

    .card {
      display: flex;
      align-items: flex-start;
      gap: var(--gap);
      width: 100%;
      box-sizing: border-box;
      padding: var(--pad);
      border: 1px solid var(--border-color);
      border-radius: var(--radius);
      background: var(--bg);
      cursor: pointer;
      transition:
        background 0.16s ease,
        border-color 0.16s ease,
        box-shadow 0.16s ease;
      /* Sin selección de texto accidental al clicar la fila. */
      user-select: none;
      -webkit-tap-highlight-color: transparent;
    }

    .card:hover {
      background: var(--bg-hover);
    }

    /* Estado marcado: borde + fondo de marca. */
    .card[data-checked] {
      background: var(--brand-soft);
      border-color: var(--brand);
    }

    /* Foco accesible visible sobre toda la fila. */
    .card:focus-visible {
      outline: none;
      box-shadow: 0 0 0 2px var(--bg), 0 0 0 4px var(--brand);
    }

    .control {
      flex-shrink: 0;
      /* Alinear el control con la primera línea del label. */
      margin-top: 0.0625rem;
      pointer-events: none; /* el click lo gobierna la fila */
    }

    .icon {
      flex-shrink: 0;
      display: inline-grid;
      place-items: center;
      width: 1.5rem;
      height: 1.5rem;
      color: var(--muted-color);
    }

    .card[data-checked] .icon {
      color: var(--brand);
    }

    ion-icon {
      font-size: 1.375rem;
    }

    .body {
      flex: 1;
      min-width: 0;
      display: flex;
      flex-direction: column;
      gap: 0.125rem;
    }

    .label {
      margin: 0;
      font-size: 0.9375rem;
      font-weight: 600;
      line-height: 1.3;
      color: var(--text-color);
    }

    .description {
      margin: 0;
      font-size: 0.8125rem;
      line-height: 1.4;
      color: var(--muted-color);
    }
  `;

  /** Tipo de control: 'checkbox' (independiente) o 'radio' (exclusivo por grupo). */
  @property() mode: 'checkbox' | 'radio' = 'checkbox';

  /** Nombre del grupo de radios (necesario para exclusión mutua en modo radio). */
  @property() name?: string;

  /** Valor asociado a la tarjeta (se emite en ok-change). */
  @property() value = '';

  /** Si la tarjeta está marcada. */
  @property({ type: Boolean, reflect: true }) checked = false;

  /** Deshabilita la interacción. */
  @property({ type: Boolean, reflect: true }) disabled = false;

  /** Título principal de la tarjeta. */
  @property() label?: string;

  /** Texto secundario opcional (muted) bajo el label. */
  @property() description?: string;

  /** Nombre de icono Iconify/Ionicons opcional a la izquierda. */
  @property() icon?: string;

  private onToggle(): void {
    if (this.disabled) return;

    if (this.mode === 'radio') {
      // En radio ya marcado no se desmarca a sí mismo (comportamiento estándar de radios).
      if (this.checked) return;
      this.checked = true;
      this.uncheckSiblings();
    } else {
      this.checked = !this.checked;
    }

    this.emitChange();
  }

  /** Desmarca el resto de ok-select-card del mismo name (grupo radio). */
  private uncheckSiblings(): void {
    if (!this.name) return;
    const root = (this.getRootNode() as Document | ShadowRoot) ?? document;
    const group = root.querySelectorAll<OkSelectCard>('ok-select-card');
    group.forEach((card) => {
      if (card !== this && card.mode === 'radio' && card.name === this.name && card.checked) {
        card.checked = false;
      }
    });
  }

  private emitChange(): void {
    const detail: OkSelectCardChangeDetail = { checked: this.checked, value: this.value };
    this.dispatchEvent(
      new CustomEvent<OkSelectCardChangeDetail>('ok-change', {
        detail,
        bubbles: true,
        composed: true,
      }),
    );
  }

  private onKeydown(e: KeyboardEvent): void {
    // Activación por teclado: Space en ambos modos; Enter también para usabilidad.
    if (e.key === ' ' || e.key === 'Enter') {
      e.preventDefault();
      this.onToggle();
    }
  }

  render(): unknown {
    const isRadio = this.mode === 'radio';
    const role = isRadio ? 'radio' : 'checkbox';

    // Se construye SOBRE Ionic: control nativo ion-checkbox / ion-radio (solo presentación,
    // el estado lo gobierna la fila; pointer-events:none en .control).
    const control = isRadio
      ? html`<ion-radio
          class="control"
          aria-hidden="true"
          ?disabled=${this.disabled}
          .value=${this.value}
        ></ion-radio>`
      : html`<ion-checkbox
          class="control"
          aria-hidden="true"
          ?checked=${this.checked}
          ?disabled=${this.disabled}
        ></ion-checkbox>`;

    return html`
      <div
        class="card"
        role=${role}
        tabindex=${this.disabled ? -1 : 0}
        aria-checked=${this.checked ? 'true' : 'false'}
        aria-disabled=${this.disabled ? 'true' : 'false'}
        aria-label=${this.label ?? this.value}
        ?data-checked=${this.checked}
        @click=${this.onToggle}
        @keydown=${this.onKeydown}
      >
        ${control}
        ${this.icon
          ? html`<span class="icon"><ion-icon name=${this.icon}></ion-icon></span>`
          : null}
        <div class="body">
          ${this.label ? html`<p class="label">${this.label}</p>` : null}
          ${this.description ? html`<p class="description">${this.description}</p>` : null}
          <slot></slot>
        </div>
      </div>
    `;
  }
}

define('ok-select-card', OkSelectCard);

declare global {
  interface HTMLElementTagNameMap {
    'ok-select-card': OkSelectCard;
  }
}
