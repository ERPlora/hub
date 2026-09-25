// hub#2072: a paid app card in Apps → Paid read «€/mes» with no amount. WhatsApp is an ERPlora
// premium module that comes only with the hub plan (ADR-0474): the catalog sends it as a
// subscription whose tiers all cost 0.00, so there is no amount to print — and the card printed the
// unit alone. A price line is either an amount with its unit, or words that say why there is none.
import { describe, expect, it } from 'vitest';

import { catalogPrice } from './apps-catalog';
import { normalizeMarketplaceModule } from './cloud';

const WHATSAPP_AS_SERVED = {
  module_id: 'whatsapp_inbox',
  name: 'WhatsApp Inbox',
  module_type: 'subscription',
  tier: 'premium',
  price: '0.00',
  subscription_price_monthly: '0.00',
  subscription_interval: 'month',
  price_from: null,
  is_free: false,
  tiers: [
    { slug: 'free', price: '0.00', interval: 'month' },
    { slug: 'basic', price: '0.00', interval: 'month' },
    { slug: 'pro', price: '0.00', interval: 'month' },
    { slug: 'enterprise', price: '0.00', interval: 'month' },
  ],
};

describe('catalogPrice (hub#2072)', () => {
  it('a paid module whose every tier costs nothing is included in the hub plan, not «€/month»', () => {
    const m = normalizeMarketplaceModule(WHATSAPP_AS_SERVED);
    expect(m.includedInPlan).toBe(true);
    expect(catalogPrice(m)).toEqual({ kind: 'included_in_plan' });
  });

  it('a monthly subscription with a real amount keeps its amount and unit', () => {
    const m = normalizeMarketplaceModule({ ...WHATSAPP_AS_SERVED, price_from: '14.99' });
    expect(m.includedInPlan).toBe(false);
    expect(catalogPrice(m)).toEqual({ kind: 'monthly', amount: '14.99' });
  });

  it('a tier with a price means the module is sold, so it is not included in the plan', () => {
    const m = normalizeMarketplaceModule({
      ...WHATSAPP_AS_SERVED,
      tiers: [{ slug: 'free', price: '0.00' }, { slug: 'pro', price: '9.99' }],
    });
    expect(m.includedInPlan).toBe(false);
  });

  it('a yearly subscription keeps its amount and unit', () => {
    const m = normalizeMarketplaceModule({ ...WHATSAPP_AS_SERVED, price_from: '99', subscription_interval: 'year' });
    expect(catalogPrice(m)).toEqual({ kind: 'yearly', amount: '99' });
  });

  it('a paid subscription with no amount and no tiers never prints the unit alone', () => {
    const m = normalizeMarketplaceModule({ module_id: 'third_party', module_type: 'subscription', subscription_interval: 'month' });
    expect(m.includedInPlan).toBe(false);
    expect(catalogPrice(m)).toEqual({ kind: 'on_request' });
  });

  it('a yearly subscription with no amount never prints the unit alone either', () => {
    const m = normalizeMarketplaceModule({ module_id: 'third_party', module_type: 'subscription', subscription_interval: 'year' });
    expect(catalogPrice(m)).toEqual({ kind: 'on_request' });
  });

  it('a one-time price keeps its amount', () => {
    const m = normalizeMarketplaceModule({ module_id: 'x', module_type: 'one_time', price: '49' });
    expect(catalogPrice(m)).toEqual({ kind: 'one_time', amount: '49' });
  });

  it('a free module is free, whatever its tiers say', () => {
    const m = normalizeMarketplaceModule({ module_id: 'inventory', module_type: 'free', is_free: true, tiers: [] });
    expect(m.includedInPlan).toBe(false);
    expect(catalogPrice(m)).toEqual({ kind: 'free' });
  });

  it('a label the SaaS writes itself wins over anything the hub would compose', () => {
    const m = normalizeMarketplaceModule({ ...WHATSAPP_AS_SERVED, price_label: 'Incluido en Standard' });
    expect(catalogPrice(m)).toEqual({ kind: 'label', label: 'Incluido en Standard' });
  });
});
