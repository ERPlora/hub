import { LitElement, html, css } from 'lit';
import { property } from 'lit/decorators.js';
import { define } from '../../base/define.js';

// ok-cta-band — banda de llamada a la acción (final de página/sección). Fondo con degradado de
// marca (o glass), título grande, subtítulo y CTAs (slot="actions", normalmente <ion-button>).
// Centrada por defecto.
//
//   <ok-cta-band eyebrow="Empieza hoy" heading="Tu ERP, listo en 5 minutos"
//                subheading="Sin tarjeta. Sin instalación.">
//     <ion-button slot="actions" href="/signup">Crear mi hub</ion-button>
//     <ion-button slot="actions" fill="outline" href="/demo">Ver demo</ion-button>
//   </ok-cta-band>
export class OkCtaBand extends LitElement {
  static styles = css`
    :host {
      display: block;
      width: 100%;
      --primary: var(--ion-color-primary, #1496d6);
      --primary-contrast: var(--ion-color-primary-contrast, #ffffff);
      --color: var(--ok-text, var(--ion-text-color, #18181b));
      --muted: var(--ok-muted, rgba(var(--ion-text-color-rgb, 24, 24, 27), 0.62));
      --surface: var(--ok-surface, var(--ion-card-background, var(--ion-background-color, #fff)));
      --radius: var(--ok-radius-lg, 28px);
      font-family: var(--ok-font, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif);
    }
    .band {
      box-sizing: border-box;
      position: relative;
      overflow: hidden;
      border-radius: var(--radius);
      padding: clamp(2.5rem, 6vw, 4.5rem) clamp(1.5rem, 5vw, 4rem);
      text-align: center;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 1rem;
    }
    /* Sólido de marca (def): texto en contraste */
    :host(:not([variant])) .band,
    :host([variant='solid']) .band {
      color: var(--primary-contrast);
      background:
        radial-gradient(80% 120% at 0% 0%, color-mix(in oklab, #fff 22%, transparent), transparent 60%),
        radial-gradient(80% 120% at 100% 100%, color-mix(in oklab, #000 18%, transparent), transparent 55%),
        linear-gradient(120deg, var(--primary), color-mix(in oklab, var(--primary) 60%, #6d28d9 40%));
    }
    :host([variant='solid']) .eyebrow,
    :host(:not([variant])) .eyebrow { color: color-mix(in oklab, var(--primary-contrast) 85%, transparent); }
    :host([variant='solid']) .sub,
    :host(:not([variant])) .sub { color: color-mix(in oklab, var(--primary-contrast) 85%, transparent); }
    /* Glass / sutil: hereda el color del tema */
    :host([variant='soft']) .band {
      color: var(--color);
      background: linear-gradient(135deg, color-mix(in oklab, var(--primary) 10%, var(--surface)),
        color-mix(in oklab, var(--primary) 3%, var(--surface)));
      border: 1px solid color-mix(in oklab, var(--primary) 22%, transparent);
    }
    :host([variant='glass']) .band {
      color: var(--color);
      background: color-mix(in oklab, var(--surface) 55%, transparent);
      -webkit-backdrop-filter: blur(18px) saturate(1.4);
      backdrop-filter: blur(18px) saturate(1.4);
      border: 1px solid color-mix(in oklab, var(--color) 12%, transparent);
    }
    .eyebrow {
      font-size: 0.74rem;
      font-weight: 600;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      color: var(--muted);
    }
    .title {
      margin: 0;
      font-size: clamp(1.7rem, 1.1rem + 2.8vw, 3rem);
      line-height: 1.08;
      letter-spacing: -0.03em;
      font-weight: 680;
      max-width: 22ch;
    }
    ::slotted([slot='heading']) {
      margin: 0;
      font-size: clamp(1.7rem, 1.1rem + 2.8vw, 3rem);
      line-height: 1.08;
      letter-spacing: -0.03em;
      font-weight: 680;
    }
    .sub {
      margin: 0;
      font-size: clamp(1rem, 0.95rem + 0.3vw, 1.2rem);
      line-height: 1.5;
      color: var(--muted);
      max-width: 50ch;
    }
    .actions {
      display: flex;
      flex-wrap: wrap;
      gap: 0.75rem;
      justify-content: center;
      margin-top: 0.6rem;
    }
  `;

  /** Eyebrow opcional. */
  @property() eyebrow?: string;
  /** Título. Para markup rico usa slot="heading". */
  @property() heading?: string;
  /** Subtítulo. */
  @property() subheading?: string;
  /** Estilo: 'solid' (def, degradado de marca) | 'soft' | 'glass'. */
  @property({ reflect: true }) variant: 'solid' | 'soft' | 'glass' = 'solid';

  render(): unknown {
    return html`
      <div class="band">
        ${this.eyebrow ? html`<span class="eyebrow">${this.eyebrow}</span>` : null}
        ${this.heading ? html`<h2 class="title">${this.heading}</h2>` : html`<slot name="heading"></slot>`}
        ${this.subheading ? html`<p class="sub">${this.subheading}</p>` : null}
        <div class="actions"><slot name="actions"></slot></div>
      </div>
    `;
  }
}

define('ok-cta-band', OkCtaBand);

declare global {
  interface HTMLElementTagNameMap {
    'ok-cta-band': OkCtaBand;
  }
}
