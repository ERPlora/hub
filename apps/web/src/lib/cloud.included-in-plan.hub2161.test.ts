// hub#2161: the SaaS catalog now says explicitly whether an app comes with the hub plan
// (`included_in_plan`, saas#2324). The hub reads that field first and only deduces it from zero
// prices when the catalog does not send it (an older store), so hub and erplora.com panel never
// disagree about the same app.
import { describe, expect, it } from 'vitest';

import { catalogPrice } from './apps-catalog';
import { normalizeMarketplaceModule } from './cloud';

const ZERO_TIERS_SUBSCRIPTION = {
  module_id: 'whatsapp_inbox',
  name: 'WhatsApp Inbox',
  module_type: 'subscription',
  price: '0.00',
  subscription_price_monthly: '0.00',
  subscription_interval: 'month',
  price_from: null,
  is_free: false,
  tiers: [
    { slug: 'free', price: '0.00', interval: 'month' },
    { slug: 'pro', price: '0.00', interval: 'month' },
  ],
};

describe('normalizeMarketplaceModule — explicit included_in_plan (hub#2161)', () => {
  it('included_in_plan: false wins over zero-priced tiers', () => {
    const m = normalizeMarketplaceModule({ ...ZERO_TIERS_SUBSCRIPTION, included_in_plan: false });
    expect(m.includedInPlan).toBe(false);
    expect(catalogPrice(m)).not.toEqual({ kind: 'included_in_plan' });
  });

  it('included_in_plan: true wins even when the tiers would not let the hub deduce it', () => {
    const m = normalizeMarketplaceModule({
      module_id: 'whatsapp_inbox',
      module_type: 'subscription',
      is_free: false,
      tiers: [],
      included_in_plan: true,
    });
    expect(m.includedInPlan).toBe(true);
    expect(catalogPrice(m)).toEqual({ kind: 'included_in_plan' });
  });

  it('an older store without the field keeps the deduction from zero prices', () => {
    const m = normalizeMarketplaceModule(ZERO_TIERS_SUBSCRIPTION);
    expect(m.includedInPlan).toBe(true);
  });

  it('a null field is ignored and the deduction from zero prices applies', () => {
    const m = normalizeMarketplaceModule({ ...ZERO_TIERS_SUBSCRIPTION, included_in_plan: null });
    expect(m.includedInPlan).toBe(true);
  });

  it('a non-boolean value never turns a sold app into an included one', () => {
    const m = normalizeMarketplaceModule({
      ...ZERO_TIERS_SUBSCRIPTION,
      tiers: [{ slug: 'pro', price: '9.99' }],
      included_in_plan: 'true',
    });
    expect(m.includedInPlan).toBe(false);
  });
});
