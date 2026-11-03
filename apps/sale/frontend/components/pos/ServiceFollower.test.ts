// One service of Services followed live (`service.service.get`): the till's notice of a refused tap goes the
// moment the service has its tax category (SALE-F38, hub#719). Renderless; mounted only while that notice is up.
import { RELEASE_GRACE_MS } from '@erplora/ui/sdk';
import { describe, expect, it } from 'vitest';

import { errorFrame, mountSale } from '../../__tests__/mount-sale';
import { service } from './__tests__/fixtures';
import ServiceFollower from './ServiceFollower.vue';

const GET = 'service.service.get';

describe('ServiceFollower', () => {
  it('follows the service by its id and hands every answer up', async () => {
    const m = await mountSale(ServiceFollower, { props: { serviceId: 'sv1' } });
    await m.live();
    expect(m.params(GET)).toEqual([{ id: 'sv1' }]);
    const untaxed = service({ id: 'sv1', needs_tax_setup: true });
    await m.result(GET, untaxed);
    expect(m.wrapper.emitted('service')).toEqual([[untaxed]]);
    const taxed = service({ id: 'sv1', needs_tax_setup: false });
    await m.result(GET, taxed, {}, 2);
    expect(m.wrapper.emitted('service')).toEqual([[untaxed], [taxed]]);
  });

  it('an error hands nothing up: what the till last knew stays', async () => {
    const m = await mountSale(ServiceFollower, { props: { serviceId: 'sv1' } });
    await m.live();
    m.net.lastStream().push(errorFrame(m.subId(GET), 'permission_denied'));
    await m.reopen();
    expect(m.wrapper.emitted('service')).toBeUndefined();
  });

  it('lets the service go when it is let go', async () => {
    const m = await mountSale(ServiceFollower, { props: { serviceId: 'sv1' } });
    await m.live();
    m.wrapper.unmount();
    await m.clock.advance(RELEASE_GRACE_MS);
    expect(m.params(GET)).toEqual([]);
  });
});
