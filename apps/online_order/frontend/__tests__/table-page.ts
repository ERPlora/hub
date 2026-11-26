// Test data of the table's page, shared by its components' tests: the visitor without a session, the business's money
// and a dish's group of sauces as `online_order.public.options` answers it.
import type { SessionMe } from '@erplora/ui/shell';

import type { OptionGroupOut } from '../operations';

export const VISITOR: SessionMe = { user: null, permissions: [], menu: [], apps: [], language: 'en' };
export const MONEY = { currency: 'EUR', decimals: 2 };
export const SAUCES: OptionGroupOut = {
  id: 'g1',
  name: 'Sauces',
  min_choices: 0,
  max_choices: 2,
  allow_repeat: false,
  options: [
    { id: 'o1', name: 'Aioli', price_delta: 50, allergens: ['egg'] },
    { id: 'o2', name: 'Brava', price_delta: 0, allergens: [] },
  ],
};
