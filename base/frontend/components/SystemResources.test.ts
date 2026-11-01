// System › Resources (BASE-G88, G45; the old hub's SystemPage `#resources`, HUB_SHELL-F136), for who runs the business:
// «Cloud resources» with the database the business is on (phase 1: the one every business shares), and why there are
// no CPU, memory or connection figures — one service runs every business, so none of them is the hub's own (PLAN-HUB
// §1a) — instead of the old «We could not read it» forever. A failed read says so, with «Retry». A business on its own
// database also says its size as the last night measured it (`base.plan.usage`'s `database`, BASE-F40), or that the
// first figure comes after the first night; one that shares its database has no size of its own.
import { afterEach, describe, expect, it } from 'vitest';

import { errorFrame, flush, mountBase, subId } from '../__tests__/mount-base';
import SystemResources from './SystemResources.vue';

const OP = 'base.system.status';
const STATUS = { version: '4da2a10', released_at: '2026-10-23T18:50:00Z', shared_database: true };
const PLAN = { known: true, people: { used: 2, limit: 5 }, devices: { used: 1, limit: 2 } };
const MEASURED = { ...PLAN, database: { available: true, bytes: 12.4 * 1024 * 1024, day: '2026-10-30' } };

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

  it('a hub on its own database says its size as the last night measured it', async () => {
    const m = await open();
    expect(m.client.stream.subscriptions('base.plan.usage').map((sub) => sub.params)).toEqual([{}]);
    await m.result(m.call, OP, { ...STATUS, shared_database: false });
    await m.result(m.call, 'base.plan.usage', MEASURED);
    const size = m.wrapper.get('[data-testid="system-resources-size"]').text();
    expect(size).toContain('12.4 MB');
    expect(size).toContain('Measured on Oct 30, 2026');
  });

  it('before the first night, says when its size comes; in Spanish too', async () => {
    const m = await open({ locale: 'es' });
    await m.result(m.call, OP, { ...STATUS, shared_database: false });
    await m.result(m.call, 'base.plan.usage', { ...PLAN, database: { available: true, bytes: null, day: null } });
    expect(m.wrapper.get('[data-testid="system-resources-size"]').text()).toBe(
      'Su tamaño se mide cada noche: la primera cifra llega mañana.',
    );
  });

  it('a hub that shares its database shows no size of its own', async () => {
    const m = await open();
    await m.result(m.call, OP, STATUS);
    await m.result(m.call, 'base.plan.usage', { ...PLAN, database: { available: false, bytes: null, day: null } });
    expect(m.wrapper.find('[data-testid="system-resources-size"]').exists()).toBe(false);
    expect(m.wrapper.text()).not.toMatch(/\bMB\b|\bKB\b/);
  });

  it('a failed read says so, with «Retry»', async () => {
    const m = await open();
    m.call.push(errorFrame(subId(m.client, OP), 'internal_error'));
    await flush();
    expect(m.wrapper.find('[data-testid="system-resources-error"]').text()).toContain('We could not read the system');
    expect(m.wrapper.find('[data-testid="system-resources-retry"]').exists()).toBe(true);
  });
});
