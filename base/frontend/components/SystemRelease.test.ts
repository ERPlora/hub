// System › Updates, the part of who runs the business (BASE-G89; the old hub's «You are on {version}», HUB_SHELL-F142):
// the version running, from the live `base.system.status` (a deploy reconnects the stream and the new one shows by
// itself), and when it was published, never a made-up date. A failed read says so, with «Retry».
import { afterEach, describe, expect, it } from 'vitest';

import { errorFrame, flush, mountBase, subId } from '../__tests__/mount-base';
import SystemRelease from './SystemRelease.vue';

const OP = 'base.system.status';
const STATUS = { version: '4da2a10', released_at: '2026-10-23T18:50:00Z', shared_database: true };

async function open(options: Parameters<typeof mountBase>[1] = {}) {
  const m = await mountBase(SystemRelease, options);
  const call = await m.live();
  return { ...m, call };
}

afterEach(() => {
  document.body.innerHTML = '';
});

describe('SystemRelease', () => {
  it('says the version running and when it was published', async () => {
    const m = await open();
    expect(m.client.stream.subscriptions(OP).map((sub) => sub.params)).toEqual([{}]);
    await m.result(m.call, OP, STATUS);
    expect(m.wrapper.find('[data-testid="system-release-version"]').text()).toBe('You are on 4da2a10');
    expect(m.wrapper.find('[data-testid="system-release-date"]').text()).toMatch(/^Updated on .*2026.*\.$/);
  });

  it('says it is reading the version until the status answers, never an empty tab', async () => {
    const m = await open();
    const loading = m.wrapper.find('[data-testid="system-release-loading"]');
    expect(loading.exists()).toBe(true);
    expect(loading.attributes('role')).toBe('status');
    expect(loading.text()).toBe('Reading the version…');
    expect(m.wrapper.find('[data-testid="system-release-version"]').exists()).toBe(false);
    await m.result(m.call, OP, STATUS);
    expect(m.wrapper.find('[data-testid="system-release-loading"]').exists()).toBe(false);
    expect(m.wrapper.find('[data-testid="system-release-version"]').exists()).toBe(true);
  });

  it('reading, in Spanish', async () => {
    const m = await open({ locale: 'es' });
    expect(m.wrapper.find('[data-testid="system-release-loading"]').text()).toBe('Consultando la versión…');
  });

  it('a failed read is not «reading» any more', async () => {
    const m = await open();
    m.call.push(errorFrame(subId(m.client, OP), 'internal_error'));
    await flush();
    expect(m.wrapper.find('[data-testid="system-release-loading"]').exists()).toBe(false);
  });

  it('in Spanish, with the date in its format', async () => {
    const m = await open({ locale: 'es' });
    await m.result(m.call, OP, STATUS);
    expect(m.wrapper.find('[data-testid="system-release-version"]').text()).toBe('Vas por la 4da2a10');
    expect(m.wrapper.find('[data-testid="system-release-date"]').text()).toMatch(/^Actualizado el 23 oct 2026/);
  });

  it('an unknown date is said, never made up', async () => {
    const m = await open();
    await m.result(m.call, OP, { ...STATUS, version: 'dev', released_at: null });
    expect(m.wrapper.find('[data-testid="system-release-version"]').text()).toBe('You are on dev');
    expect(m.wrapper.find('[data-testid="system-release-date"]').text()).toBe(
      'We do not know when this version was published.',
    );
  });

  it('a failed read says so, with «Retry»', async () => {
    const m = await open();
    m.call.push(errorFrame(subId(m.client, OP), 'internal_error'));
    await flush();
    expect(m.wrapper.find('[data-testid="system-release-error"]').text()).toContain('We could not read the system');
    expect(m.wrapper.find('[data-testid="system-release-retry"]').exists()).toBe(true);
  });
});
