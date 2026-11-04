// The money of the diary: whole cents of euros, until it follows the business's currency (hub#577). An amount is written
// with the platform's `formatMoney` (`@erplora/ui/components`) in this money; pages never format by hand.
import type { Money } from '@erplora/ui/components';

export const APPOINTMENT_MONEY: Money = { currency: 'EUR', decimals: 2 };
