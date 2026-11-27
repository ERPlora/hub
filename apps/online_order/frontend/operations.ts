// Types of Online orders' operations for the SDK (`useLive`, `useCommand`), from apps/online_order/schemas.py. Written by
// hand: nothing generates them from `/api/openapi.json`. Keep them in step with schemas.py and with
// `frontend/generated/operations.json`. A table is said as Tables says it (`TableRefIn`).
import type { TableRefIn } from '../../table/frontend/operations';

export interface TableCodeListIn {
  limit?: number;
  offset?: number;
}

/** A table, in the floor plan's order, with the code its QR carries: none until its QR is generated the first time. */
export interface TableCodeOut {
  table_id: string;
  /** Its number with its zone, as the floor plan names it: «5 (Terrace)». */
  table: string;
  number: string;
  zone_name: string | null;
  code: string | null;
  /** The address of the table's page, which its QR opens. */
  url: string | null;
  issued_at: string | null;
}

export interface TableCodePage {
  rows: TableCodeOut[];
  total: number;
  limit: number;
  offset: number;
}

/** The table's page names its table by the code its QR carries. */
export interface PublicCodeIn {
  code: string;
}

export interface PublicOptionsIn extends PublicCodeIn {
  product_id: string;
}

/** A dish of the menu, a product of Inventory; prices in the currency's minor unit. */
export interface MenuItemOut {
  id: string;
  name: string;
  description: string;
  price: number;
  /** Where its photo is served; empty: it has none. */
  image_url: string;
  allergens: string[];
}

export interface MenuGroupOut {
  /** The category's name; empty for the dishes in none. */
  name: string;
  items: MenuItemOut[];
}

/** One of the things a customer picks: an option of a dish or a dish of a set menu's course. */
export interface ChoiceOut {
  /** What the order names when it is picked. */
  id: string;
  name: string;
  price_delta: number;
  allergens: string[];
}

export interface MenuCourseOut {
  id: string;
  name: string;
  min_choices: number;
  max_choices: number;
  allow_repeat: boolean;
  choices: ChoiceOut[];
}

export interface MenuComboOut {
  id: string;
  name: string;
  price: number;
  image_url: string;
  courses: MenuCourseOut[];
}

export interface PublicMenuOut {
  business_name: string;
  table_number: string;
  zone_name: string | null;
  groups: MenuGroupOut[];
  combos: MenuComboOut[];
}

export interface OptionGroupOut {
  id: string;
  name: string;
  min_choices: number;
  /** 0 = no ceiling. */
  max_choices: number;
  allow_repeat: boolean;
  options: ChoiceOut[];
}

export interface PublicOptionsOut {
  product_id: string;
  groups: OptionGroupOut[];
}

/** A dish with its options, or a set menu with its dishes, by their ids: never a price, which is the server's. */
export interface SendLineIn {
  product_id?: string;
  option_ids?: string[];
  combo_id?: string;
  choices?: { option_id: string; quantity: number }[];
  quantity: number;
  notes: string;
}

export interface PublicSendIn extends PublicCodeIn {
  lines: SendLineIn[];
}

export interface PublicSentOut {
  id: string;
  /** `pending`: it waits for the staff to confirm it. */
  status: string;
  total: number;
}

declare module '@erplora/ui/sdk' {
  interface Operations {
    'online_order.qr_code.list': { input: TableCodeListIn; output: TableCodePage };
    'online_order.qr_code.regenerate': { input: TableRefIn; output: TableCodeOut };
    'online_order.public.menu': { input: PublicCodeIn; output: PublicMenuOut };
    'online_order.public.options': { input: PublicOptionsIn; output: PublicOptionsOut };
    'online_order.public.send': { input: PublicSendIn; output: PublicSentOut };
  }
}
