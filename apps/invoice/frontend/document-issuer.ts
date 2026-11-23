// The issuer as apps/invoice/schemas/document_issuer.py sends it: the one of an `InvoiceOut`, from the copy the invoice
// keeps, and what `IssuerIn` and `IssuerOut` say of the ROI.
export interface DocumentIssuerOut {
  issuer_name: string;
  /** The tax ID as kept: the one VeriFactu declares and the QR carries. */
  issuer_tax_id: string;
  /** What the document prints: the EU VAT number (ESB27593136) of an issuer in the ROI, its tax ID otherwise. */
  issuer_vat_number: string;
  issuer_address: string;
  issuer_country: string;
}

/** Whether the business is registered for intra-EU operations (ROI): its documents print its EU VAT number. */
export interface IntraEuOperatorIn {
  intra_eu_operator?: boolean;
}

export interface IntraEuOperatorOut {
  intra_eu_operator: boolean;
  /** The tax ID as the documents print it: ESB12345674 while in the ROI, the tax ID as kept otherwise. */
  vat_number: string;
}
