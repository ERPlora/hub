// The IRPF withholding of an invoice as apps/invoice/schemas/invoices.py takes and sends it, written by hand as
// `operations.d.ts`.

/** The rates of the closed list (apps/invoice/withholding.py). */
export type WithholdingRate = 15 | 7 | 1 | 19;

/** What the customer of a manual invoice withholds of its base; nothing, when it says none. */
export interface WithholdingIn {
  withholding_rate?: WithholdingRate;
}

/** What is withheld of a document, with its sign, and what is left to collect. */
export interface WithholdingOut {
  /** «15.00»; `null` when nothing is withheld. */
  withholding_rate: string | null;
  withholding_amount: number;
  /** The total without what is withheld. */
  payable_amount: number;
}
