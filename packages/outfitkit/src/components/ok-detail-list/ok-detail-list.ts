import { LitElement, html, css, nothing } from 'lit';
import { property } from 'lit/decorators.js';
import { unsafeHTML } from 'lit/directives/unsafe-html.js';
import { define } from '../../base/define.js';

/** Un par etiqueta/valor del detail-list (description list). */
export interface OkDetailItem {
  /** Etiqueta del par (muted). */
  label: string;
  /** Valor del par. String plano o, si `html` es true, marcado HTML enriquecido. */
  value?: string;
  /** Si true, `value` se interpreta como HTML enriquecido (sanitiza tú la fuente). */
  html?: boolean;
  /** Si true, este par ocupa el ancho completo aunque haya 2 columnas. */
  full?: boolean;
}

// ok-detail-list — lista de detalle (description list, <dl>) para vistas de ficha.
// Renderiza pares label/value alineados por baseline, con la etiqueta muted.
// Porta el look del .ux-stack del CSS antiguo (grid minmax(120px,30%) 1fr).
// Buen compañero de ok-page-header en pantallas de detalle.
export class OkDetailList extends LitElement {
  static styles = css`
    :host {
      display: block;
      width: 100%;
      /* Tokens propios estilo Ionic (overridables): --ok-* → --ion-* → hex. */
      --label-color: var(--ok-color-medium, var(--ion-color-medium, #92949c));
      --value-color: var(--ok-text-color, var(--ion-text-color, #1f2933));
      --row-gap: 0.75rem;
      --col-gap: 1rem;
      --label-width: minmax(120px, 30%);
      --divider-color: var(--ok-border-color, var(--ion-border-color, #e0e0e0));
    }

    .dl {
      display: grid;
      grid-template-columns: 1fr;
      gap: var(--row-gap) var(--col-gap);
      margin: 0;
      padding: 0;
      box-sizing: border-box;
    }

    /* 2 columnas en desktop; se apila a 1 en pantallas estrechas. */
    :host([columns='2']) .dl {
      grid-template-columns: 1fr 1fr;
    }

    /* Modo denso: menos separación vertical. */
    :host([dense]) {
      --row-gap: 0.375rem;
    }

    .row {
      display: grid;
      grid-template-columns: var(--label-width) 1fr;
      gap: 0.25rem var(--col-gap);
      align-items: baseline;
      min-width: 0;
    }

    /* Un par puede forzar ancho completo en layout de 2 columnas. */
    .row.full {
      grid-column: 1 / -1;
    }

    .label {
      margin: 0;
      font-size: 0.8125rem;
      font-weight: 500;
      color: var(--label-color);
      min-width: 0;
      overflow-wrap: anywhere;
    }

    .value {
      margin: 0;
      font-size: 0.9375rem;
      line-height: 1.4;
      color: var(--value-color);
      min-width: 0;
      overflow-wrap: anywhere;
    }

    :host([dense]) .value {
      font-size: 0.875rem;
    }

    .value.empty {
      color: var(--label-color);
    }

    /* El valor enriquecido puede traer enlaces/badges: que hereden bien. */
    .value ::slotted(*),
    .value a {
      color: inherit;
    }

    /* Apilado en móvil: la etiqueta encima del valor, full width. */
    @media (max-width: 600px) {
      :host([columns='2']) .dl {
        grid-template-columns: 1fr;
      }
      .row {
        grid-template-columns: 1fr;
        gap: 0.125rem;
      }
    }
  `;

  /** Pares label/value a renderizar. */
  @property({ attribute: false }) items: OkDetailItem[] = [];

  /** Número de columnas en desktop (1 ó 2). Reflejado a atributo para el CSS. */
  @property({ type: Number, reflect: true }) columns: 1 | 2 = 1;

  /** Modo compacto (menos separación). Reflejado a atributo. */
  @property({ type: Boolean, reflect: true }) dense = false;

  /** Placeholder para valores vacíos. */
  @property() placeholder = '—';

  private renderValue(item: OkDetailItem): unknown {
    const raw = item.value;
    if (raw === undefined || raw === null || raw === '') {
      return html`<dd class="value empty">${this.placeholder}</dd>`;
    }
    if (item.html) {
      return html`<dd class="value">${unsafeHTML(raw)}</dd>`;
    }
    return html`<dd class="value">${raw}</dd>`;
  }

  render(): unknown {
    const items = this.items ?? [];
    if (items.length === 0) {
      return nothing;
    }
    return html`
      <dl class="dl">
        ${items.map(
          (item) => html`
            <div class="row ${item.full ? 'full' : ''}" role="presentation">
              <dt class="label">${item.label}</dt>
              ${this.renderValue(item)}
            </div>
          `,
        )}
      </dl>
    `;
  }
}

define('ok-detail-list', OkDetailList);

declare global {
  interface HTMLElementTagNameMap {
    'ok-detail-list': OkDetailList;
  }
}
