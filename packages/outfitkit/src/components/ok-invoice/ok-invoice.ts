import { LitElement, html, css, nothing } from 'lit';
import { property } from 'lit/decorators.js';
import { define } from '../../base/define.js';
import '../ok-qr/ok-qr.js';

// ok-invoice — Web Component PRESENTACIONAL y AISLADO de la FACTURA A4 (documento fiscal completo).
//
// Hermano de `ok-receipt` (tiquet térmico 80mm): mismo principio, distinto FORMATO. No habla con
// ningún backend: recibe un JSON ya resuelto (prop `invoice`) y lo pinta como una factura A4
// profesional (emisor + receptor con datos fiscales, líneas con descuento/impuesto, resumen de
// impuestos por tipo, totales, condiciones de pago, pie legal y QR opcional — reusa `ok-qr`).
//
// Uso:
//   const el = document.createElement('ok-invoice');
//   el.invoice = { issuer: {…}, customer: {…}, number: 'F2026/0001', lines: [...], total: 121 };
//   container.appendChild(el);

/** Parte fiscal (emisor o receptor). */
export interface InvoiceParty {
  name: string;
  /** NIF / CIF / VAT. */
  tax_id?: string;
  address?: string;
  city?: string;
  postal_code?: string;
  country?: string;
  email?: string;
  phone?: string;
}

/** Una línea de factura. */
export interface InvoiceLine {
  description: string;
  qty: number;
  unit_price: number;
  /** % de descuento sobre la línea (opcional). */
  discount_percent?: number;
  /** % de impuesto aplicado a la línea (informativo; el cálculo va en `taxes`). */
  tax_rate?: number;
  /** Importe de la línea (neto tras descuento, sin impuesto). */
  total: number;
}

/** Resumen de un tipo impositivo. */
export interface InvoiceTaxLine {
  /** Etiqueta (p.ej. "IVA 21%"). */
  label: string;
  /** Tipo en % (p.ej. 21). */
  rate?: number;
  base: number;
  amount: number;
}

// Textos i18n (default inglés). Pásalos desde fuera con `.labels`.
export interface OkInvoiceLabels {
  /** Mensaje cuando no hay datos de factura. */
  empty: string;
  /** Título del documento (cabecera derecha). */
  invoice: string;
  /** Etiqueta del nº de factura. */
  number: string;
  /** Etiqueta de la fecha de emisión. */
  date: string;
  /** Etiqueta de la fecha de vencimiento. */
  dueDate: string;
  /** Cabecera del bloque receptor. */
  billTo: string;
  /** Cabecera de columna: descripción. */
  description: string;
  /** Cabecera de columna: cantidad. */
  qty: string;
  /** Cabecera de columna: precio unitario. */
  price: string;
  /** Cabecera de columna: descuento. */
  discount: string;
  /** Cabecera de columna: impuesto. */
  tax: string;
  /** Cabecera de columna: importe de línea. */
  amount: string;
  /** Mensaje cuando no hay líneas. */
  noLines: string;
  /** Etiqueta de la base imponible. */
  taxBase: string;
  /** Etiqueta del descuento total. */
  discountTotal: string;
  /** Etiqueta del total. */
  total: string;
  /** Cabecera de la forma de pago. */
  paymentMethod: string;
}

const DEFAULT_LABELS: OkInvoiceLabels = {
  empty: 'No invoice data.',
  invoice: 'Invoice',
  number: 'No.',
  date: 'Date',
  dueDate: 'Due date',
  billTo: 'Bill to',
  description: 'Description',
  qty: 'Qty',
  price: 'Price',
  discount: 'Disc.',
  tax: 'Tax',
  amount: 'Amount',
  noLines: '— No lines —',
  taxBase: 'Tax base',
  discountTotal: 'Discount',
  total: 'TOTAL',
  paymentMethod: 'Payment method',
};

/** JSON completo de la factura. */
export interface InvoiceData {
  /** Emisor (con logo opcional). */
  issuer: InvoiceParty & { logo_url?: string };
  /** Receptor / cliente. */
  customer: InvoiceParty;
  /** Tipo fiscal (p.ej. 'F1' completa, 'F2' simplificada, 'R1' rectificativa). */
  type?: string;
  /** Nº de factura (serie + número). */
  number: string;
  /** Fecha de emisión (ya formateada o ISO legible). */
  issue_date: string;
  /** Fecha de vencimiento (opcional). */
  due_date?: string;
  lines: InvoiceLine[];
  /** Base imponible total (suma de netos). */
  subtotal: number;
  /** Descuento total agregado (opcional). */
  discount_total?: number;
  /** Resumen de impuestos por tipo. */
  taxes: InvoiceTaxLine[];
  /** Suma de impuestos. */
  tax_total: number;
  /** Total a pagar. */
  total: number;
  /** Símbolo de moneda (def. '€'). */
  currency?: string;
  /** Método de pago (p.ej. "Transferencia", "Tarjeta"). */
  payment_method?: string;
  /** Condiciones de pago / IBAN / vencimiento textual. */
  payment_terms?: string;
  /** Notas libres. */
  notes?: string;
  /** Pie legal (LOPD, registro mercantil, etc.). */
  footer?: string;
  /** Payload del QR (VeriFactu / verificación). Si vacío, no se pinta. */
  qr?: string;
  /** Leyenda bajo el QR. */
  qr_note?: string;
}

export class OkInvoice extends LitElement {
  static styles = css`
    :host {
      --ink: var(--ok-text, var(--ion-text-color, #1c1b18));
      --muted: #6b6b6b;
      --rule: #d9d6cf;
      --accent: var(--ok-color-primary, var(--ion-color-primary, #0091ce));
      --soft: color-mix(in srgb, var(--accent) 8%, #fff);
      display: block;
      width: 100%;
    }
    .sheet {
      box-sizing: border-box;
      /* A4: ancho de papel. Overridable vía --invoice-width. */
      width: var(--invoice-width, 210mm);
      max-width: 100%;
      margin: 0 auto;
      padding: 16mm 14mm;
      background: #fff;
      color: var(--ink);
      font-family: var(--ok-font, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif);
      font-size: 12px;
      line-height: 1.5;
    }
    /* Cabecera: emisor a la izquierda, bloque "FACTURA" a la derecha. */
    .top { display: flex; justify-content: space-between; gap: 2rem; align-items: flex-start; }
    .issuer-logo { max-height: 18mm; max-width: 55mm; margin-bottom: .5rem; display: block; }
    .issuer-name { font-size: 15px; font-weight: 700; }
    .issuer-meta, .party-meta { color: var(--muted); font-size: 11px; white-space: pre-line; }
    .doc { text-align: right; min-width: 48mm; }
    .doc-title { font-size: 24px; font-weight: 800; letter-spacing: .06em; color: var(--accent); text-transform: uppercase; }
    .doc-type { font-size: 10px; color: var(--muted); text-transform: uppercase; letter-spacing: .08em; }
    .doc-grid { margin-top: .6rem; display: grid; grid-template-columns: auto auto; gap: .1rem .8rem; justify-content: end; font-size: 11px; }
    .doc-grid .k { color: var(--muted); text-align: right; }
    .doc-grid .v { font-weight: 600; text-align: right; }
    /* Bloque receptor. */
    .bill-to { margin: 9mm 0 6mm; padding: 3mm 4mm; background: var(--soft); border-radius: 8px; }
    .bill-to .label { font-size: 9px; text-transform: uppercase; letter-spacing: .08em; color: var(--muted); }
    .bill-to .name { font-weight: 700; font-size: 13px; }
    /* Tabla de líneas. */
    table.lines { width: 100%; border-collapse: collapse; margin-top: 2mm; }
    table.lines thead th {
      font-size: 9px; text-transform: uppercase; letter-spacing: .05em; color: var(--muted);
      text-align: left; padding: 2mm 2mm; border-bottom: 1.5px solid var(--ink);
    }
    table.lines tbody td { padding: 2mm 2mm; border-bottom: 1px solid var(--rule); vertical-align: top; }
    .num { text-align: right; white-space: nowrap; }
    .desc { width: 42%; }
    /* Resumen de totales (derecha). */
    .summary { display: flex; justify-content: flex-end; margin-top: 4mm; }
    .summary table { border-collapse: collapse; min-width: 70mm; }
    .summary td { padding: 1mm 2mm; }
    .summary td.num { text-align: right; white-space: nowrap; }
    .summary .grand td { font-size: 15px; font-weight: 800; border-top: 1.5px solid var(--ink); padding-top: 2mm; }
    .summary .grand td.num { color: var(--accent); }
    .muted { color: var(--muted); }
    /* Pie: pago, notas, QR. */
    .foot { margin-top: 8mm; display: flex; justify-content: space-between; gap: 2rem; align-items: flex-start; }
    .pay-box { font-size: 11px; }
    .pay-box .h { font-size: 9px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); }
    .qr-wrap { display: flex; flex-direction: column; align-items: center; gap: 1mm; }
    .qr-note { font-size: 8px; max-width: 36mm; text-align: center; color: var(--muted); word-break: break-word; }
    .legal { margin-top: 8mm; padding-top: 3mm; border-top: 1px solid var(--rule); font-size: 9px; color: var(--muted); white-space: pre-line; text-align: center; }
    .empty { padding: 12mm; text-align: center; color: #999; font-style: italic; }
  `;

  /** JSON de la factura a renderizar. */
  @property({ attribute: false }) invoice?: InvoiceData;

  /** Tamaño del QR en px (lado). */
  @property({ type: Number, attribute: 'qr-size' }) qrSize = 96;

  /** Textos traducibles (merge sobre los defaults en inglés). */
  @property({ attribute: false }) labels: Partial<OkInvoiceLabels> = {};

  private get t(): OkInvoiceLabels {
    return { ...DEFAULT_LABELS, ...this.labels };
  }

  private cur(): string {
    return this.invoice?.currency ?? '€';
  }

  private money(n: number | undefined): string {
    return `${Number(n ?? 0).toFixed(2)} ${this.cur()}`;
  }

  render() {
    const inv = this.invoice;
    if (!inv) return html`<div class="sheet empty">${this.t.empty}</div>`;

    return html`<div class="sheet" part="sheet">
      ${this.renderTop(inv)}
      ${this.renderBillTo(inv)}
      ${this.renderLines(inv)}
      ${this.renderSummary(inv)}
      ${this.renderFoot(inv)}
      ${inv.footer ? html`<div class="legal">${inv.footer}</div>` : nothing}
    </div>`;
  }

  private party(p: InvoiceParty) {
    const loc = [p.postal_code, p.city].filter(Boolean).join(' ');
    const lines = [p.address, loc, p.country, p.tax_id, p.email, p.phone].filter(Boolean);
    return html`${lines.map((l) => html`<div>${l}</div>`)}`;
  }

  private renderTop(inv: InvoiceData) {
    const iss = inv.issuer ?? { name: '' };
    return html`<div class="top">
      <div>
        ${iss.logo_url ? html`<img class="issuer-logo" src=${iss.logo_url} alt=${iss.name || 'logo'} />` : nothing}
        <div class="issuer-name">${iss.name}</div>
        <div class="issuer-meta">${this.party(iss)}</div>
      </div>
      <div class="doc">
        <div class="doc-title">${this.t.invoice}</div>
        ${inv.type ? html`<div class="doc-type">${inv.type}</div>` : nothing}
        <div class="doc-grid">
          <span class="k">${this.t.number}</span><span class="v">${inv.number}</span>
          <span class="k">${this.t.date}</span><span class="v">${inv.issue_date}</span>
          ${inv.due_date ? html`<span class="k">${this.t.dueDate}</span><span class="v">${inv.due_date}</span>` : nothing}
        </div>
      </div>
    </div>`;
  }

  private renderBillTo(inv: InvoiceData) {
    const c = inv.customer;
    if (!c) return nothing;
    return html`<div class="bill-to">
      <div class="label">${this.t.billTo}</div>
      <div class="name">${c.name}</div>
      <div class="party-meta">${this.party(c)}</div>
    </div>`;
  }

  private renderLines(inv: InvoiceData) {
    const lines = inv.lines ?? [];
    const hasDisc = lines.some((l) => l.discount_percent);
    const hasTax = lines.some((l) => l.tax_rate != null);
    return html`<table class="lines">
      <thead>
        <tr>
          <th class="desc">${this.t.description}</th>
          <th class="num">${this.t.qty}</th>
          <th class="num">${this.t.price}</th>
          ${hasDisc ? html`<th class="num">${this.t.discount}</th>` : nothing}
          ${hasTax ? html`<th class="num">${this.t.tax}</th>` : nothing}
          <th class="num">${this.t.amount}</th>
        </tr>
      </thead>
      <tbody>
        ${lines.length
          ? lines.map(
              (l) => html`<tr>
                <td class="desc">${l.description}</td>
                <td class="num">${l.qty}</td>
                <td class="num">${this.money(l.unit_price)}</td>
                ${hasDisc ? html`<td class="num">${l.discount_percent ? `${l.discount_percent}%` : '—'}</td>` : nothing}
                ${hasTax ? html`<td class="num">${l.tax_rate != null ? `${l.tax_rate}%` : '—'}</td>` : nothing}
                <td class="num">${this.money(l.total)}</td>
              </tr>`,
            )
          : html`<tr><td colspan="6" class="muted" style="text-align:center;padding:6mm">${this.t.noLines}</td></tr>`}
      </tbody>
    </table>`;
  }

  private renderSummary(inv: InvoiceData) {
    const taxes = inv.taxes ?? [];
    return html`<div class="summary">
      <table>
        <tr><td class="muted">${this.t.taxBase}</td><td class="num">${this.money(inv.subtotal)}</td></tr>
        ${inv.discount_total
          ? html`<tr><td class="muted">${this.t.discountTotal}</td><td class="num">−${this.money(inv.discount_total)}</td></tr>`
          : nothing}
        ${taxes.map(
          (t) => html`<tr><td class="muted">${t.label}${t.base != null ? html` <span class="muted">(${this.money(t.base)})</span>` : nothing}</td><td class="num">${this.money(t.amount)}</td></tr>`,
        )}
        <tr class="grand"><td>${this.t.total}</td><td class="num">${this.money(inv.total)}</td></tr>
      </table>
    </div>`;
  }

  private renderFoot(inv: InvoiceData) {
    const hasPay = inv.payment_method || inv.payment_terms || inv.notes;
    if (!hasPay && !inv.qr) return nothing;
    return html`<div class="foot">
      <div class="pay-box">
        ${inv.payment_method ? html`<div class="h">${this.t.paymentMethod}</div><div>${inv.payment_method}</div>` : nothing}
        ${inv.payment_terms ? html`<div style="margin-top:2mm" class="muted">${inv.payment_terms}</div>` : nothing}
        ${inv.notes ? html`<div style="margin-top:3mm">${inv.notes}</div>` : nothing}
      </div>
      ${inv.qr
        ? html`<div class="qr-wrap">
            <ok-qr .value=${inv.qr} .size=${this.qrSize} ec="M"></ok-qr>
            ${inv.qr_note ? html`<div class="qr-note">${inv.qr_note}</div>` : nothing}
          </div>`
        : nothing}
    </div>`;
  }
}

define('ok-invoice', OkInvoice);

declare global {
  interface HTMLElementTagNameMap {
    'ok-invoice': OkInvoice;
  }
}
