declare module '../operations' {
  interface SaleOut {
    /** The code its ticket prints under a QR of its own, to ask for the full invoice; none for a full invoice or
     *  without Invoicing. */
    receipt_code: string | null;
  }
}

export {};
