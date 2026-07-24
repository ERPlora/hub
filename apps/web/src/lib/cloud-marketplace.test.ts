import { describe, expect, it } from 'vitest';

import { normalizeMarketplaceModule } from './cloud';

describe('marketplace module normalization', () => {
  it('uses the real module id, category, version and free state from SaaS', () => {
    expect(normalizeMarketplaceModule({
      id: 362,
      module_id: 'inventory',
      name: 'Inventory',
      description: 'Stock and movements',
      version: '2.4.0',
      module_type: 'free',
      is_free: true,
      functional_unit_name: 'Inventory',
      is_active: true,
    })).toMatchObject({
      id: 'inventory',
      name: 'Inventory',
      category: 'Inventory',
      version: '2.4.0',
      isFree: true,
      priceAmount: null,
      available: true,
    });
  });

  it('uses the lowest real SaaS subscription price and interval', () => {
    expect(normalizeMarketplaceModule({
      module_id: 'whatsapp_inbox',
      name: 'WhatsApp Inbox',
      module_type: 'subscription',
      price: '0.00',
      subscription_price_monthly: '0.00',
      price_from: '14.99',
      subscription_interval: 'month',
      category: 'Communication',
      is_active: true,
    })).toMatchObject({
      id: 'whatsapp_inbox',
      isFree: false,
      priceAmount: '14.99',
      priceInterval: 'month',
      category: 'Communication',
    });
  });

  it('does not turn missing paid pricing into a fabricated amount', () => {
    expect(normalizeMarketplaceModule({
      module_id: 'future_module',
      module_type: 'subscription',
      is_coming_soon: true,
    })).toMatchObject({
      isFree: false,
      priceAmount: null,
      available: false,
    });
  });
});
