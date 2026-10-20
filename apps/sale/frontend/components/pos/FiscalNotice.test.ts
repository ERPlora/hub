// flow: SALE-F07 — the till warns when VeriFactu refuses new sales now (`verifactu.config.get`, live, its
// `issue_blocker`): above the grid, with VeriFactu's own reason and, to whoever can configure it, «Review VeriFactu».
// Nothing while it can sell, nor when VeriFactu cannot be read (the charge itself would say why).
import { describe, expect, it } from 'vitest';

import { click, EMPLOYEE, errorFrame, MANAGER, mountSale } from '../../__tests__/mount-sale';
import FiscalNotice from './FiscalNotice.vue';

const OP = 'verifactu.config.get';
const BLOCKED = { issue_blocker: { code: 'production_closed', message: 'Production is not open on this server yet.' } };
const OWNER = { ...MANAGER, permissions: [...MANAGER.permissions, 'verifactu.configure'] };

async function setup(session = OWNER) {
  const m = await mountSale(FiscalNotice, { session, locale: 'es' });
  await m.live();
  return m;
}

describe('FiscalNotice', () => {
  it('says why nothing can be charged now, with VeriFactu’s own words, and leads whoever can fix it there', async () => {
    const s = await setup();
    expect(s.params(OP)).toEqual([{}]);
    await s.result(OP, BLOCKED);
    expect(s.find('pos-fiscal-notice').text()).toContain('Ahora no se pueden cobrar ventas');
    expect(s.find('pos-fiscal-notice').text()).toContain('Production is not open on this server yet.');
    await click(s.find('pos-fiscal-review').element);
    expect(s.router.currentRoute.value.path).toBe('/verifactu/config');
  });

  it('an employee reads the reason without the way to configure', async () => {
    const s = await setup(EMPLOYEE);
    await s.result(OP, BLOCKED);
    expect(s.find('pos-fiscal-notice').exists()).toBe(true);
    expect(s.find('pos-fiscal-review').exists()).toBe(false);
  });

  it('says nothing while it can sell, or when VeriFactu cannot be read', async () => {
    const s = await setup();
    await s.result(OP, { issue_blocker: null });
    expect(s.find('pos-fiscal-notice').exists()).toBe(false);
    s.net.lastStream().push(errorFrame(s.subId(OP), 'internal_error'));
    await s.reopen();
    expect(s.find('pos-fiscal-notice').exists()).toBe(false);
  });
});
