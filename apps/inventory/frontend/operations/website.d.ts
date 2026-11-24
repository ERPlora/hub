declare module '../operations' {
  interface SaleProductOut {
    /** INVENTORY-F36: off, the website's catalog leaves it out; the till still sells it. */
    show_on_website: boolean;
  }
  interface ProductIn {
    /** On unless sent off. */
    show_on_website?: boolean;
  }
  interface ProductPatchIn {
    show_on_website?: boolean;
  }
  interface ForSaleListIn {
    /** Only the ones shown (true) or hidden (false) on the website; the till asks none. */
    show_on_website?: boolean;
  }
}

export {};
