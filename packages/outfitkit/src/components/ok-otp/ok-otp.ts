import { LitElement, html, css } from 'lit';
import { property, query } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// ok-otp — entrada de código de un solo uso (OTP): `length` casillas de un dígito, centradas.
// Auto-avanza al teclear, retrocede con Backspace, y al PEGAR reparte los dígitos por las casillas.
// AUTOCONTENIDO: CSS propio en el shadow. Usa inputs nativos `<input inputmode="numeric">`
// (no necesita Ionic para esto). El estado vive en la prop `value` (string de dígitos).
//   • prop `length`  → número de casillas (def 6)
//   • prop `value`   → valor actual (string de dígitos)
// Eventos (bubbles + composed):
//   • `ok-change`    detail { value }   — en cada cambio
//   • `ok-complete`  detail { value }   — cuando se llenan todas las casillas

// Textos traducibles (default inglés). Pásalos desde fuera vía la prop `labels`.
export interface OkOtpLabels {
  /** aria-label de cada casilla. Recibe el índice (1-based) y el total. */
  digitLabel: (index: number, length: number) => string;
}

const DEFAULT_LABELS: OkOtpLabels = {
  digitLabel: (index, length) => `Digit ${index} of ${length}`,
};

export class OkOtp extends LitElement {
  static styles = css`
    :host {
      /* Vars overridable (estilo Ionic), default = cadena --ok-* → --ion-* → hex */
      --color: var(--ok-text, var(--ion-text-color, #1c1b17));
      --background: var(--ok-surface, var(--ion-background-color, #ffffff));
      --border-color: var(--ok-border, rgba(var(--ion-text-color-rgb, 28, 27, 23), 0.25));
      --border-color-focus: var(--ok-primary, var(--ion-color-primary, #3880ff));
      --border-radius: var(--ok-radius, 8px);
      --gap: var(--ok-otp-gap, 0.5rem);
      --size: var(--ok-otp-size, 3rem);
      --font: var(--ok-font, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif);

      display: flex;
      justify-content: center;
      align-items: center;
      gap: var(--gap);
    }
    input {
      width: var(--size);
      height: var(--size);
      box-sizing: border-box;
      text-align: center;
      font-family: var(--font);
      font-size: calc(var(--size) * 0.45);
      font-weight: 600;
      color: var(--color);
      background: var(--background);
      border: 1px solid var(--border-color);
      border-radius: var(--border-radius);
      outline: none;
      transition: border-color 0.15s ease, box-shadow 0.15s ease;
      -moz-appearance: textfield;
    }
    input::-webkit-outer-spin-button,
    input::-webkit-inner-spin-button {
      -webkit-appearance: none;
      margin: 0;
    }
    input:focus {
      border-color: var(--border-color-focus);
      box-shadow: 0 0 0 2px rgba(var(--ion-color-primary-rgb, 56, 128, 255), 0.2);
    }
    input:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }
  `;

  /** Número de casillas de la OTP. */
  @property({ type: Number }) length = 6;
  /** Valor actual (string de dígitos). */
  @property({ type: String }) value = '';
  /** Textos traducibles (merge sobre los defaults en inglés). */
  @property({ attribute: false }) labels: Partial<OkOtpLabels> = {};

  // Textos efectivos: defaults en inglés + overrides del consumidor.
  private get t(): OkOtpLabels {
    return { ...DEFAULT_LABELS, ...this.labels };
  }

  @query('input') private firstInput?: HTMLInputElement;

  // Devuelve los inputs del shadow en orden.
  private get inputs(): HTMLInputElement[] {
    return Array.from(this.renderRoot.querySelectorAll('input'));
  }

  // Pone el foco en una casilla por índice (si existe) y selecciona su contenido.
  private focusAt(index: number): void {
    const el = this.inputs[index];
    if (el) {
      el.focus();
      el.select();
    }
  }

  // Reconstruye `value` desde el contenido de las casillas y emite eventos.
  private syncFromInputs(): void {
    const digits = this.inputs.map((el) => el.value).join('');
    this.value = digits;
    this.dispatchEvent(
      new CustomEvent('ok-change', {
        detail: { value: digits },
        bubbles: true,
        composed: true,
      }),
    );
    if (digits.length === this.length && /^\d+$/.test(digits)) {
      this.dispatchEvent(
        new CustomEvent('ok-complete', {
          detail: { value: digits },
          bubbles: true,
          composed: true,
        }),
      );
    }
  }

  // Teclear en una casilla: solo dígitos, fuerza un único carácter y auto-avanza.
  private onInput(e: Event, index: number): void {
    const el = e.target as HTMLInputElement;
    const cleaned = el.value.replace(/\D/g, '');
    if (cleaned.length > 1) {
      // Probablemente se introdujo más de un dígito (autocompletar): repártelos.
      this.distribute(cleaned, index);
      return;
    }
    el.value = cleaned;
    if (cleaned) this.focusAt(index + 1);
    this.syncFromInputs();
  }

  // Backspace en casilla vacía → retrocede y borra la anterior.
  private onKeydown(e: KeyboardEvent, index: number): void {
    const el = e.target as HTMLInputElement;
    if (e.key === 'Backspace' && !el.value && index > 0) {
      e.preventDefault();
      const prev = this.inputs[index - 1];
      if (prev) {
        prev.value = '';
        this.focusAt(index - 1);
        this.syncFromInputs();
      }
    } else if (e.key === 'ArrowLeft') {
      e.preventDefault();
      this.focusAt(index - 1);
    } else if (e.key === 'ArrowRight') {
      e.preventDefault();
      this.focusAt(index + 1);
    }
  }

  // Pegar: reparte los dígitos del portapapeles desde la casilla `start`.
  private onPaste(e: ClipboardEvent, start: number): void {
    e.preventDefault();
    const text = (e.clipboardData?.getData('text') ?? '').replace(/\D/g, '');
    if (text) this.distribute(text, start);
  }

  // Reparte una cadena de dígitos por las casillas a partir de `start`.
  private distribute(digits: string, start: number): void {
    const inputs = this.inputs;
    let i = start;
    for (const ch of digits) {
      if (i >= inputs.length) break;
      inputs[i].value = ch;
      i++;
    }
    this.focusAt(Math.min(i, inputs.length - 1));
    this.syncFromInputs();
  }

  // Sincroniza las casillas con `value` cuando cambia desde fuera.
  private digitAt(index: number): string {
    return this.value[index] ?? '';
  }

  // Tras renderizar, asegura que el foco inicial sea cómodo si está vacío (no fuerza foco).
  protected firstUpdated(): void {
    void this.firstInput;
  }

  render(): unknown {
    const slots = Array.from({ length: Math.max(0, this.length) }, (_, i) => i);
    return html`${slots.map(
      (i) => html`<input
        type="text"
        inputmode="numeric"
        autocomplete="one-time-code"
        maxlength="1"
        aria-label=${this.t.digitLabel(i + 1, this.length)}
        .value=${this.digitAt(i)}
        @input=${(e: Event) => this.onInput(e, i)}
        @keydown=${(e: KeyboardEvent) => this.onKeydown(e, i)}
        @paste=${(e: ClipboardEvent) => this.onPaste(e, i)}
        @focus=${(e: Event) => (e.target as HTMLInputElement).select()}
      />`,
    )}`;
  }
}

define('ok-otp', OkOtp);

declare global {
  interface HTMLElementTagNameMap {
    'ok-otp': OkOtp;
  }
}
