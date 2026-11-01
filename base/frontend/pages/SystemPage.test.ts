// System's page (BASE-F39, BASE-G87): its four tabs, each in the address, what each opens for who runs the business and
// what anyone else is told, with no useless «Retry». What «Usage and plan» says is SystemUsage.test.ts's.
import { AppPage, type ShellTab } from '@erplora/ui/shell';
import { describe, expect, it } from 'vitest';

import { EMPLOYEE, flush, mountBase } from '../__tests__/mount-base';
import FailedEvents from '../components/FailedEvents.vue';
import SystemLog from '../components/SystemLog.vue';
import SystemRelease from '../components/SystemRelease.vue';
import SystemUsage from '../components/SystemUsage.vue';
import SystemPage from './SystemPage.vue';

// ── The tabs (APP-BASE-7) ───────────────────────────────────────────────────────────────────────────────────

async function at(path: string, options: Parameters<typeof mountBase>[1] = {}) {
  const m = await mountBase(SystemPage, { path, routes: ['/system', '/settings'], ...options });
  // Anyone else asks nothing live here: no stream opens for them.
  if (options.session !== EMPLOYEE) await m.live();
  await flush();
  return m;
}

const tabIds = (m: Awaited<ReturnType<typeof at>>) =>
  (m.wrapper.getComponent(AppPage).props('tabs') as ShellTab[]).map((tab) => [`tab-${tab.id}`, tab.label]);

describe('SystemPage › its tabs (BASE-G87)', () => {
  it('who runs the business has four tabs, in their order', async () => {
    const m = await at('/system');
    expect(tabIds(m)).toEqual([
      ['tab-usage', 'Usage and plan'],
      ['tab-updates', 'Updates'],
      ['tab-events', 'Failed events'],
      ['tab-logs', 'Logs'],
    ]);
  });

  it('anyone else has three: Logs does not exist for them', async () => {
    const m = await at('/system', { session: EMPLOYEE, locale: 'es' });
    expect(tabIds(m).map(([id]) => id)).toEqual(['tab-usage', 'tab-updates', 'tab-events']);
    expect(tabIds(m).map(([, label]) => label)).toEqual(['Uso y plan', 'Actualizaciones', 'Eventos caídos']);
  });

  it('opens «Usage and plan», its own and nothing of the others', async () => {
    const m = await at('/system');
    expect(m.wrapper.findComponent(SystemUsage).exists()).toBe(true);
    expect(m.wrapper.findComponent(FailedEvents).exists()).toBe(false);
    expect(m.wrapper.findComponent(SystemLog).exists()).toBe(false);
  });

  it.each(['#resources', '#plan'])('the old address %s opens «Usage and plan»', async (hash) => {
    const m = await at(`/system${hash}`);
    expect(m.wrapper.findComponent(SystemUsage).exists()).toBe(true);
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

  it('Logs in the address of anyone else opens «Usage and plan», which tells who may see it', async () => {
    const m = await at('/system#logs', { session: EMPLOYEE });
    expect(m.wrapper.findComponent(SystemLog).exists()).toBe(false);
    expect(m.wrapper.find('[data-testid="system-usage-denied"]').text()).toBe(
      'Only the owner or an administrator can see how much the hub is using.',
    );
    // Nothing of who runs the business is asked: the Hub would refuse it.
    expect(m.client.stream.subscriptions('base.plan.usage')).toEqual([]);
    expect(m.wrapper.find('[data-testid="system-usage-retry"]').exists()).toBe(false);
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
