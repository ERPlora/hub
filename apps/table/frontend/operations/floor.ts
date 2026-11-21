declare module '../operations' {
  interface TableOut {
    /** What is left to charge on all its open checks, in cents of the business's currency, while occupied (0 until
     *  something is ordered); null when nobody sits at it. */
    amount: number | null;
  }
}

export {};
