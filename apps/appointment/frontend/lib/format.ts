// The money of the diary is the business's (BASE-F50): its country's currency with the decimals the server counts it
// in, as `base.business.get` says it (`useBusinessMoney`, the platform's), never a fixed euro nor the browser's Intl
// decimals. Until the business answers an amount is a figure without a symbol. An amount is written with the
// platform's `formatMoney`; pages never format by hand.
export type { Money } from '../../../../base/frontend/lib/home';
export { formatMoney, useBusinessMoney } from '../../../../base/frontend/lib/money';
