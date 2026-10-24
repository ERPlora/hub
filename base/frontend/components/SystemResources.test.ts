// System › Resources (BASE-G88, G45; the old hub's SystemPage `#resources`, HUB_SHELL-F136), for who runs the business:
// «Cloud resources» with the database the business is on (phase 1: the one every business shares), and why there are
// no CPU, memory or connection figures — one service runs every business, so none of them is the hub's own (PLAN-HUB
// §1a) — instead of the old «We could not read it» forever. A failed read says so, with «Retry».
import { afterEach, describe, expect, it } from 'vitest';

import { errorFrame, flush, mountBase, subId } from '../__tests__/mount-base';
import SystemResources from './SystemResources.vue';

const OP = 'base.system.status';
const STATUS = { version: '4da2a10', released_at: '2026-10-23T18:50:00Z', shared_database: true };

async function open(options: Parameters<typeof mountBase>[1] = {}) {
  const m = await mountBase(SystemResources, options);
  const call = await m.live();
  return { ...m, call };
}

afterEach(() => {
  document.body.innerHTML = '';
});

describe('SystemResources', () => {
  it('follows the system status live, reading meanwhile', async () => {
    const m = await open();
    expect(m.client.stream.subscriptions(OP).map((sub) => sub.params)).toEqual([{}]);
    expect(m.wrapper.find('[data-testid="system-resources-loading"]').exists()).toBe(true);
  });

  it('says the cloud, the database and why there are no usage figures', async () => {
    const m = await open();
    await m.result(m.call, OP, STATUS);
    expect(m.wrapper.find('h2').text()).toBe('Cloud resources');
    expect(m.wrapper.find('[data-testid="system-resources-cloud"]').text()).toBe('Cloud');
    const database = m.wrapper.find('[data-testid="system-resources-database"]').text();
    expect(database).toContain('PostgreSQL');
    expect(database).toContain('Shared database');
    expect(m.wrapper.find('[data-testid="system-resources-not-measured"]').text()).toContain(
      'CPU, memory and connections are not measured per business',
    );
    // Never a made-up zero nor a flat line.
    expect(m.wrapper.text()).not.toMatch(/\b0 ?%/);
  });

  it('a hub on its own database says so', async () => {
    const m = await open({ locale: 'es' });
    await m.result(m.call, OP, { ...STATUS, shared_database: false });
    expect(m.wrapper.find('[data-testid="system-resources-database"]').text()).toContain('Base de datos propia');
  });

  it('a failed read says so, with «Retry»', async () => {
    const m = await open();
    m.call.push(errorFrame(subId(m.client, OP), 'internal_error'));
    await flush();
    expect(m.wrapper.find('[data-testid="system-resources-error"]').text()).toContain('We could not read the system');
    expect(m.wrapper.find('[data-testid="system-resources-retry"]').exists()).toBe(true);
  });
});
