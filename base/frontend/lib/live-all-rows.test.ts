// `useLiveAllRows(op, query)`: every row of a live list a screen needs whole (a sheet to print), read in windows of a
// hundred, the server's cap on a list's `limit`: the first window, then as many as its total asks, joined in order,
// each one live. It is complete once every window has come.
import { RELEASE_GRACE_MS } from '@erplora/ui/sdk';
import { describe, expect, it } from 'vitest';
import { defineComponent, h, ref } from 'vue';

import { OWNER } from '../__tests__/mount-base';
import { flush, mountInShell, page } from '../__tests__/mount-in-shell';
import { useLiveAllRows } from './live-all-rows';

const OP = 'demo.item.list';
const row = (id: string) => ({ id, name: id });

async function setup() {
  const status = ref<'open' | 'done'>('open');
  const exposed: { all?: ReturnType<typeof useLiveAllRows<'demo.item.list'>> } = {};
  const Host = defineComponent({
    setup() {
      exposed.all = useLiveAllRows(OP, () => ({ status: status.value }));
      return () => h('p', exposed.all!.rows.value.map((r) => r.id).join(','));
    },
  });
  const m = await mountInShell(Host, {}, { path: '/', session: OWNER, messages: { en: {}, es: {} } });
  await m.live();
  return { ...m, status, all: exposed.all! };
}

describe('useLiveAllRows', () => {
  it('asks the first hundred rows and, when they are all, stays on one window and is complete', async () => {
    const s = await setup();
    expect(s.params(OP)).toEqual([{ status: 'open', limit: 100, offset: 0 }]);
    expect([s.all.status.value, s.all.complete.value]).toEqual(['loading', false]);
    await s.result(OP, page([row('1'), row('2')], 2, 100, 0));
    expect(s.wrapper.text()).toBe('1,2');
    expect([s.all.status.value, s.all.total.value, s.all.complete.value]).toEqual(['live', 2, true]);
  });

  it('an empty list is complete with no rows', async () => {
    const s = await setup();
    await s.result(OP, page([], 0, 100, 0));
    expect([s.all.rows.value, s.all.complete.value]).toEqual([[], true]);
  });

  it('opens as many windows as the total asks, joins them in order and is complete only when all came', async () => {
    const s = await setup();
    await s.result(OP, page([row('1')], 250, 100, 0));
    await flush();
    await s.reopen();
    expect(s.params(OP)).toEqual([
      { status: 'open', limit: 100, offset: 0 },
      { status: 'open', limit: 100, offset: 100 },
      { status: 'open', limit: 100, offset: 200 },
    ]);
    await s.result(OP, page([row('1')], 250, 100, 0), { offset: 0 });
    await s.result(OP, page([row('201')], 250, 100, 200), { offset: 200 });
    // The middle window has not come: what follows it waits, so the rows never jump.
    expect(s.wrapper.text()).toBe('1');
    expect(s.all.complete.value).toBe(false);
    await s.result(OP, page([row('101')], 250, 100, 100), { offset: 100 });
    expect(s.wrapper.text()).toBe('1,101,201');
    expect(s.all.complete.value).toBe(true);
  });

  it('drops the windows the total no longer asks for', async () => {
    const s = await setup();
    await s.result(OP, page([row('1')], 150, 100, 0));
    await flush();
    await s.reopen();
    expect(s.params(OP)).toHaveLength(2);
    await s.result(OP, page([row('1')], 50, 100, 0), { offset: 0 });
    await flush();
    // A dropped subscription is released after the SDK's grace, then the stream reopens without it.
    await s.clock.advance(RELEASE_GRACE_MS);
    await s.reopen();
    expect(s.params(OP)).toEqual([{ status: 'open', limit: 100, offset: 0 }]);
    expect(s.wrapper.text()).toBe('1');
  });

  it('follows its query in every window', async () => {
    const s = await setup();
    s.status.value = 'done';
    await flush();
    await s.reopen();
    await s.clock.advance(RELEASE_GRACE_MS);
    expect(s.params(OP)).toEqual([{ status: 'done', limit: 100, offset: 0 }]);
  });
});
