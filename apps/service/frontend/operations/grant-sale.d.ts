import type { GrantOut } from '../operations';

declare module '../operations' {
  /** A voucher sold as the list of sold vouchers shows it (`service.grant.list`); the writes answer `GrantOut`. */
  interface ListedGrantOut extends GrantOut {
    /** The number Sales names the sale that charged it by (20261124-0001); null when it says no sale or the reader
     *  cannot read that sale (Sales off, or a sale not theirs to see). */
    sale_number: string | null;
  }
}

export {};
