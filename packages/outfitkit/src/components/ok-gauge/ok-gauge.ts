import { LitElement, html, css } from 'lit';
import { property } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// ok-gauge — gauge/medidor CONSOLIDADO (arc · ring · bullet) en SVG a mano.
// Porta el diseño de la librería CSS antigua: ux-gauge (semicírculo), ux-circ /
// ux-oee (anillo determinado) y ux-bullet/ux-perf (barra Tufte con zonas + target).
// AUTOCONTENIDO y CSP-safe: SVG dibujado a mano, sin librerías de charts.
//   • type 'arc'    → semicírculo 180° (half-dial), relleno por stroke-dasharray animado.
//   • type 'ring'   → círculo completo determinado, empieza a las 12h (rotate(-90deg)),
//                     etiqueta {value} centrada.
//   • type 'bullet' → barra horizontal Tufte con zonas cualitativas + tick de target.
// El color del relleno cambia según `thresholds` (zonas) o `color` explícito.

/** Una zona/umbral cualitativo del gauge. Se aplica hasta el valor `to`. */
export interface OkGaugeThreshold {
  /** Límite superior de la zona (en la escala min..max). */
  to: number;
  /** Color de la zona (cualquier color CSS válido). */
  color: string;
}

/** Tipo de gauge a renderizar. */
export type OkGaugeType = 'arc' | 'ring' | 'bullet';

export class OkGauge extends LitElement {
  static styles = css`
    :host {
      display: block;
      width: 100%;
      box-sizing: border-box;

      /* Tokens propios estilo Ionic (overridables): --ok-* → --ion-* → hex. */
      --bg: var(--ok-surface, var(--ion-background-color, #ffffff));
      --line: var(--ok-border-color, var(--ion-border-color, #e0e0e0));
      --track: var(--ok-track-color, var(--ion-color-light, #f4f5f8));
      --ink: var(--ok-text-color, var(--ion-text-color, #1f2933));
      --ink-muted: var(--ok-color-medium, var(--ion-color-medium, #92949c));
      --accent: var(--ok-primary, var(--ion-color-primary, #3880ff));
    }

    .gauge {
      display: inline-flex;
      flex-direction: column;
      align-items: center;
      gap: 6px;
      box-sizing: border-box;
    }

    /* Arc y ring centran su SVG; bullet ocupa el ancho del contenedor. */
    .gauge--arc,
    .gauge--ring {
      width: 100%;
      align-items: center;
    }
    .gauge--bullet {
      display: flex;
      width: 100%;
      align-items: stretch;
      gap: 4px;
    }

    .dial {
      position: relative;
      display: inline-flex;
      align-items: flex-end;
      justify-content: center;
    }

    svg {
      display: block;
      overflow: visible;
    }

    /* Trazo de pista y relleno (compartidos arc/ring). */
    .track {
      fill: none;
      stroke: var(--track);
      stroke-linecap: round;
    }
    .fill {
      fill: none;
      stroke-linecap: round;
      transition: stroke-dashoffset 0.6s cubic-bezier(0.16, 1, 0.3, 1);
    }

    /* Valor central. */
    .value {
      position: absolute;
      font-weight: 600;
      letter-spacing: -0.03em;
      color: var(--ink);
      font-variant-numeric: tabular-nums;
      line-height: 1;
    }
    .value sup {
      font-weight: 500;
      color: var(--ink-muted);
      margin-left: 1px;
    }
    /* Arc: valor abajo dentro del semicírculo. */
    .gauge--arc .value {
      left: 0;
      right: 0;
      bottom: 2px;
      text-align: center;
    }
    /* Ring: valor centrado. */
    .gauge--ring .dial {
      align-items: center;
    }
    .gauge--ring .value {
      inset: 0;
      display: grid;
      place-items: center;
    }

    .label {
      font-size: 0.6875rem;
      color: var(--ink-muted);
      text-transform: uppercase;
      letter-spacing: 0.06em;
      text-align: center;
    }
    .sublabel {
      font-size: 0.8125rem;
      color: var(--ink-muted);
      text-align: center;
    }

    /* ---- Bullet (barra Tufte) ---- */
    .bullet {
      display: flex;
      flex-direction: column;
      gap: 6px;
      width: 100%;
    }
    .bullet__head {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      gap: 8px;
      font-size: 0.8125rem;
      color: var(--ink-muted);
    }
    .bullet__head b {
      color: var(--ink);
      font-weight: 600;
      font-variant-numeric: tabular-nums;
    }
    .bullet__bar {
      position: relative;
      height: 14px;
      background: var(--track);
      border-radius: 999px;
      overflow: hidden;
    }
    .bullet__zone {
      position: absolute;
      top: 0;
      bottom: 0;
    }
    .bullet__fill {
      position: absolute;
      top: 3px;
      bottom: 3px;
      left: 3px;
      border-radius: 999px;
      transition: width 0.4s cubic-bezier(0.16, 1, 0.3, 1);
    }
    .bullet__target {
      position: absolute;
      top: -2px;
      bottom: -2px;
      width: 2px;
      background: var(--ink);
      border-radius: 1px;
      transform: translateX(-1px);
    }
  `;

  /** Tipo de gauge: semicírculo, anillo o barra bullet. */
  @property() type: OkGaugeType = 'arc';
  /** Valor actual a representar. */
  @property({ type: Number }) value = 0;
  /** Mínimo de la escala. */
  @property({ type: Number }) min = 0;
  /** Máximo de la escala. */
  @property({ type: Number }) max = 100;
  /** Zonas cualitativas (cada una se pinta hasta `to`); también fijan el color del relleno. */
  @property({ attribute: false }) thresholds: OkGaugeThreshold[] = [];
  /** Marcador de objetivo (bullet); si no se da, no se dibuja. */
  @property({ type: Number }) target?: number;
  /** Etiqueta principal (mayúsculas, muted). */
  @property() label?: string;
  /** Texto secundario bajo el valor / a la derecha del valor en bullet. */
  @property() sublabel?: string;
  /** Color explícito del relleno; tiene prioridad sobre los thresholds. */
  @property() color = '';
  /** Tamaño en px del diámetro (arc/ring); el alto del arc es la mitad. */
  @property({ type: Number }) size = 140;
  /** Sufijo del valor (ej. '%'); por defecto '%'. */
  @property() unit = '%';

  // Fracción normalizada del valor en [0,1] respecto a min..max.
  private get fraction(): number {
    const range = this.max - this.min || 1;
    const f = (this.value - this.min) / range;
    return Math.min(1, Math.max(0, f));
  }

  // Color efectivo del relleno: prop explícita > primer threshold cuyo `to` >= value > accent.
  private get fillColor(): string {
    if (this.color) return this.color;
    if (this.thresholds?.length) {
      const sorted = [...this.thresholds].sort((a, b) => a.to - b.to);
      for (const z of sorted) {
        if (this.value <= z.to) return z.color;
      }
      // Por encima de todas las zonas: usa la última.
      return sorted[sorted.length - 1].color;
    }
    return 'var(--accent)';
  }

  // Texto del valor con unidad como superíndice si la hay.
  // Se envuelve en un único <span> para que el valor y la unidad fluyan inline
  // como un solo bloque; en el ring el contenedor es grid/place-items y, sin el
  // wrapper, el número y el <sup> caerían en filas distintas (uno encima de otro).
  private renderValueText(): unknown {
    const n = Number.isInteger(this.value) ? this.value : Number(this.value.toFixed(1));
    return html`<span class="value-text"
      >${n}${this.unit ? html`<sup>${this.unit}</sup>` : null}</span
    >`;
  }

  // ---- ARC: semicírculo 180° ----
  private renderArc(): unknown {
    const w = this.size;
    const stroke = Math.max(8, Math.round(w * 0.085));
    const pad = stroke / 2 + 2;
    const r = (w - pad * 2) / 2;
    const cx = w / 2;
    const cy = w / 2; // el centro del arco está en la base del semicírculo
    const h = r + pad; // alto = radio + padding (medio dial)
    // Path semicircular de izquierda (180°) a derecha (0°), por arriba.
    const x0 = cx - r;
    const x1 = cx + r;
    const arcPath = `M ${x0} ${cy} A ${r} ${r} 0 0 1 ${x1} ${cy}`;
    const len = Math.PI * r; // longitud del semicírculo
    const offset = len * (1 - this.fraction);
    const valueFs = Math.round(w * 0.18);

    return html`
      <div class="dial" style=${`width:${w}px;height:${h}px;`}>
        <svg
          width=${w}
          height=${h}
          viewBox=${`0 0 ${w} ${h}`}
          role="img"
          aria-label=${this.ariaText()}
        >
          <path class="track" d=${arcPath} stroke-width=${stroke} />
          <path
            class="fill"
            d=${arcPath}
            stroke=${this.fillColor}
            stroke-width=${stroke}
            stroke-dasharray=${len}
            stroke-dashoffset=${offset}
          />
        </svg>
        <div class="value" style=${`font-size:${valueFs}px;`}>${this.renderValueText()}</div>
      </div>
      ${this.label ? html`<div class="label">${this.label}</div>` : null}
      ${this.sublabel ? html`<div class="sublabel">${this.sublabel}</div>` : null}
    `;
  }

  // ---- RING: círculo completo determinado, empieza a las 12h ----
  private renderRing(): unknown {
    const w = this.size;
    const stroke = Math.max(6, Math.round(w * 0.075));
    const pad = stroke / 2 + 2;
    const r = (w - pad * 2) / 2;
    const cx = w / 2;
    const cy = w / 2;
    const circ = 2 * Math.PI * r;
    const offset = circ * (1 - this.fraction);
    const valueFs = Math.round(w * 0.2);

    return html`
      <div class="dial" style=${`width:${w}px;height:${w}px;`}>
        <svg
          width=${w}
          height=${w}
          viewBox=${`0 0 ${w} ${w}`}
          role="img"
          aria-label=${this.ariaText()}
          style="transform: rotate(-90deg);"
        >
          <circle class="track" cx=${cx} cy=${cy} r=${r} stroke-width=${stroke} />
          <circle
            class="fill"
            cx=${cx}
            cy=${cy}
            r=${r}
            stroke=${this.fillColor}
            stroke-width=${stroke}
            stroke-dasharray=${circ}
            stroke-dashoffset=${offset}
          />
        </svg>
        <div class="value" style=${`font-size:${valueFs}px;`}>${this.renderValueText()}</div>
      </div>
      ${this.label ? html`<div class="label">${this.label}</div>` : null}
      ${this.sublabel ? html`<div class="sublabel">${this.sublabel}</div>` : null}
    `;
  }

  // ---- BULLET: barra Tufte horizontal con zonas + target ----
  private renderBullet(): unknown {
    const range = this.max - this.min || 1;
    // Posición porcentual de un valor en la escala (0..100, clamp).
    const pct = (v: number): number =>
      Math.min(100, Math.max(0, ((v - this.min) / range) * 100));

    // Zonas cualitativas: cada threshold pinta desde el anterior `to` hasta el suyo.
    const sorted = this.thresholds?.length
      ? [...this.thresholds].sort((a, b) => a.to - b.to)
      : [];
    let prev = this.min;
    const zones = sorted.map((z) => {
      const left = pct(prev);
      const width = pct(z.to) - left;
      prev = z.to;
      return { left, width, color: z.color };
    });

    const fillW = pct(this.value);
    const valueNum = Number.isInteger(this.value)
      ? this.value
      : Number(this.value.toFixed(1));

    return html`
      <div class="bullet" role="img" aria-label=${this.ariaText()}>
        ${this.label || this.sublabel
          ? html`
              <div class="bullet__head">
                <span>${this.label ?? ''}</span>
                <b>${valueNum}${this.unit}${this.sublabel ? html` · ${this.sublabel}` : ''}</b>
              </div>
            `
          : null}
        <div class="bullet__bar">
          ${zones.map(
            (z) => html`
              <span
                class="bullet__zone"
                style=${`left:${z.left}%;width:${z.width}%;background:${this.zoneTint(
                  z.color,
                )};`}
              ></span>
            `,
          )}
          <span
            class="bullet__fill"
            style=${`width:calc(${fillW}% - 6px);background:${this.fillColor};`}
          ></span>
          ${this.target != null
            ? html`<span class="bullet__target" style=${`left:${pct(this.target)}%;`}></span>`
            : null}
        </div>
      </div>
    `;
  }

  // Tinte suave para el fondo de zona (la librería antigua usaba color-mix al ~18%).
  private zoneTint(color: string): string {
    return `color-mix(in srgb, ${color} 18%, transparent)`;
  }

  // Texto accesible que describe el gauge.
  private ariaText(): string {
    const base = `${this.label ? this.label + ': ' : ''}${this.value}${this.unit} de ${this.max}${this.unit}`;
    return this.target != null ? `${base} (objetivo ${this.target}${this.unit})` : base;
  }

  render(): unknown {
    if (this.type === 'bullet') {
      return html`<div class="gauge gauge--bullet">${this.renderBullet()}</div>`;
    }
    if (this.type === 'ring') {
      return html`<div class="gauge gauge--ring">${this.renderRing()}</div>`;
    }
    return html`<div class="gauge gauge--arc">${this.renderArc()}</div>`;
  }
}

define('ok-gauge', OkGauge);

declare global {
  interface HTMLElementTagNameMap {
    'ok-gauge': OkGauge;
  }
}
