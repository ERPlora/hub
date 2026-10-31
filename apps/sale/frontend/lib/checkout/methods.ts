// The payment methods the charge sheet offers (SALE-F02, F03, F37). Which ones may charge today is the
// server's (`allowed`: the till settings «Allow cash / card / transfer»); the legal cash limit too
// (`cash_limit` of `sale.checkout.preview`): here they are only ordered, painted and picked.
// Icons: registered ones only, the current product's. Its `ellipsis-horizontal-circle-outline` and Bizum's
// brand mark wait in apps/sale/UI-REQUESTS.md («Cobro»).
import type { PaymentMethodOut } from '../../operations';

type MethodLike = Pick<PaymentMethodOut, 'type' | 'name'>;

export const isCash = (method: Pick<PaymentMethodOut, 'type'> | undefined): boolean => method?.type === 'cash';

/** The methods that may charge today, cash first and the rest as the server orders them. */
export function chargeableMethods(rows: readonly PaymentMethodOut[]): PaymentMethodOut[] {
  const allowed = rows.filter((m) => m.allowed);
  return [...allowed.filter(isCash), ...allowed.filter((m) => !isCash(m))];
}

const BY_TYPE: Record<string, string> = {
  cash: 'ion:cash-outline',
  card: 'ion:card-outline',
  transfer: 'ion:swap-horizontal-outline',
};

const BY_NAME: [RegExp, string][] = [
  [/bizum|m[óo]vil|mobile|apple pay|google pay/i, 'ion:phone-portrait-outline'],
  // A voucher before a gift, as the current product: a «vale regalo» is a voucher.
  [/vale|cheque|ticket|voucher/i, 'ion:ticket-outline'],
  [/regalo|gift/i, 'ion:gift-outline'],
];

const FALLBACK = 'ion:wallet-outline';

/** The icon of a method: by its type, and an «other» one by its name (Bizum, a voucher…). */
export function methodIcon(method: MethodLike): string {
  if (BY_TYPE[method.type]) return BY_TYPE[method.type];
  return BY_NAME.find(([pattern]) => pattern.test(method.name))?.[1] ?? FALLBACK;
}

/** From the limit on (the limit itself included), no cash at all, not even part of a split. */
export function cashOverLimit(limit: number | null | undefined, total: number | undefined): boolean {
  return typeof limit === 'number' && typeof total === 'number' && total >= limit;
}

/** The method the sheet starts on: the first that can charge this total (cash, unless over its limit). */
export function defaultMethod<T extends Pick<PaymentMethodOut, 'type'>>(methods: readonly T[], cashOff: boolean): T | undefined {
  return methods.find((m) => !(cashOff && isCash(m))) ?? methods[0];
}
