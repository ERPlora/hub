// System › «Plan and limits» (BASE-G81; the old hub's SystemPage, tab `#plan`): the live `base.plan.usage` — the
// people of the business against the plan's limit, the devices in use (a session open here, APP-BASE-3) and their
// limit —, a warning when every place is taken, where plans are managed (erplora.com, no button:
// the stores refuse an app that sells), and a refusal that says who may see it instead of a useless «Retry».
import { AppPage, type ShellTab } from '@erplora/ui/shell';
import { afterEach, describe, expect, it } from 'vitest';

import { EMPLOYEE, errorFrame, flush, mountBase, subId } from '../__tests__/mount-base';
import FailedEvents from '../components/FailedEvents.vue';
import SystemLog from '../components/SystemLog.vue';
import SystemRelease from '../components/SystemRelease.vue';
import SystemResources from '../components/SystemResources.vue';
import type { PlanUsage } from '../operations';
import SystemPage from './SystemPage.vue';

const USAGE: PlanUsage = { known: true, people: { used: 2, limit: 3 }, devices: { used: 1, limit: 2 } };

async function open(options: Parameters<typeof mountBase>[1] = {}) {
  // «Plan and limits» is its tab now: `/system` opens Resources, as the old hub did (BASE-G87).
  const m = await mountBase(SystemPage, { path: '/system#plan', routes: ['/system', '/settings'], ...options });
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

// ── The tabs (APP-BASE-7) ───────────────────────────────────────────────────────────────────────────────────

async function at(path: string, options: Parameters<typeof mountBase>[1] = {}) {
  const m = await mountBase(SystemPage, { path, routes: ['/system', '/settings'], ...options });
  await m.live();
  await flush();
  return m;
}

const tabIds = (m: Awaited<ReturnType<typeof at>>) =>
  (m.wrapper.getComponent(AppPage).props('tabs') as ShellTab[]).map((tab) => [`tab-${tab.id}`, tab.label]);

describe('SystemPage › its tabs (BASE-G87)', () => {
  it('who runs the business has the old hub’s five tabs, in its order', async () => {
    const m = await at('/system');
    expect(tabIds(m)).toEqual([
      ['tab-resources', 'Resources'],
      ['tab-plan', 'Plan and limits'],
      ['tab-updates', 'Updates'],
      ['tab-events', 'Failed events'],
      ['tab-logs', 'Logs'],
    ]);
  });

  it('anyone else has four: Logs does not exist for them', async () => {
    const m = await at('/system', { session: EMPLOYEE, locale: 'es' });
    expect(tabIds(m).map(([id]) => id)).toEqual(['tab-resources', 'tab-plan', 'tab-updates', 'tab-events']);
    expect(tabIds(m).map(([, label]) => label)).toEqual(['Recursos', 'Plan y límites', 'Actualizaciones', 'Eventos caídos']);
  });

  it('opens Resources, its own and nothing of the others', async () => {
    const m = await at('/system');
    expect(m.wrapper.findComponent(SystemResources).exists()).toBe(true);
    expect(m.wrapper.findComponent(FailedEvents).exists()).toBe(false);
    expect(m.wrapper.findComponent(SystemLog).exists()).toBe(false);
  });

  it('opens the tab of the address', async () => {
    expect((await at('/system#events')).wrapper.findComponent(FailedEvents).exists()).toBe(true);
    expect((await at('/system#logs')).wrapper.findComponent(SystemLog).exists()).toBe(true);
  });

  it('a tab chosen goes to the address, replacing it (Back leaves System)', async () => {
    const m = await at('/system');
    const segment = m.wrapper.find('ion-segment');
    segment.element.dispatchEvent(new CustomEvent('ionChange', { detail: { value: 'events' } }));
    await flush();
    expect(m.router.currentRoute.value.hash).toBe('#events');
    expect(m.wrapper.findComponent(FailedEvents).exists()).toBe(true);
  });

  it('Logs in the address of anyone else opens Resources', async () => {
    const m = await at('/system#logs', { session: EMPLOYEE });
    expect(m.wrapper.findComponent(SystemLog).exists()).toBe(false);
    expect(m.wrapper.find('[data-testid="system-resources-denied"]').text()).toBe(
      'Only the owner or an administrator can see how much the hub is using.',
    );
    // Nothing of who runs the business is asked: the Hub would refuse it.
    expect(m.client.stream.subscriptions('base.system.status')).toEqual([]);
  });

  it('Failed events tells anyone else who may see them, never «All in order»', async () => {
    const m = await at('/system#events', { session: EMPLOYEE });
    expect(m.wrapper.find('[data-testid="system-events-denied"]').text()).toBe(
      'Only the owner or an administrator can see the failed events.',
    );
    expect(m.wrapper.text()).not.toContain('All in order');
    expect(m.client.stream.subscriptions('base.failed_event.list')).toEqual([]);
  });

  it('Updates says the hub updates itself; the version only to who runs the business', async () => {
    const owner = await at('/system#updates');
    expect(owner.wrapper.find('[data-testid="system-updates"] h2').text()).toBe('What we have updated');
    expect(owner.wrapper.text()).toContain('This hub updates itself when we publish a new version');
    expect(owner.wrapper.findComponent(SystemRelease).exists()).toBe(true);
    const employee = await at('/system#updates', { session: EMPLOYEE });
    expect(employee.wrapper.text()).toContain('This hub updates itself when we publish a new version');
    expect(employee.wrapper.findComponent(SystemRelease).exists()).toBe(false);
  });

  it('the old backups tab goes to Settings › Data', async () => {
    const m = await at('/system#backups');
    expect([m.router.currentRoute.value.path, m.router.currentRoute.value.hash]).toEqual(['/settings', '#data']);
  });
});
