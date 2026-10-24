// System › «Plan and limits» (BASE-G81; the old hub's SystemPage, tab `#plan`): the live `base.plan.usage` — the
// people of the business against the plan's limit, the devices in use (a session open here, APP-BASE-3) and their
// limit —, a warning when every place is taken, where plans are managed (erplora.com, no button:
// the stores refuse an app that sells), and a refusal that says who may see it instead of a useless «Retry».
import { afterEach, describe, expect, it } from 'vitest';

import { EMPLOYEE, errorFrame, flush, mountBase, subId } from '../__tests__/mount-base';
import type { PlanUsage } from '../operations';
import SystemPage from './SystemPage.vue';

const USAGE: PlanUsage = { known: true, people: { used: 2, limit: 3 }, devices: { used: 1, limit: 2 } };

async function open(options: Parameters<typeof mountBase>[1] = {}) {
  const m = await mountBase(SystemPage, { path: '/system', routes: ['/system'], ...options });
  const call = await m.live();
  return { ...m, call };
}

afterEach(() => {
  document.body.innerHTML = '';
});

describe('SystemPage › Plan and limits', () => {
  it('follows the plan’s use live', async () => {
    const m = await open();
    expect(m.client.stream.subscriptions('base.plan.usage').map((sub) => sub.params)).toEqual([{}]);
    expect(m.wrapper.find('[data-testid="system-plan-loading"]').exists()).toBe(true);
  });

  it('the people against the plan’s limit, the devices in use and their limit, and where plans are managed', async () => {
    const m = await open();
    await m.result(m.call, 'base.plan.usage', USAGE);
    expect(m.wrapper.find('[data-testid="system-plan-people"]').text()).toContain('2 of 3');
    const devices = m.wrapper.find('[data-testid="system-plan-devices"]');
    expect(devices.find('[data-testid="system-plan-devices-used"]').text()).toBe('1');
    expect(devices.text()).toContain('Up to 2');
    expect(devices.text()).toContain('With a session open now.');
    expect(devices.text()).not.toContain('n/a');
    expect(m.wrapper.find('[data-testid="system-plan-status"]').text()).toBe('Within the limit');
    expect(m.wrapper.find('[data-testid="system-plan-full"]').exists()).toBe(false);
    expect(m.wrapper.text()).toContain('Plans are managed from your ERPlora account, on erplora.com.');
  });

  it('every place taken: «Close to the limit» and why, with no button (BASE-G81)', async () => {
    const m = await open({ locale: 'es' });
    await m.result(m.call, 'base.plan.usage', { ...USAGE, people: { used: 3, limit: 3 } });
    expect(m.wrapper.find('[data-testid="system-plan-status"]').text()).toBe('Cerca del límite');
    expect(m.wrapper.find('[data-testid="system-plan-full"]').text()).toContain(
      'Tu plan tiene todas las plazas ocupadas, así que no puedes añadir a nadie más.',
    );
    expect(m.wrapper.find('[data-testid="system-plan-full"] a, [data-testid="system-plan-full"] ion-button').exists()).toBe(false);
    expect(m.wrapper.find('[data-testid="system-plan-devices"]').text()).toContain('Hasta 2');
    expect(m.wrapper.find('[data-testid="system-plan-devices"]').text()).toContain('Con una sesión abierta ahora.');
  });

  it('no limit in the plan says so instead of a bar', async () => {
    const m = await open();
    await m.result(m.call, 'base.plan.usage', { known: true, people: { used: 4, limit: null }, devices: { used: 3, limit: null } });
    expect(m.wrapper.find('[data-testid="system-plan-people"]').text()).toContain('No limit');
    expect(m.wrapper.find('[data-testid="system-plan-devices"]').text()).toContain('No limit');
    expect(m.wrapper.find('[data-testid="system-plan-devices-used"]').text()).toBe('3');
    expect(m.wrapper.find('[data-testid="system-plan-status"]').text()).toBe('Within the limit');
  });

  it('a plan it does not know yet is said, never painted as unlimited', async () => {
    const m = await open();
    await m.result(m.call, 'base.plan.usage', { known: false, people: { used: 1, limit: null }, devices: { used: 1, limit: null } });
    expect(m.wrapper.find('[data-testid="system-plan-unknown"]').exists()).toBe(true);
    expect(m.wrapper.find('[data-testid="system-plan-people"]').text()).not.toContain('No limit');
    // What is in use is the hub's own count: it shows without a plan, its limit does not.
    expect(m.wrapper.find('[data-testid="system-plan-devices-used"]').text()).toBe('1');
    expect(m.wrapper.find('[data-testid="system-plan-devices"]').text()).not.toContain('No limit');
    expect(m.wrapper.find('[data-testid="system-plan-status"]').exists()).toBe(false);
  });

  it('who does not run the business is told who may see it, with no «Retry» that cannot help', async () => {
    const m = await open({ session: EMPLOYEE });
    m.call.push(errorFrame(subId(m.client, 'base.plan.usage'), 'permission_denied'));
    await flush();
    expect(m.wrapper.find('[data-testid="system-plan-denied"]').text()).toContain('Only whoever runs the business can see');
    expect(m.wrapper.find('[data-testid="system-plan-retry"]').exists()).toBe(false);
  });

  it('a failed read says so with «Retry»', async () => {
    const m = await open();
    m.call.push(errorFrame(subId(m.client, 'base.plan.usage'), 'internal_error'));
    await flush();
    expect(m.wrapper.find('[data-testid="system-plan-error"]').exists()).toBe(true);
    expect(m.wrapper.find('[data-testid="system-plan-retry"]').exists()).toBe(true);
  });
});
