declare module '../operations' {
  interface MovementOut {
    /** The number Sales names the sale by (20261123-0003); null when the reader cannot read that sale (Sales off, or
     *  a sale not theirs to see). */
    sale_number: string | null;
  }
}

export {};
