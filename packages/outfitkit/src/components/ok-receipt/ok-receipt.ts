import { LitElement, html, css, nothing } from 'lit';
import { property } from 'lit/decorators.js';
import { define } from '../../base/define.js';
import '../ok-qr/ok-qr.js';

// ok-receipt — Web Component PRESENTACIONAL y AISLADO del tiquet/recibo de venta (POS).
//
// No habla con ningún backend: recibe un JSON ya resuelto (prop `receipt`) y lo PINTA con
// estética de impresora térmica (80mm). Cualquier botón externo (imprimir, enviar, previsualizar)
// le pasa el objeto; el componente solo lo formatea. Reusa `ok-qr` para el QR (p.ej. VeriFactu).
//
// Uso:
//   const el = document.createElement('ok-receipt');
//   el.receipt = { business: {…}, number: '0001', lines: [...], total: 12.30, qr: '…' };
//   container.appendChild(el);

/** Cabecera del negocio (lo que va arriba del tiquet). */
export interface ReceiptBusiness {
  name: string;
  address?: string;
  /** NIF / CIF. */
  tax_id?: string;
  phone?: string;
  /** URL del logo (opcional; alternativamente usa el slot `logo`). */
  logo_url?: string;
}

/** Una línea de venta. */
export interface ReceiptLine {
  name: string;
  qty: number;
  unit_price: number;
  total: number;
  /** Nota/observación bajo la línea (opcional). */
  note?: string;
}

/** Desglose de un impuesto (p.ej. IVA 21%). */
export interface ReceiptTax {
  label: string;
  base: number;
  amount: number;
}

/** Datos del cobro. */
export interface ReceiptPayment {
  method: string;
  paid?: number;
  change?: number;
}

// Textos i18n (default inglés). Pásalos desde fuera con `.labels`.
export interface OkReceiptLabels {
  /** Mensaje cuando no hay datos de tiquet. */
  empty: string;
  /** Prefijo del teléfono del negocio (p.ej. 'Tel.'). */
  phone: string;
  /** Etiqueta del nº de tiquet. */
  receipt: string;
  /** Etiqueta de quien atiende (cajero/a). */
  servedBy: string;
  /** Etiqueta del cliente. */
  customer: string;
  /** Cabecera de columna: concepto/artículo. */
  item: string;
  /** Cabecera de columna: importe. */
  amount: string;
  /** Mensaje cuando no hay líneas. */
  noLines: string;
  /** Etiqueta del subtotal. */
  subtotal: string;
  /** Etiqueta del total. */
  total: string;
  /** Etiqueta del cambio devuelto. */
  change: string;
}

const DEFAULT_LABELS: OkReceiptLabels = {
  empty: 'No receipt data.',
  phone: 'Tel.',
  receipt: 'Receipt',
  servedBy: 'Served by',
  customer: 'Customer',
  item: 'Item',
  amount: 'Amount',
  noLines: '— No lines —',
  subtotal: 'Subtotal',
  total: 'TOTAL',
  change: 'Change',
};

/** JSON completo del tiquet. */
export interface ReceiptData {
  business: ReceiptBusiness;
  /** Nº de tiquet/ticket. */
  number: string;
  /** Fecha/hora ya formateada o ISO (se muestra tal cual si es string legible). */
  datetime?: string;
  cashier?: string;
  customer?: string;
  lines: ReceiptLine[];
  subtotal?: number;
  taxes?: ReceiptTax[];
  total: number;
  payment?: ReceiptPayment;
  /** Símbolo de moneda (def. '€'). */
  currency?: string;
  /** Mensaje de pie (gracias / leyenda legal). */
  footer?: string;
  /** Payload del QR (VeriFactu / URL de verificación). Si vacío, no se pinta QR. */
  qr?: string;
  /** Leyenda bajo el QR. */
  qr_note?: string;
}

export class OkReceipt extends LitElement {
  static styles = css`
    :host {
      /* Ancho de papel térmico estándar (80mm). Overridable vía --receipt-width. */
      --w: var(--receipt-width, 80mm);
      display: block;
      width: 100%;
    }
    .paper {
      box-sizing: border-box;
      width: var(--w);
      max-width: 100%;
      margin: 0 auto;
      padding: 4mm 3mm;
      background: #fff;
      color: #000;
      /* Monospace = look de tiquet; tabular para alinear importes. */
      font-family: 'Roboto Mono', ui-monospace, 'SFMono-Regular', Menlo, Consolas, monospace;
      font-size: 11px;
      line-height: 1.45;
      font-variant-numeric: tabular-nums;
    }
    .center { text-align: center; }
    .biz-logo { max-width: 60%; max-height: 22mm; margin: 0 auto 2mm; display: block; }
    .biz-name { font-size: 14px; font-weight: 700; letter-spacing: .04em; text-transform: uppercase; }
    .biz-meta { font-size: 10px; }
    .sep { border: none; border-top: 1px dashed #000; margin: 2mm 0; }
    .meta {
      display: flex; justify-content: space-between; gap: .5rem;
      font-size: 10px;
    }
    table { width: 100%; border-collapse: collapse; }
    th, td { padding: .3mm 0; vertical-align: top; }
    thead th { font-size: 9px; text-transform: uppercase; text-align: left; border-bottom: 1px solid #000; }
    th.num, td.num { text-align: right; white-space: nowrap; }
    .line-name { word-break: break-word; }
    .line-note { font-size: 9px; padding-left: 2mm; opacity: .8; }
    .qty-price { font-size: 9px; opacity: .85; }
    .totals { width: 100%; }
    .totals td { padding: .2mm 0; }
    .totals td.num { text-align: right; white-space: nowrap; }
    .grand td { font-size: 14px; font-weight: 700; padding-top: 1mm; }
    .pay td { font-size: 10px; }
    .footer { font-size: 10px; white-space: pre-line; }
    .qr-wrap { display: flex; flex-direction: column; align-items: center; gap: 1mm; margin-top: 2mm; }
    .qr-note { font-size: 8px; text-align: center; word-break: break-word; }
    .empty { padding: 4mm; text-align: center; color: #888; font-style: italic; }
  `;

  /** JSON del tiquet a renderizar. */
  @property({ attribute: false }) receipt?: ReceiptData;

  /** Tamaño del QR en px (lado). */
  @property({ type: Number, attribute: 'qr-size' }) qrSize = 120;

  /** Textos traducibles (merge sobre los defaults en inglés). */
  @property({ attribute: false }) labels: Partial<OkReceiptLabels> = {};

  private get t(): OkReceiptLabels {
    return { ...DEFAULT_LABELS, ...this.labels };
  }

  private cur(): string {
    return this.receipt?.currency ?? '€';
  }

  private money(n: number | undefined): string {
    return `${Number(n ?? 0).toFixed(2)} ${this.cur()}`;
  }

  render() {
    const r = this.receipt;
    if (!r) return html`<div class="paper empty">${this.t.empty}</div>`;

    return html`<div class="paper" part="paper">
      ${this.renderHeader(r)}
      <hr class="sep" />
      ${this.renderMeta(r)}
      <hr class="sep" />
      ${this.renderLines(r)}
      <hr class="sep" />
      ${this.renderTotals(r)}
      ${r.footer ? html`<hr class="sep" /><div class="center footer">${r.footer}</div>` : nothing}
      ${this.renderQr(r)}
    </div>`;
  }

  private renderHeader(r: ReceiptData) {
    const b = r.business ?? { name: '' };
    return html`<div class="center">
      ${b.logo_url
        ? html`<img class="biz-logo" src=${b.logo_url} alt=${b.name || 'logo'} />`
        : html`<slot name="logo"></slot>`}
      <div class="biz-name">${b.name}</div>
      ${b.address ? html`<div class="biz-meta">${b.address}</div>` : nothing}
      ${b.tax_id ? html`<div class="biz-meta">${b.tax_id}</div>` : nothing}
      ${b.phone ? html`<div class="biz-meta">${this.t.phone} ${b.phone}</div>` : nothing}
    </div>`;
  }

  private renderMeta(r: ReceiptData) {
    return html`<div class="meta">
        <span>${this.t.receipt}: <strong>${r.number}</strong></span>
        ${r.datetime ? html`<span>${r.datetime}</span>` : nothing}
      </div>
      ${r.cashier || r.customer
        ? html`<div class="meta">
            ${r.cashier ? html`<span>${this.t.servedBy}: ${r.cashier}</span>` : html`<span></span>`}
            ${r.customer ? html`<span>${this.t.customer}: ${r.customer}</span>` : nothing}
          </div>`
        : nothing}`;
  }

  private renderLines(r: ReceiptData) {
    const lines = r.lines ?? [];
    if (!lines.length) return html`<div class="center biz-meta">${this.t.noLines}</div>`;
    return html`<table>
      <thead>
        <tr><th>${this.t.item}</th><th class="num">${this.t.amount}</th></tr>
      </thead>
      <tbody>
        ${lines.map(
          (l) => html`<tr>
              <td class="line-name">
                <div>${l.name}</div>
                <div class="qty-price">${l.qty} × ${this.money(l.unit_price)}</div>
                ${l.note ? html`<div class="line-note">${l.note}</div>` : nothing}
              </td>
              <td class="num">${this.money(l.total)}</td>
            </tr>`,
        )}
      </tbody>
    </table>`;
  }

  private renderTotals(r: ReceiptData) {
    const taxes = r.taxes ?? [];
    return html`<table class="totals">
      ${r.subtotal != null
        ? html`<tr><td>${this.t.subtotal}</td><td class="num">${this.money(r.subtotal)}</td></tr>`
        : nothing}
      ${taxes.map(
        (t) => html`<tr><td>${t.label}</td><td class="num">${this.money(t.amount)}</td></tr>`,
      )}
      <tr class="grand"><td>${this.t.total}</td><td class="num">${this.money(r.total)}</td></tr>
      ${r.payment
        ? html`<tr class="pay"><td>${r.payment.method}</td><td class="num">${this.money(
              r.payment.paid ?? r.total,
            )}</td></tr>
            ${r.payment.change != null
              ? html`<tr class="pay"><td>${this.t.change}</td><td class="num">${this.money(
                  r.payment.change,
                )}</td></tr>`
              : nothing}`
        : nothing}
    </table>`;
  }

  private renderQr(r: ReceiptData) {
    if (!r.qr) return nothing;
    return html`<div class="qr-wrap">
      <ok-qr .value=${r.qr} .size=${this.qrSize} ec="M" color="#000" background="#fff"></ok-qr>
      ${r.qr_note ? html`<div class="qr-note">${r.qr_note}</div>` : nothing}
    </div>`;
  }
}

define('ok-receipt', OkReceipt);

declare global {
  interface HTMLElementTagNameMap {
    'ok-receipt': OkReceipt;
  }
}
