import { LitElement, html, css } from 'lit';
import { property, state } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// Entrada de un país en el selector (la aporta el consumidor o se usa el set por defecto).
export interface OkPhoneCountry {
  /** Código ISO 3166-1 alpha-2 (ej. 'ES'). Clave del país. */
  iso: string;
  /** Nombre legible del país. */
  name: string;
  /** Prefijo telefónico internacional con '+' (ej. '+34'). */
  dial: string;
}

// Textos i18n (default inglés). Pásalos desde fuera con `.labels`.
export interface OkPhoneLabels {
  /** aria-label del selector de país. */
  country: string;
  /** aria-label del input de número. */
  number: string;
}

const DEFAULT_LABELS: OkPhoneLabels = {
  country: 'Country',
  number: 'Phone number',
};

// ok-phone — teléfono con prefijo de país: un selector (bandera emoji + prefijo) + input de número.
// AUTOCONTENIDO: CSS propio en el shadow; por dentro usa `ion-select` (país) e `ion-input` (número);
// el HOST registra Ionic, aquí no se importa @ionic/core. CSP-safe: sin eval.
//
// La bandera emoji se deriva del ISO2 mediante Regional Indicator Symbols (no necesita assets).
//
// Props:
//   • value       → número nacional (string, sin prefijo).
//   • country     → ISO2 del país seleccionado (def 'ES').
//   • .countries? → Array<OkPhoneCountry>; si no se pasa, usa un set por defecto razonable.
//   • placeholder → texto del input de número.
//   • label?      → etiqueta opcional sobre el grupo.
// Evento (bubbles + composed):
//   • `ok-change`  detail { value, country, dial, e164 }
//        - value:   número nacional crudo (string)
//        - country: ISO2 seleccionado
//        - dial:    prefijo (+34…)
//        - e164:    número en formato E.164 (dial + dígitos), o '' si no hay número
export class OkPhone extends LitElement {
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
    .label {
      display: block;
      margin: 0 0 0.25rem;
      font-size: 0.85rem;
      color: var(--color);
    }
    /* Selector de país (ancho fijo cómodo) + número (resto del espacio). */
    .row {
      display: flex;
      align-items: stretch;
      gap: 0.5rem;
      width: 100%;
    }
    .country {
      --background: var(--background);
      --color: var(--color);
      --border-color: var(--border-color);
      --border-radius: var(--border-radius);
      flex: 0 0 7.5rem;
      min-width: 0;
    }
    .number {
      --background: var(--background);
      --color: var(--color);
      --border-color: var(--border-color);
      --border-radius: var(--border-radius);
      --highlight-color-focused: var(--primary-color);
      flex: 1 1 auto;
      min-width: 0;
    }
    /* Móvil: apila país sobre número para no comprimir el input. */
    @media (max-width: 480px) {
      .row {
        flex-direction: column;
      }
      .country {
        flex: 0 0 auto;
        width: 100%;
      }
    }
  `;

  // Set por defecto razonable (UE + GB/US + LatAm comunes). El consumidor puede sustituirlo.
  private static DEFAULT_COUNTRIES: OkPhoneCountry[] = [
    { iso: 'ES', name: 'España', dial: '+34' },
    { iso: 'PT', name: 'Portugal', dial: '+351' },
    { iso: 'FR', name: 'Francia', dial: '+33' },
    { iso: 'IT', name: 'Italia', dial: '+39' },
    { iso: 'DE', name: 'Alemania', dial: '+49' },
    { iso: 'GB', name: 'Reino Unido', dial: '+44' },
    { iso: 'IE', name: 'Irlanda', dial: '+353' },
    { iso: 'NL', name: 'Países Bajos', dial: '+31' },
    { iso: 'BE', name: 'Bélgica', dial: '+32' },
    { iso: 'US', name: 'Estados Unidos', dial: '+1' },
    { iso: 'MX', name: 'México', dial: '+52' },
    { iso: 'AR', name: 'Argentina', dial: '+54' },
    { iso: 'CO', name: 'Colombia', dial: '+57' },
    { iso: 'CL', name: 'Chile', dial: '+56' },
  ];

  /** Número nacional (sin prefijo). */
  @property() value = '';
  /** ISO2 del país seleccionado. */
  @property() country = 'ES';
  /** Lista de países (si no se pasa, se usa el set por defecto). */
  @property({ attribute: false }) countries?: OkPhoneCountry[];
  /** Placeholder del input de número. */
  @property() placeholder = '';
  /** Etiqueta opcional sobre el grupo. */
  @property() label?: string;

  /** Textos traducibles (merge sobre los defaults en inglés). */
  @property({ attribute: false }) labels: Partial<OkPhoneLabels> = {};

  private get t(): OkPhoneLabels {
    return { ...DEFAULT_LABELS, ...this.labels };
  }

  // Texto crudo del número (sólo dígitos), reflejado en el ion-input.
  @state() private number = '';

  // Sincroniza el número interno con la prop `value` (filtrando a dígitos).
  protected willUpdate(changed: Map<string, unknown>): void {
    if (changed.has('value')) {
      this.number = this.onlyDigits(this.value);
    }
  }

  // Lista efectiva de países.
  private get list(): OkPhoneCountry[] {
    return this.countries?.length ? this.countries : OkPhone.DEFAULT_COUNTRIES;
  }

  // País actualmente seleccionado (fallback al primero de la lista).
  private get current(): OkPhoneCountry {
    return this.list.find((c) => c.iso === this.country) ?? this.list[0];
  }

  // Deja sólo dígitos en una cadena.
  private onlyDigits(raw: string): string {
    let out = '';
    for (const ch of raw) if (ch >= '0' && ch <= '9') out += ch;
    return out;
  }

  // Convierte un ISO2 a su bandera emoji (Regional Indicator Symbols). Sin assets.
  private flag(iso: string): string {
    const code = iso.trim().toUpperCase();
    if (code.length !== 2) return '';
    const base = 0x1f1e6; // 'A'
    return String.fromCodePoint(
      base + (code.charCodeAt(0) - 65),
      base + (code.charCodeAt(1) - 65),
    );
  }

  // Calcula el número en formato E.164 (dial + dígitos), o '' si no hay número.
  private e164(): string {
    return this.number ? `${this.current.dial}${this.number}` : '';
  }

  // Emite `ok-change` con el estado actual completo.
  private emit(): void {
    this.dispatchEvent(
      new CustomEvent('ok-change', {
        detail: {
          value: this.number,
          country: this.current.iso,
          dial: this.current.dial,
          e164: this.e164(),
        },
        bubbles: true,
        composed: true,
      }),
    );
  }

  // Cambio de país en el ion-select.
  private onCountry(e: Event): void {
    const iso = (e as CustomEvent).detail?.value ?? this.country;
    this.country = iso;
    this.emit();
  }

  // Edición del número: filtra a dígitos y emite.
  private onNumber(e: Event): void {
    const raw = (e as CustomEvent).detail?.value ?? '';
    this.number = this.onlyDigits(String(raw));
    this.value = this.number;
    this.emit();
  }

  render(): unknown {
    return html`
      ${this.label ? html`<span class="label">${this.label}</span>` : null}
      <div class="row">
        <ion-select
          class="country"
          fill="outline"
          interface="popover"
          aria-label=${this.t.country}
          .value=${this.current.iso}
          @ionChange=${this.onCountry}
        >
          ${this.list.map(
            (c) => html`<ion-select-option value=${c.iso}>
              ${this.flag(c.iso)} ${c.dial}
            </ion-select-option>`,
          )}
        </ion-select>
        <ion-input
          class="number"
          type="tel"
          inputmode="tel"
          fill="outline"
          aria-label=${this.t.number}
          placeholder=${this.placeholder}
          .value=${this.number}
          @ionInput=${this.onNumber}
        ></ion-input>
      </div>
    `;
  }
}

define('ok-phone', OkPhone);

declare global {
  interface HTMLElementTagNameMap {
    'ok-phone': OkPhone;
  }
}
