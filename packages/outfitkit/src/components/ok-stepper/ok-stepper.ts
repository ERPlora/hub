import { LitElement, html, css } from 'lit';
import { property } from 'lit/decorators.js';
import { define } from '../../base/define.js';

/** Un paso del stepper/wizard. */
export interface OkStep {
  /** Etiqueta corta del paso. */
  label: string;
  /** Descripción opcional bajo la etiqueta (solo desktop). */
  description?: string;
}

// Textos humanos del stepper (i18n). Default INGLÉS; el consumidor sobreescribe vía `labels`.
export interface OkStepperLabels {
  /** Resumen compacto (móvil); `{n}` = paso actual (1-based), `{total}` = total de pasos. */
  stepCount: string;
}

const DEFAULT_LABELS: OkStepperLabels = {
  stepCount: 'Step {n} of {total}',
};

// ok-stepper — indicador de pasos (no envuelve un ion-* contenedor: es CSS propio autocontenido).
// Muestra círculos numerados conectados por una línea. En desktop es horizontal; en móvil colapsa a
// "Paso X de N · label". Estados por índice respecto a `current`:
//   < current  → completado (check, color primary)
//   == current → activo (primary, resaltado)
//   > current  → pendiente (muted)
// Emite `ok-step-select` (detail { index }, bubbles+composed) al pulsar un paso, permitiendo que el
// consumidor (p. ej. ok-wizard) decida si navega o no.
export class OkStepper extends LitElement {
  static styles = css`
    /* Theming en dos capas: cadena --ok-* → --ion-* → hex (sin variables privadas). */
    :host {
      display: block;
      width: 100%;
      max-width: 100%;
      box-sizing: border-box;
      /* Colores derivados del tema, overridable por componente al estilo Ionic. */
      --color-primary: var(--ok-color-primary, var(--ion-color-primary, #3880ff));
      --color-on-primary: var(--ok-color-primary-contrast, var(--ion-color-primary-contrast, #fff));
      --color-muted: var(--ok-color-medium, var(--ion-color-medium, #92949c));
      --color-line: var(--ok-border-color, var(--ion-border-color, #e0e0e0));
      --color-text: var(--ok-text-color, var(--ion-text-color, #1f2937));
      --circle-size: 2rem;
      font-family: var(--ok-font-family, var(--ion-font-family, inherit));
    }

    /* ---------- Vista desktop (horizontal) ---------- */
    .steps {
      display: flex;
      align-items: flex-start;
      width: 100%;
      list-style: none;
      margin: 0;
      padding: 0;
    }

    .step {
      display: flex;
      flex-direction: column;
      align-items: center;
      flex: 1 1 0;
      min-width: 0;
      position: relative;
      text-align: center;
    }

    /* Botón clicable (todo el bloque círculo+texto). CSP-safe: sin handlers inline. */
    .step-btn {
      appearance: none;
      background: transparent;
      border: 0;
      padding: 0;
      margin: 0;
      width: 100%;
      cursor: pointer;
      color: inherit;
      font: inherit;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 0.375rem;
      transition: background-color var(--ok-transition, 150ms ease),
        color var(--ok-transition, 150ms ease), border-color var(--ok-transition, 150ms ease),
        box-shadow var(--ok-transition, 150ms ease), transform 120ms ease;
    }
    .step-btn:focus-visible {
      outline: 2px solid var(--color-primary);
      outline-offset: 2px;
      border-radius: 0.5rem;
    }
    /* Hover sutil solo con ratón: el círculo se acerca al primary. */
    @media (hover: hover) {
      .step-btn:hover .circle {
        border-color: var(--color-primary);
        color: var(--color-primary);
      }
    }
    .step-btn:active {
      transform: scale(var(--ok-press-scale, 0.97));
    }
    @media (prefers-reduced-motion: reduce) {
      .step-btn:active {
        transform: none;
      }
    }

    /* La línea conectora se dibuja a la izquierda de cada círculo (excepto el primero). */
    .step:not(:first-child) .circle-row::before {
      content: '';
      position: absolute;
      top: calc(var(--circle-size) / 2);
      right: 50%;
      left: -50%;
      height: 2px;
      background: var(--color-line);
      z-index: 0;
    }
    /* Si el paso es <= current, la línea entrante se pinta como completada. */
    .step.completed .circle-row::before,
    .step.active .circle-row::before {
      background: var(--color-primary);
    }

    .circle-row {
      position: relative;
      display: flex;
      justify-content: center;
      width: 100%;
    }

    .circle {
      position: relative;
      z-index: 1;
      width: var(--circle-size);
      height: var(--circle-size);
      border-radius: 50%;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      font-size: 0.875rem;
      font-weight: 600;
      border: 2px solid var(--color-line);
      background: var(--ok-background, var(--ion-background-color, #fff));
      color: var(--color-muted);
      transition: background 0.15s ease, border-color 0.15s ease, color 0.15s ease;
    }

    /* Pendiente: muted (por defecto). Completado: relleno primary con check. */
    .step.completed .circle {
      background: var(--color-primary);
      border-color: var(--color-primary);
      color: var(--color-on-primary);
    }
    /* Activo: resaltado con anillo. */
    .step.active .circle {
      border-color: var(--color-primary);
      color: var(--color-primary);
      box-shadow: 0 0 0 4px color-mix(in srgb, var(--color-primary) 18%, transparent);
    }

    .circle ion-icon {
      font-size: 1.125rem;
    }

    .labels {
      display: flex;
      flex-direction: column;
      gap: 0.125rem;
      padding: 0 0.25rem;
    }
    .label {
      font-size: 0.8125rem;
      font-weight: 500;
      color: var(--color-muted);
      line-height: 1.25;
      overflow-wrap: anywhere;
    }
    .step.active .label {
      color: var(--color-text);
      font-weight: 600;
    }
    .step.completed .label {
      color: var(--color-text);
    }
    .description {
      font-size: 0.75rem;
      color: var(--color-muted);
      line-height: 1.2;
    }

    /* ---------- Vista móvil (compacta) ---------- */
    .compact {
      display: none;
      align-items: center;
      gap: 0.625rem;
      width: 100%;
    }
    .compact .circle {
      flex: 0 0 auto;
    }
    .compact-text {
      display: flex;
      flex-direction: column;
      min-width: 0;
    }
    .compact-count {
      font-size: 0.75rem;
      color: var(--color-muted);
      font-weight: 500;
    }
    .compact-label {
      font-size: 0.9375rem;
      font-weight: 600;
      color: var(--color-text);
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    /* Breakpoint: por debajo de 640px colapsamos a la vista compacta. */
    @media (max-width: 640px) {
      .steps {
        display: none;
      }
      .compact {
        display: flex;
      }
    }
  `;

  /** Lista de pasos a mostrar. */
  @property({ attribute: false }) steps: OkStep[] = [];
  /** Índice (0-based) del paso activo. */
  @property({ type: Number }) current = 0;
  /** Textos humanos sobreescribibles (i18n). Default INGLÉS. */
  @property({ attribute: false }) labels: Partial<OkStepperLabels> = {};

  /** Textos efectivos: defaults INGLÉS mezclados con los del consumidor. */
  private get t(): OkStepperLabels {
    return { ...DEFAULT_LABELS, ...this.labels };
  }

  /** Emite ok-step-select al pulsar un paso. */
  private _select(index: number): void {
    this.dispatchEvent(
      new CustomEvent('ok-step-select', {
        detail: { index },
        bubbles: true,
        composed: true,
      }),
    );
  }

  /** Estado de un paso respecto al actual. */
  private _stateClass(i: number): string {
    if (i < this.current) return 'completed';
    if (i === this.current) return 'active';
    return 'pending';
  }

  render(): unknown {
    const total = this.steps.length;
    const cur = this.steps[this.current];

    return html`
      <!-- Desktop: pasos horizontales conectados -->
      <ol class="steps" role="list">
        ${this.steps.map((step, i) => {
          const state = this._stateClass(i);
          return html`<li class="step ${state}">
            <button
              type="button"
              class="step-btn"
              aria-current=${i === this.current ? 'step' : 'false'}
              @click=${() => this._select(i)}
            >
              <span class="circle-row">
                <span class="circle">
                  ${i < this.current
                    ? html`<ion-icon name="checkmark-outline" aria-hidden="true"></ion-icon>`
                    : html`${i + 1}`}
                </span>
              </span>
              <span class="labels">
                <span class="label">${step.label}</span>
                ${step.description
                  ? html`<span class="description">${step.description}</span>`
                  : ''}
              </span>
            </button>
          </li>`;
        })}
      </ol>

      <!-- Móvil: resumen compacto "Paso X de N · label" -->
      <div class="compact">
        <span class="circle">${this.current + 1}</span>
        <span class="compact-text">
          <span class="compact-count"
            >${this.t.stepCount
              .replace('{n}', String(this.current + 1))
              .replace('{total}', String(total))}</span
          >
          <span class="compact-label">${cur ? cur.label : ''}</span>
        </span>
      </div>
    `;
  }
}

define('ok-stepper', OkStepper);

declare global {
  interface HTMLElementTagNameMap {
    'ok-stepper': OkStepper;
  }
}
