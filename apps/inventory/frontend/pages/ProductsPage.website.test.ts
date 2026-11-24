import { afterEach, describe, expect, it } from 'vitest';

import { EMPLOYEE, ok, page, product, refusal } from '../__tests__/mount-inventory';
import { api, setup } from '../__tests__/products-page';

afterEach(() => {
  document.body.innerHTML = '';
});

const SHOWN = product();
const HIDDEN = product({ show_on_website: false });

describe('ProductsPage: show on website (INVENTORY-F36)', () => {
  it('offers «Hide from website» on a product shown there and «Show on website» on a hidden one', async () => {
    const s = await setup();
    await s.show(page([SHOWN], 1));
    const actions = s.prop<Array<{ id: string; hidden?: (row: unknown) => boolean; menuOnly?: boolean }>>('actions');

    expect(actions.filter((a) => a.id.endsWith('website')).map((a) => [a.id, a.hidden?.(SHOWN), a.hidden?.(HIDDEN), a.menuOnly])).toEqual([
      ['hide_from_website', false, true, true],
      ['show_on_website', true, false, true],
    ]);
  });

  it('changes it from the list without opening the product, and a refusal is said above the table', async () => {
    const s = await setup({}, () => ok(HIDDEN));
    await s.show(page([SHOWN], 1));

    await s.act('hide_from_website', SHOWN);
    expect(s.body(s.calls('/api/inventory/products/update')[0])).toEqual({ id: 'p1', show_on_website: false });
    await s.act('show_on_website', HIDDEN);
    expect(s.body(s.calls('/api/inventory/products/update')[1])).toEqual({ id: 'p1', show_on_website: true });
    s.net.onApi(api(() => refusal(403, 'permission_denied', 'You do not have permission.')));
    await s.act('hide_from_website', SHOWN);
    expect(s.testid('inventory-products-page-error').text()).toContain('You do not have permission.');
  });

  it('is not offered to whoever cannot change products', async () => {
    const s = await setup({ session: EMPLOYEE });
    await s.show(page([SHOWN], 1));

    expect(s.prop<Array<{ id: string }>>('actions').map((a) => a.id)).not.toContain('hide_from_website');
  });

  it('reads in Spanish', async () => {
    const s = await setup({ locale: 'es' });
    await s.show(page([SHOWN], 1));

    const labels = s.prop<Array<{ id: string; label: string }>>('actions').filter((a) => a.id.endsWith('website')).map((a) => a.label);
    expect(labels).toEqual(['Ocultar de la página web', 'Mostrar en la página web']);
  });
});
