// Settings › Data › Reset (BASE-G108, BASE-G109): only for who administers the hub. «Undo an import»: one row per
// import that can be undone, confirmed without typing, then what was removed per app; a refusal shows in the dialog
// (hub#2720: the old screen said nothing). «Reset the business»: the plan per section, what never goes, and — when
// the business has its own database — the sections ticked, emptied after typing its name; in phase 1 (shared
// database) the screen says why it cannot instead of offering the red button.
import { ConfirmDialog } from '@erplora/ui/components';
import { afterEach, describe, expect, it } from 'vitest';

import { load } from '../../__tests__/data-fixtures';
import { EMPLOYEE, flush, mountBase } from '../../__tests__/mount-base';
import type { HubReset } from '../../operations';
import ResetPanel from './ResetPanel.vue';

afterEach(() => {
  document.body.innerHTML = '';
});

const PLAN: HubReset = {
  dry_run: true,
  confirm_with: 'Bar Pepe',
  available: true,
  sections: [
    { id: 'inventory', label: 'Inventory', rows: 14, datasets: [{ key: 'inventory.product', label: 'Products', rows: 12 }, { key: 'inventory.category', label: 'Categories', rows: 2 }] },
    { id: 'table', label: 'Tables', rows: 1, datasets: [{ key: 'table.table', label: 'Tables', rows: 1 }] },
  ],
  apps: [],
};

type Sent = { url: string; body: Record<string, unknown> };

async function settle() {
  for (let i = 0; i < 4; i += 1) await flush();
}

async function panel(answer: (sent: Sent) => Response, imports = [load(), load({ id: 'gone', name: 'Old', undoable: false })]) {
  const sent: Sent[] = [];
  const m = await mountBase(ResetPanel, {
    path: '/settings?data=reset#data',
    routes: ['/settings'],
    onApi: ({ url, init }) => {
      const call = { url, body: JSON.parse(String(init.body ?? '{}')) as Record<string, unknown> };
      sent.push(call);
      return answer(call);
    },
  });
  const call = await m.live();
  await m.result(call, 'base.import.list', { imports, unfinished: null });
  await settle();
  return { ...m, sent };
}

const plan = (fields: Partial<HubReset> = {}) => (sent: Sent) =>
  sent.url.endsWith('/reset') ? Response.json({ ...PLAN, ...fields, dry_run: Boolean(sent.body.dry_run) }) : Response.json({});

const dialog = (m: Awaited<ReturnType<typeof panel>>, testid: string) =>
  m.wrapper.findAllComponents(ConfirmDialog).find((d) => d.props('testid') === testid)!;

describe('ResetPanel', () => {
  it('to a person who does not administer the hub, says only an administrator can, and asks nothing', async () => {
    const m = await mountBase(ResetPanel, { session: EMPLOYEE });
    await settle();
    expect(m.wrapper.text()).toContain('Only an administrator can undo imports or reset the business.');
    expect(m.net.api).toEqual([]);
    expect(m.client.stream.subscriptions('base.import.list')).toEqual([]);
  });

  it('lists the imports that can be undone and undoes one, saying what went per app', async () => {
    const m = await panel((sent) =>
      sent.url.endsWith('/undo')
        ? Response.json({ id: sent.body.id, apps: [{ id: 'inventory', label: 'Inventory', removed: 12, failed: 1, problems: ['Products: in use'] }] })
        : plan()(sent),
    );
    const rows = m.wrapper.findAll('[data-testid="undo-row"]');
    expect(rows.map((row) => row.attributes('data-id'))).toEqual([load().id]);
    expect(rows[0].text()).toContain('14 rows');
    await m.wrapper.get(`[data-testid="undo-${load().id}"]`).trigger('click');
    await settle();
    const confirm = dialog(m, 'undo-confirm');
    expect([confirm.props('open'), confirm.props('title'), confirm.props('requireText')]).toEqual([true, 'Undo «Restaurant»', undefined]);
    expect(confirm.props('message')).toBe('The 14 rows this import brought will be removed. What you created afterwards stays.');
    confirm.vm.$emit('confirm');
    await settle();
    expect(m.sent.at(-1)).toEqual({ url: '/api/settings/data/imports/undo', body: { id: load().id } });
    expect(confirm.props('open')).toBe(false);
    const result = m.wrapper.get('[data-testid="undo-result"]').text();
    expect(result).toContain('Inventory — 12 rows removed');
    expect(result).toContain('Inventory — 1 row could not be removed');
    expect(result).toContain('Products: in use');
  });

  it('a refused undo stays in the dialog with the reason (hub#2720)', async () => {
    const m = await panel((sent) =>
      sent.url.endsWith('/undo')
        ? Response.json({ error: { code: 'base.import_undone', message: 'This load was undone already.' } }, { status: 409 })
        : plan()(sent),
    );
    await m.wrapper.get(`[data-testid="undo-${load().id}"]`).trigger('click');
    await settle();
    const confirm = dialog(m, 'undo-confirm');
    confirm.vm.$emit('confirm');
    await settle();
    expect(confirm.props('open')).toBe(true);
    expect(confirm.props('error')).toMatchObject({ message: 'This load was undone already.' });
  });

  it('shows the plan, what never goes, and offers «Export a copy first»', async () => {
    const m = await panel(plan());
    expect(m.sent[0]).toEqual({ url: '/api/settings/data/reset', body: { dry_run: true } });
    const sections = m.wrapper.findAll('[data-testid="reset-section"]');
    expect(sections.map((row) => row.attributes('data-id'))).toEqual(['inventory', 'table']);
    expect(sections[0].text()).toContain('14 rows');
    expect(sections[0].text()).toContain('Products · 12');
    expect(m.wrapper.text()).toContain('Sales, invoices, fiscal records, people and their access');
    await m.wrapper.get('[data-testid="reset-export-first"]').trigger('click');
    await settle();
    expect(m.router.currentRoute.value.fullPath).toBe('/settings?data=export#data');
  });

  it('empties the sections ticked after the business\'s name is typed, and says what went', async () => {
    const m = await panel((sent) =>
      sent.url.endsWith('/reset') && !sent.body.dry_run
        ? Response.json({ ...PLAN, dry_run: false, sections: [PLAN.sections[1]], apps: [{ id: 'inventory', label: 'Inventory', removed: 14, failed: 0, problems: [] }] })
        : plan()(sent),
    );
    const submit = m.wrapper.get('[data-testid="reset-submit"]');
    expect((submit.element as HTMLElement & { disabled?: boolean }).disabled).toBe(true);
    m.wrapper.get('[data-testid="reset-section-inventory"]').element.dispatchEvent(new CustomEvent('ionChange', { detail: { checked: true } }));
    await settle();
    expect((submit.element as HTMLElement & { disabled?: boolean }).disabled).toBe(false);
    await submit.trigger('click');
    await settle();
    const confirm = dialog(m, 'reset-confirm');
    expect(confirm.props()).toMatchObject({
      open: true,
      title: 'This cannot be undone',
      message: '14 rows will be removed for good:',
      consequences: ['Inventory — 14 rows'],
      requireText: 'Bar Pepe',
      requireTextLabel: 'Type «Bar Pepe» to confirm',
      confirmLabel: 'Remove for good',
    });
    confirm.vm.$emit('confirm');
    await settle();
    expect(m.sent.at(-1)).toEqual({ url: '/api/settings/data/reset', body: { apps: ['inventory'], confirm: 'Bar Pepe' } });
    expect(confirm.props('open')).toBe(false);
    expect(m.wrapper.get('[data-testid="reset-result"]').text()).toContain('Inventory — 14 rows removed');
    expect(m.wrapper.findAll('[data-testid="reset-section"]').map((row) => row.attributes('data-id'))).toEqual(['table']);
  });

  it('a refused reset stays in the dialog with the reason', async () => {
    const m = await panel((sent) =>
      sent.url.endsWith('/reset') && !sent.body.dry_run
        ? Response.json({ error: { code: 'invalid_payload', message: 'The name does not match.' } }, { status: 422 })
        : plan()(sent),
    );
    m.wrapper.get('[data-testid="reset-section-table"]').element.dispatchEvent(new CustomEvent('ionChange', { detail: { checked: true } }));
    await settle();
    await m.wrapper.get('[data-testid="reset-submit"]').trigger('click');
    await settle();
    const confirm = dialog(m, 'reset-confirm');
    confirm.vm.$emit('confirm');
    await settle();
    expect(confirm.props('open')).toBe(true);
    expect(confirm.props('error')).toMatchObject({ message: 'The name does not match.' });
  });

  it('in a business that shares its database, says why it cannot be emptied and offers no red button', async () => {
    const m = await panel(plan({ available: false }));
    expect(m.wrapper.get('[data-testid="reset-shared"]').text()).toContain('Your business still shares its database with others');
    expect(m.wrapper.find('[data-testid="reset-submit"]').exists()).toBe(false);
    expect(m.wrapper.find('[data-testid="reset-section-inventory"]').exists()).toBe(false);
    // What each section has is still told.
    expect(m.wrapper.findAll('[data-testid="reset-section"]')).toHaveLength(2);
  });

  it('says when there is nothing to reset, and when the plan could not be worked out (and retries)', async () => {
    let failing = true;
    const m = await panel((sent) =>
      failing ? Response.json({ error: { code: 'internal', message: 'down' } }, { status: 500 }) : plan({ sections: [] })(sent),
    );
    expect(m.wrapper.text()).toContain('What each section has could not be worked out.');
    failing = false;
    await m.wrapper.get('[data-testid="reset-retry"]').trigger('click');
    await settle();
    expect(m.wrapper.text()).toContain('There is nothing to reset: no section has data.');
  });
});
