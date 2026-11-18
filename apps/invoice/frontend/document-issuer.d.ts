// The issuer of an `InvoiceOut`, as apps/invoice/schemas/document_issuer.py sends it: the copy the invoice keeps.
export interface DocumentIssuerOut {
  issuer_name: string;
  /** The tax ID as kept: the one VeriFactu declares and the QR carries. */
  issuer_tax_id: string;
  /** What the document prints: the EU VAT number (ESB27593136) of an issuer in the ROI, its tax ID otherwise. */
  issuer_vat_number: string;
  issuer_address: string;
  issuer_country: string;
}
