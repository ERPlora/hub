// The notices above the till's grid (SALE-F07): how many articles cannot be sold for lack of VAT,
// with «Review the catalogue» (to Inventory's list of unconfigured products) only for whoever can fix
// it, and the reason of the last tap on a blocked tile.
import { describe, expect, it } from 'vitest';

import { click, errorFrame, MANAGER, mountSale } from '../../__tests__/mount-sale';
import { page, product } from './__tests__/fixtures';
import CatalogNotices from './CatalogNotices.vue';

const OP = 'inventory.product.list';
const FIXER = { ...MANAGER, permissions: [...MANAGER.permissions, 'inventory.change_product'] };

async function setup(options: { props?: Record<string, unknown>; session?: typeof MANAGER; locale?: 'en' | 'es' } = {}) {
  const m = await mountSale(CatalogNotices, { props: { tapNotice: null, ...options.props }, session: options.session, locale: options.locale });
  await m.live();
  return m;
}

describe('CatalogNotices', () => {
  it('counts the articles without VAT on the server: one row is enough, the total says how many', async () => {
    const m = await setup();
    expect(m.params(OP)).toEqual([{ needs_tax_setup: true, is_active: true, limit: 1, offset: 0 }]);
    await m.result(OP, page([], 0, 1));
    expect(m.find('pos-catalog-health').exists()).toBe(false);
  });

  it('says how many cannot be sold, in one sentence and in the reader’s language', async () => {
    const one = await setup({ locale: 'es' });
    await one.result(OP, page([product({ needs_tax_setup: true })], 1, 1));
    expect(one.find('pos-catalog-health').text()).toBe('1 artículo no se puede vender: le falta configurar el IVA.');
    const many = await setup();
    await many.result(OP, page([product({ needs_tax_setup: true })], 3, 1));
    expect(many.find('pos-catalog-health').text()).toBe('3 items cannot be sold: their VAT is not set up.');
    expect(many.find('pos-catalog-health').attributes('role')).toBe('status');
  });

  it('only whoever can change products gets «Review the catalogue», which opens the unconfigured ones', async () => {
    const seller = await setup();
    await seller.result(OP, page([product()], 2, 1));
    expect(seller.find('pos-catalog-health-fix').exists()).toBe(false);
    const fixer = await setup({ session: FIXER });
    await fixer.result(OP, page([product()], 2, 1));
    const fix = fixer.find('pos-catalog-health-fix');
    expect(fix.text()).toBe('Review the catalogue');
    await click(fix.element);
    expect(fixer.router.currentRoute.value.fullPath).toBe('/inventory/products?status=unconfigured');
  });

  it('says nothing about the catalogue when it cannot be counted (Inventory off): the grid says it', async () => {
    const m = await setup();
    m.net.lastStream().push(errorFrame(m.subId(OP), 'app_inactive'));
    await m.reopen();
    expect(m.find('pos-catalog-health').exists()).toBe(false);
  });

  it('shows the reason of the last blocked tap where the cashier is looking', async () => {
    const m = await setup({ props: { tapNotice: 'Cannot be sold: no tax category. VAT needs to be set up.' } });
    const notice = m.find('pos-tap-notice');
    expect(notice.text()).toBe('Cannot be sold: no tax category. VAT needs to be set up.');
    expect(notice.attributes('role')).toBe('status');
  });
});
