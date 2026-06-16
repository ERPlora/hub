import { LitElement, html, css } from 'lit';
import { property } from 'lit/decorators.js';
import { define } from '../../base/define.js';
import { OkStepper, type OkStep } from '../ok-stepper/ok-stepper.js';

// Re-exportamos el tipo de paso para que el consumidor no tenga que importar de dos sitios.
export type { OkStep } from '../ok-stepper/ok-stepper.js';

// ok-wizard — asistente multi-paso. Compone un ok-stepper arriba, el contenido del paso actual por
// slots nombrados (`step-0`, `step-1`, …) y una barra de navegación abajo (Atrás / Siguiente /
// Finalizar) con ok-button (ion-button por dentro).
// Eventos (bubbles+composed):
//   - ok-step-change { index } al cambiar de paso (Atrás/Siguiente o clic en el stepper).
//   - ok-finish              al pulsar Finalizar en el último paso.
export class OkWizard extends LitElement {
  static styles = css`
    /* Autocontenido; ancho máximo el del contenedor. */
    :host {
      display: block;
      width: 100%;
      max-width: 100%;
      box-sizing: border-box;
      font-family: var(--ok-font-family, var(--ion-font-family, inherit));
    }

    .stepper {
      margin-bottom: 1.5rem;
    }

    /* Contenedor del contenido del paso. Solo se muestra el slot del paso actual; el resto se
       oculta vía [hidden]. Min-height para que la barra de navegación no salte entre pasos. */
    .panels {
      min-height: 4rem;
    }
    .panel[hidden] {
      display: none;
    }

    /* Barra de navegación: Atrás a la izquierda, Siguiente/Finalizar a la derecha. */
    .nav {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 0.75rem;
      margin-top: 1.5rem;
      padding-top: 1rem;
      border-top: 1px solid var(--ok-border-color, var(--ion-border-color, #e0e0e0));
    }
    /* Cuando no hay botón Atrás, empujamos el de avance a la derecha. */
    .nav.no-back {
      justify-content: flex-end;
    }

    @media (max-width: 640px) {
      .stepper {
        margin-bottom: 1rem;
      }
    }
  `;

  /** Lista de pasos (misma forma que ok-stepper). */
  @property({ attribute: false }) steps: OkStep[] = [];
  /** Índice (0-based) del paso actual. */
  @property({ type: Number }) current = 0;
  /** Etiqueta del botón Atrás. Default INGLÉS. */
  @property() backLabel = 'Back';
  /** Etiqueta del botón Siguiente. Default INGLÉS. */
  @property() nextLabel = 'Next';
  /** Etiqueta del botón Finalizar (último paso). Default INGLÉS. */
  @property() finishLabel = 'Finish';

  /** Cambia al índice dado (con clamp) y emite ok-step-change si realmente cambia. */
  private _goTo(index: number): void {
    const last = this.steps.length - 1;
    const next = Math.max(0, Math.min(index, last));
    if (next === this.current) return;
    this.current = next;
    this.dispatchEvent(
      new CustomEvent('ok-step-change', {
        detail: { index: next },
        bubbles: true,
        composed: true,
      }),
    );
  }

  /** Retrocede un paso. */
  private _back(): void {
    this._goTo(this.current - 1);
  }

  /** Avanza un paso, o emite ok-finish si es el último. */
  private _next(): void {
    if (this.current >= this.steps.length - 1) {
      this.dispatchEvent(
        new CustomEvent('ok-finish', { bubbles: true, composed: true }),
      );
      return;
    }
    this._goTo(this.current + 1);
  }

  /** Navegación desde el stepper (clic en un paso). */
  private _onStepSelect(e: Event): void {
    const { index } = (e as CustomEvent<{ index: number }>).detail;
    // Detenemos el evento del stepper: el wizard re-emite su propio ok-step-change.
    e.stopPropagation();
    this._goTo(index);
  }

  render(): unknown {
    const isFirst = this.current <= 0;
    const isLast = this.current >= this.steps.length - 1;

    return html`
      <div class="stepper">
        <ok-stepper
          .steps=${this.steps}
          .current=${this.current}
          @ok-step-select=${(e: Event) => this._onStepSelect(e)}
        ></ok-stepper>
      </div>

      <!-- Solo el panel del paso actual es visible; el resto queda oculto pero en el DOM -->
      <div class="panels">
        ${this.steps.map(
          (_step, i) => html`<div class="panel" ?hidden=${i !== this.current}>
            <slot name="step-${i}"></slot>
          </div>`,
        )}
      </div>

      <div class="nav ${isFirst ? 'no-back' : ''}">
        ${isFirst
          ? ''
          : html`<ion-button fill="outline" color="medium" @click=${() => this._back()}>
              ${this.backLabel}
            </ion-button>`}
        <ion-button color="primary" @click=${() => this._next()}>
          ${isLast ? this.finishLabel : this.nextLabel}
        </ion-button>
      </div>
    `;
  }
}

// Aseguramos que ok-stepper queda referenciado (registro idempotente vía su propio módulo).
void OkStepper;

define('ok-wizard', OkWizard);

declare global {
  interface HTMLElementTagNameMap {
    'ok-wizard': OkWizard;
  }
}
