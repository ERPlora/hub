// System › Logs (BASE-G90, G24; the old hub's SystemPage `#logs`, HUB_SHELL-F144), for who runs the business: the live
// `base.event.list` — the last 50 events between the hub's apps — in a table of Time, Level and Event (its name, the
// app that recorded it and what happened to it, in the person's language; never its content), searchable, filtered by
// level and paged by 20. No events says so in plain words; a failed read says so, with «Retry».
import { DataTable } from '@erplora/ui/components';
import { afterEach, describe, expect, it } from 'vitest';
import type { Component } from 'vue';

import { errorFrame, flush, mountBase, subId } from '../__tests__/mount-base';
import type { EventLogEntry } from '../operations';
import SystemLog from './SystemLog.vue';

const OP = 'base.event.list';

function entry(id: string, over: Partial<EventLogEntry> = {}): EventLogEntry {
  return {
    id,
    at: '2026-10-23T18:50:00Z',
    level: 'info',
    name: 'sale.sale.completed',
    app: 'sale',
    app_name: 'Sales & POS',
    detail: 'Delivered to Invoicing.',
    ...over,
  };
}

/** A prop of the log's DataTable (a generic component: its props are read untyped). */
const prop = <T = unknown>(m: Awaited<ReturnType<typeof open>>, name: string) =>
  (m.wrapper.findComponent(DataTable as unknown as Component).props() as Record<string, unknown>)[name] as T;

async function open(options: Parameters<typeof mountBase>[1] = {}) {
  const m = await mountBase(SystemLog, options);
  const call = await m.live();
  return { ...m, call };
}

afterEach(() => {
  document.body.innerHTML = '';
});

describe('SystemLog', () => {
  it('follows the log live, in a table of time, level and event, 20 a page, searchable and filtered by level', async () => {
    const m = await open();
    expect(m.client.stream.subscriptions(OP).map((sub) => sub.params)).toEqual([{}]);
    await m.result(m.call, OP, { entries: [entry('e1'), entry('e2', { level: 'error', detail: 'Invoicing could not take it: it is in Failed events.' })] });
    expect(prop<{ key: string; label: string }[]>(m, 'columns').map((column) => [column.key, column.label])).toEqual([
      ['at', 'Time'],
      ['level', 'Level'],
      ['event', 'Event'],
    ]);
    expect(prop(m, 'pageSize')).toBe(20);
    expect(prop(m, 'searchPlaceholder')).toBe('Search event…');
    expect(prop(m, 'searchKeys')).toEqual(['name', 'app_name', 'detail']);
    const level = prop<unknown[]>(m, 'columns')[1] as { filter: { type: string; options: { value: string; label: string }[] } };
    expect(level.filter.options).toEqual([
      { value: 'info', label: 'Info' },
      { value: 'warning', label: 'Warning' },
      { value: 'error', label: 'Error' },
    ]);
    expect(m.wrapper.text()).toContain('sale.sale.completed');
    expect(m.wrapper.text()).toContain('Sales & POS');
    expect(m.wrapper.text()).toContain('Invoicing could not take it: it is in Failed events.');
  });

  it('on a phone each event is a card headed by its time, so what happened is never past the screen’s edge', async () => {
    const m = await open();
    await m.result(m.call, OP, { entries: [entry('e1')] });
    expect(prop(m, 'views')).toEqual(['table', 'cards']);
    expect(prop(m, 'cardTitleColumn')).toBe('at');
    const at = prop<{ format: (value: unknown, row: EventLogEntry) => string }[]>(m, 'columns')[0];
    expect(prop<(row: EventLogEntry) => string>(m, 'cardTitle')(entry('e1'))).toBe(at.format(undefined, entry('e1')));
    expect(at.format(undefined, entry('e1'))).toMatch(/^Oct 2[34], 2026, \d{1,2}:50 [AP]M$/);
  });

  it('paints each level as a pill in the person’s language', async () => {
    const m = await open({ locale: 'es' });
    await m.result(m.call, OP, { entries: [entry('e1', { level: 'warning' })] });
    expect(m.wrapper.find('[data-testid="system-log-level"]').text()).toBe('Aviso');
  });

  it('no events says so in plain words', async () => {
    const m = await open();
    await m.result(m.call, OP, { entries: [] });
    expect(prop(m, 'emptyMessage')).toBe(
      "No events yet: nothing has gone between this business's apps.",
    );
  });

  it('loading, then a failed read with «Retry»', async () => {
    const m = await open();
    expect(prop(m, 'loading')).toBe(true);
    m.call.push(errorFrame(subId(m.client, OP), 'internal_error'));
    await flush();
    expect(prop(m, 'error')).toBe(
      'The log could not be loaded. Check the connection and try again.',
    );
  });
});
