// The Home card while a load still waits for an app (hub#609): it says its data comes by itself, says so of an app that
// could not be set up, and follows the load live, so the card tells how it ended with nothing pressed.
import { afterEach, describe, expect, it } from 'vitest';

import { load } from '../__tests__/data-fixtures';
import { flush, mountBase } from '../__tests__/mount-base';
import type { ImportRow } from '../operations';
import BlueprintCardPending from './BlueprintCardPending.vue';

afterEach(() => {
  document.body.innerHTML = '';
});

function loadWith(status: 'waiting' | 'setup_failed'): ImportRow {
  return load({
    status: 'partial',
    retry: status === 'setup_failed',
    retry_blocked: status === 'setup_failed' ? '' : 'waiting',
    report: { status: 'partial', dropped: [], apps: [{ id: 'service', label: 'Services', status, reason: 'Why.', datasets: [] }] },
  });
}

async function settle() {
  for (let i = 0; i < 4; i += 1) await flush();
}

async function pending(row: ImportRow, locale: 'en' | 'es' = 'en') {
  const m = await mountBase(BlueprintCardPending, { props: { load: row }, locale, path: '/', routes: ['/'] });
  return { ...m, call: await m.live() };
}

describe('BlueprintCardPending', () => {
  it('says the app is being set up and its data comes by itself', async () => {
    const m = await pending(loadWith('waiting'));
    expect(m.wrapper.get('[data-testid="blueprint-card-pending"]').text()).toContain('Your apps are being set up');
    expect(m.wrapper.get('[data-testid="blueprint-card-pending"]').text()).toContain('Services');
    expect(m.wrapper.find('ion-spinner').exists()).toBe(true);
  });

  it('says it in Spanish', async () => {
    const m = await pending(loadWith('waiting'), 'es');
    expect(m.wrapper.get('[data-testid="blueprint-card-pending"]').text()).toContain('Tus apps se están preparando');
  });

  it('says an app could not be set up and that it keeps trying, with no spinner', async () => {
    const m = await pending(loadWith('setup_failed'));
    expect(m.wrapper.get('[data-testid="blueprint-card-failing"]').text()).toContain('Services');
    expect(m.wrapper.find('[data-testid="blueprint-card-pending"]').exists()).toBe(false);
    expect(m.wrapper.find('ion-spinner').exists()).toBe(false);
    expect(m.wrapper.emitted('settled')).toBeUndefined();
  });

  it('follows the load live: a failure shows, and the end is told to the card', async () => {
    const row = loadWith('waiting');
    const m = await pending(row);

    await m.result(m.call, 'base.import.list', { imports: [loadWith('setup_failed')], unfinished: null });
    await settle();
    expect(m.wrapper.find('[data-testid="blueprint-card-failing"]').exists()).toBe(true);
    expect(m.wrapper.emitted('settled')).toBeUndefined();

    const done = load({ id: row.id });
    await m.result(m.call, 'base.import.list', { imports: [done], unfinished: null }, 2);
    await settle();
    expect(m.wrapper.emitted('settled')).toEqual([[done]]);
  });

  it('keeps saying it while the list does not have the load yet', async () => {
    const m = await pending(loadWith('waiting'));
    await m.result(m.call, 'base.import.list', { imports: [], unfinished: null });
    await settle();
    expect(m.wrapper.find('[data-testid="blueprint-card-pending"]').exists()).toBe(true);
    expect(m.wrapper.emitted('settled')).toBeUndefined();
  });
});
