import { LitElement, html, css } from 'lit';
import { property, state } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// ok-currency — input monetario con máscara de moneda (miles + decimales + símbolo).
// AUTOCONTENIDO: CSS propio en el shadow; por dentro usa un `ion-input` (el HOST registra Ionic,
// aquí no se importa @ionic/core). CSP-safe: el formateo usa `Intl.NumberFormat` nativo, sin eval.
//
// Mientras se escribe sólo se aceptan dígitos y el separador decimal del locale (el resto se
// descarta). Al perder el foco se reformatea el valor completo con símbolo y separador de miles.
//
// Props:
//   • value        → importe numérico (number). Vacío/NaN = sin valor.
//   • currency     → código ISO 4217 (def 'EUR').
//   • locale       → locale BCP-47 para el formato (def navegador o 'es-ES').
//   • placeholder  → texto cuando está vacío.
//   • label?       → etiqueta opcional sobre el campo.
// Evento (bubbles + composed):
//   • `ok-change`  detail { value: number }  → al perder el foco con un importe válido.
export class OkCurrency extends LitElement {
  static styles = css`
    :host {
      /* Vars overridable (estilo Ionic), default = cadena --ok-* → --ion-* → hex */
      --background: var(--ok-surface, var(--ion-item-background, #ffffff));
      --color: var(--ok-text, var(--ion-text-color, #1c1b17));
      --border-color: var(--ok-border, rgba(var(--ion-text-color-rgb, 28, 27, 23), 0.2));
      --border-radius: var(--ok-radius, var(--ion-border-radius, 8px));
      --primary-color: var(--ok-primary, var(--ion-color-primary, #3880ff));
      --font: var(--ok-font, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif);

      /* Ocupa el ancho del contenedor y es responsive. */
      display: block;
      width: 100%;
      color: var(--color);
      font-family: var(--font);
    }
    .control {
      --background: var(--background);
      --color: var(--color);
      --border-color: var(--border-color);
      --border-radius: var(--border-radius);
      --highlight-color-focused: var(--primary-color);
      width: 100%;
    }
  `;

  /** Importe numérico actual. */
  @property({ type: Number }) value?: number;
  /** Código ISO 4217 de la moneda. */
  @property() currency = 'EUR';
  /** Locale BCP-47 para el formato (def: navegador o 'es-ES'). */
  @property() locale: string =
    (typeof navigator !== 'undefined' && navigator.language) || 'es-ES';
  /** Placeholder cuando el campo está vacío. */
  @property() placeholder = '';
  /** Etiqueta opcional sobre el campo. */
  @property() label?: string;

  // Texto mostrado en el ion-input (formateado o "en edición").
  @state() private display = '';
  // Marca de foco: mientras está enfocado mostramos sólo el número crudo (editable).
  @state() private focused = false;

  // Construye un formateador de moneda (símbolo + miles + 2 decimales) para el locale actual.
  private currencyFormatter(): Intl.NumberFormat {
    return new Intl.NumberFormat(this.locale, {
      style: 'currency',
      currency: this.currency,
    });
  }

  // Devuelve el separador decimal del locale (',' o '.') usando Intl.
  private decimalSeparator(): string {
    const parts = new Intl.NumberFormat(this.locale).formatToParts(1.1);
    return parts.find((p) => p.type === 'decimal')?.value ?? '.';
  }

  // Limpia el texto crudo dejando sólo dígitos y un único separador decimal.
  private sanitize(raw: string): string {
    const sep = this.decimalSeparator();
    let out = '';
    let hasSep = false;
    for (const ch of raw) {
      if (ch >= '0' && ch <= '9') out += ch;
      else if (ch === sep && !hasSep) {
        out += sep;
        hasSep = true;
      }
    }
    return out;
  }

  // Convierte el texto crudo (con separador del locale) a number. NaN si no hay número.
  private parse(raw: string): number {
    const sep = this.decimalSeparator();
    // Normaliza a punto decimal para Number().
    const normalized = this.sanitize(raw).split(sep).join('.');
    if (!normalized) return NaN;
    return Number(normalized);
  }

  // Sincroniza el texto mostrado a partir del `value` cuando NO está enfocado.
  private syncDisplayFromValue(): void {
    if (this.focused) return;
    if (this.value == null || Number.isNaN(this.value)) {
      this.display = '';
      return;
    }
    this.display = this.currencyFormatter().format(this.value);
  }

  // Recalcula el display ante cambios de props relevantes (value/currency/locale).
  protected willUpdate(changed: Map<string, unknown>): void {
    if (
      (changed.has('value') || changed.has('currency') || changed.has('locale')) &&
      !this.focused
    ) {
      this.syncDisplayFromValue();
    }
  }

  // Mientras escribe: filtra a dígitos + separador decimal y refleja el texto crudo.
  private onInput(e: Event): void {
    const raw = (e as CustomEvent).detail?.value ?? '';
    this.display = this.sanitize(String(raw));
  }

  // Al enfocar: muestra el número crudo (sin símbolo ni miles) para editar cómodamente.
  private onFocus(): void {
    this.focused = true;
    if (this.value != null && !Number.isNaN(this.value)) {
      const sep = this.decimalSeparator();
      // Representa el número con separador del locale, sin agrupación de miles.
      this.display = String(this.value).split('.').join(sep);
    } else {
      this.display = '';
    }
  }

  // Al perder el foco: parsea, reformatea con símbolo y emite `ok-change` si cambió.
  private onBlur(): void {
    this.focused = false;
    const parsed = this.parse(this.display);
    if (Number.isNaN(parsed)) {
      this.value = undefined;
      this.display = '';
    } else {
      this.value = parsed;
      this.display = this.currencyFormatter().format(parsed);
    }
    this.dispatchEvent(
      new CustomEvent('ok-change', {
        detail: { value: Number.isNaN(parsed) ? NaN : parsed },
        bubbles: true,
        composed: true,
      }),
    );
  }

  render(): unknown {
    return html`
      <ion-input
        class="control"
        fill="outline"
        inputmode="decimal"
        label=${this.label ?? ''}
        label-placement=${this.label ? 'stacked' : 'fixed'}
        placeholder=${this.placeholder}
        .value=${this.display}
        @ionInput=${this.onInput}
        @ionFocus=${this.onFocus}
        @ionBlur=${this.onBlur}
      ></ion-input>
    `;
  }
}

define('ok-currency', OkCurrency);

declare global {
  interface HTMLElementTagNameMap {
    'ok-currency': OkCurrency;
  }
}
