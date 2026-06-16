import { LitElement, html, css } from 'lit';
import { property, state } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// ok-calculator — calculadora genérica (display de dos líneas + teclado 4 columnas).
// Porta el diseño .ux-calc del CSS antiguo: tarjeta 280px, línea prev tenue + valor 3xl
// tabular, operadores ámbar (.is-active resalta el elegido), equals en color de marca,
// teclas fn (AC/⌫) en mayúsculas, AC y 0 ocupan 2 columnas.
// Máquina de estados completa: operator / stored / justEvaluated.

/** Operador interno usado por la máquina de estados. */
export type OkCalculatorOp = '+' | '-' | '*' | '/' | '';

/** Detalle del evento ok-input emitido en cada pulsación de tecla. */
export interface OkCalculatorInputDetail {
  /** Tecla pulsada tal cual aparece en el teclado (dígito, operador, '=', 'AC', '⌫', '.'). */
  key: string;
}

/** Detalle del evento ok-change emitido cuando cambia el valor mostrado. */
export interface OkCalculatorChangeDetail {
  /** Valor actual del display. */
  value: string;
}

// Definición declarativa del teclado: cada celda describe su tipo y símbolo.
interface KeyDef {
  label: string;
  kind: 'digit' | 'op' | 'equals' | 'fn' | 'dot';
  op?: OkCalculatorOp;
  wide?: boolean;
}

const KEYS: KeyDef[] = [
  { label: 'AC', kind: 'fn', wide: true },
  { label: '⌫', kind: 'fn' },
  { label: '÷', kind: 'op', op: '/' },
  { label: '7', kind: 'digit' },
  { label: '8', kind: 'digit' },
  { label: '9', kind: 'digit' },
  { label: '×', kind: 'op', op: '*' },
  { label: '4', kind: 'digit' },
  { label: '5', kind: 'digit' },
  { label: '6', kind: 'digit' },
  { label: '−', kind: 'op', op: '-' },
  { label: '1', kind: 'digit' },
  { label: '2', kind: 'digit' },
  { label: '3', kind: 'digit' },
  { label: '+', kind: 'op', op: '+' },
  { label: '0', kind: 'digit', wide: true },
  { label: '.', kind: 'dot' },
  { label: '=', kind: 'equals' },
];

// Símbolos para mostrar el operador en la línea prev.
const OP_SYMBOL: Record<Exclude<OkCalculatorOp, ''>, string> = {
  '+': '+',
  '-': '−',
  '*': '×',
  '/': '÷',
};

export class OkCalculator extends LitElement {
  static styles = css`
    :host {
      display: block;
      width: 100%;
      /* Tokens propios estilo Ionic (overridables): --ok-* → --ion-* → hex. */
      --bg: var(--ok-surface-2, var(--ion-color-step-50, #f7f7f8));
      --display-bg: var(--ok-surface-3, var(--ion-color-step-100, #eeeef0));
      --line: var(--ok-border-color, var(--ion-border-color, #d7d8da));
      --ink: var(--ok-text-color, var(--ion-text-color, #1f2933));
      --ink-2: var(--ok-color-medium-shade, var(--ion-color-medium-shade, #5a5e62));
      --ink-3: var(--ok-color-medium, var(--ion-color-medium, #92949c));
      --key-bg: var(--ok-surface-3, var(--ion-color-step-100, #eeeef0));
      --key-bg-hover: var(--ok-surface-4, var(--ion-color-step-150, #e3e3e6));
      --radius-md: var(--ok-radius-md, 10px);
      --radius-lg: var(--ok-radius-lg, 14px);
      --radius-xl: var(--ok-radius-xl, 18px);
      /* Operador ámbar (warn). */
      --op-bg: var(--ok-color-warning-tint, var(--ion-color-warning-tint, #ffd965));
      --op-fg: var(--ok-color-warning-shade, var(--ion-color-warning-shade, #b88a00));
      --op-active-bg: var(--ok-color-warning, var(--ion-color-warning, #ffc409));
      --op-active-fg: var(--ok-color-warning-contrast, var(--ion-color-warning-contrast, #1f2933));
      /* Equals en color de marca. */
      --equals-bg: var(--ok-color-primary, var(--ion-color-primary, #3880ff));
      --equals-bg-hover: var(--ok-color-primary-shade, var(--ion-color-primary-shade, #3171e0));
      --equals-fg: var(--ok-color-primary-contrast, var(--ion-color-primary-contrast, #fff));
      --glow: var(--ok-focus-ring, 0 0 0 3px rgba(56, 128, 255, 0.35));
    }

    .calc {
      display: flex;
      flex-direction: column;
      gap: 12px;
      width: 280px;
      max-width: 100%;
      box-sizing: border-box;
      padding: 14px;
      background: var(--bg);
      border: 1px solid var(--line);
      border-radius: var(--radius-xl);
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
    }

    .display {
      display: flex;
      flex-direction: column;
      align-items: flex-end;
      justify-content: flex-end;
      gap: 4px;
      min-height: 78px;
      padding: 12px 14px;
      box-sizing: border-box;
      background: var(--display-bg);
      border: 1px solid var(--line);
      border-radius: var(--radius-lg);
      text-align: right;
      font-variant-numeric: tabular-nums;
      overflow: hidden;
    }

    .display-prev {
      width: 100%;
      font-size: 0.8125rem;
      color: var(--ink-3);
      letter-spacing: -0.01em;
      line-height: 1.2;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      min-height: 14px;
    }

    .display-value {
      width: 100%;
      font-size: 1.875rem; /* 3xl */
      font-weight: 600;
      color: var(--ink);
      letter-spacing: -0.03em;
      line-height: 1.05;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .keys {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 6px;
    }

    .key {
      height: 48px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      box-sizing: border-box;
      background: var(--key-bg);
      border: 1px solid var(--line);
      border-radius: var(--radius-md);
      color: var(--ink);
      font: inherit;
      font-size: 1.125rem;
      font-weight: 500;
      font-variant-numeric: tabular-nums;
      letter-spacing: -0.02em;
      cursor: pointer;
      user-select: none;
      transition: background 120ms ease, transform 120ms ease;
    }
    .key:hover {
      background: var(--key-bg-hover);
    }
    .key:active {
      transform: scale(0.96);
    }
    .key:focus-visible {
      outline: none;
      box-shadow: var(--glow);
    }

    .key--op {
      background: var(--op-bg);
      color: var(--op-fg);
      border-color: transparent;
    }
    .key--op:hover {
      background: var(--op-bg);
      filter: brightness(0.96);
    }
    .key--op.is-active {
      background: var(--op-active-bg);
      color: var(--op-active-fg);
      border-color: transparent;
    }

    .key--equals {
      background: var(--equals-bg);
      color: var(--equals-fg);
      border-color: transparent;
      box-shadow: 0 1px 0 rgba(0, 0, 0, 0.2), inset 0 1px 0 rgba(255, 255, 255, 0.18);
    }
    .key--equals:hover {
      background: var(--equals-bg-hover);
    }

    .key--fn {
      background: transparent;
      color: var(--ink-2);
      font-size: 0.875rem;
      font-weight: 500;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }
    .key--fn:hover {
      background: var(--key-bg);
      color: var(--ink);
    }

    .key--wide {
      grid-column: span 2;
    }
  `;

  /**
   * Valor mostrado. Si se setea desde fuera actúa como modo controlado (opcional);
   * si no, el componente gestiona su propio estado interno.
   */
  @property() value?: string;

  // Estado interno de la máquina (mirror de los signals del diseño antiguo).
  @state() private _display = '0';
  @state() private _prev = '';
  @state() private _op: OkCalculatorOp = '';
  @state() private _stored = 0;
  @state() private _justEvaluated = false;

  // Devuelve el display efectivo (controlado si `value` está definido).
  private get _shownValue(): string {
    return this.value !== undefined ? this.value : this._display;
  }

  render(): unknown {
    return html`
      <div class="calc" role="group" aria-label="Calculadora">
        <div class="display">
          <div class="display-prev" aria-hidden="true">${this._prev}</div>
          <div class="display-value" role="status" aria-live="polite">
            ${this._shownValue}
          </div>
        </div>
        <div class="keys">
          ${KEYS.map((k) => this._renderKey(k))}
        </div>
      </div>
    `;
  }

  private _renderKey(k: KeyDef): unknown {
    const classes = ['key'];
    if (k.kind === 'op') classes.push('key--op');
    if (k.kind === 'equals') classes.push('key--equals');
    if (k.kind === 'fn') classes.push('key--fn');
    if (k.wide) classes.push('key--wide');
    // Resalta el operador actualmente elegido.
    const active = k.kind === 'op' && k.op === this._op;
    if (active) classes.push('is-active');

    return html`
      <button
        type="button"
        class=${classes.join(' ')}
        aria-pressed=${k.kind === 'op' ? String(active) : 'false'}
        aria-label=${this._ariaForKey(k)}
        @click=${() => this._onKey(k)}
      >
        ${k.label}
      </button>
    `;
  }

  // Etiqueta accesible legible para teclas con símbolos.
  private _ariaForKey(k: KeyDef): string {
    switch (k.label) {
      case '÷':
        return 'Dividir';
      case '×':
        return 'Multiplicar';
      case '−':
        return 'Restar';
      case '+':
        return 'Sumar';
      case '=':
        return 'Igual';
      case '⌫':
        return 'Borrar';
      case 'AC':
        return 'Borrar todo';
      case '.':
        return 'Coma decimal';
      default:
        return k.label;
    }
  }

  // Despacha la pulsación según el tipo de tecla y emite los eventos.
  private _onKey(k: KeyDef): void {
    this._emitInput(k.label);
    switch (k.kind) {
      case 'digit':
        this._inputDigit(k.label);
        break;
      case 'dot':
        this._inputDot();
        break;
      case 'op':
        this._applyOperator(k.op as OkCalculatorOp, k.label);
        break;
      case 'equals':
        this._evaluate();
        break;
      case 'fn':
        if (k.label === 'AC') this._clear();
        else this._backspace();
        break;
    }
  }

  // Lee el display actual sincronizado con el modo controlado.
  private get _cur(): string {
    return this._shownValue;
  }

  private _inputDigit(d: string): void {
    const cur = this._cur;
    const next = cur === '0' || this._justEvaluated ? d : cur + d;
    this._justEvaluated = false;
    this._setDisplay(next);
  }

  private _inputDot(): void {
    const cur = this._cur;
    const next = cur.includes('.') ? cur : cur + '.';
    this._justEvaluated = false;
    this._setDisplay(next);
  }

  private _applyOperator(op: OkCalculatorOp, sym: string): void {
    this._stored = parseFloat(this._cur);
    this._op = op;
    this._prev = `${this._cur} ${sym}`;
    this._justEvaluated = false;
    this._setDisplay('0');
  }

  private _evaluate(): void {
    const b = parseFloat(this._cur);
    const a = this._stored;
    let r: number;
    switch (this._op) {
      case '+':
        r = a + b;
        break;
      case '-':
        r = a - b;
        break;
      case '*':
        r = a * b;
        break;
      case '/':
        r = b === 0 ? 0 : a / b;
        break;
      default:
        r = b;
    }
    const opSym = this._op ? OP_SYMBOL[this._op] : '';
    this._prev = this._op ? `${a} ${opSym} ${b} =` : '';
    const result = Number.isFinite(r) ? +r.toFixed(8) : 0;
    this._op = '';
    this._stored = 0;
    this._justEvaluated = true;
    this._setDisplay(String(result));
  }

  private _clear(): void {
    this._prev = '';
    this._op = '';
    this._stored = 0;
    this._justEvaluated = false;
    this._setDisplay('0');
  }

  private _backspace(): void {
    const cur = this._cur;
    const next = cur.length > 1 ? cur.slice(0, -1) : '0';
    this._setDisplay(next);
  }

  // Aplica el nuevo display y emite ok-change. En modo controlado no muta
  // el estado interno: el consumidor decide si actualiza `value`.
  private _setDisplay(next: string): void {
    if (this.value === undefined) {
      this._display = next;
    }
    this._emitChange(next);
  }

  private _emitInput(key: string): void {
    this.dispatchEvent(
      new CustomEvent<OkCalculatorInputDetail>('ok-input', {
        detail: { key },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private _emitChange(value: string): void {
    this.dispatchEvent(
      new CustomEvent<OkCalculatorChangeDetail>('ok-change', {
        detail: { value },
        bubbles: true,
        composed: true,
      }),
    );
  }
}

define('ok-calculator', OkCalculator);

declare global {
  interface HTMLElementTagNameMap {
    'ok-calculator': OkCalculator;
  }
}
