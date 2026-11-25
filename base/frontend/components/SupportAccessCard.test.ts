import { formatDateTime } from '@erplora/ui/components';
import { toastSuccess } from '@erplora/ui/shell';
import { afterEach, describe, expect, it } from 'vitest';

import { EMPLOYEE, errorFrame, flush, subId } from '../__tests__/mount-base';
import { openSettingsCard, posted, switchOf } from '../__tests__/settings-card';
import type { SupportAccess } from '../operations/access';
import SupportAccessCard from './SupportAccessCard.vue';

const OP = 'base.support_access.get';
const OFF: SupportAccess = { enabled: false, can_change: true, updated_by: '', updated_at: null, visits: [] };
const ON: SupportAccess = { ...OFF, enabled: true, updated_by: 'Ana', updated_at: '2026-11-24T09:30:00Z' };

const open = (options: Parameters<typeof openSettingsCard>[1] = {}) => openSettingsCard(SupportAccessCard, options);
const toggle = (m: Parameters<typeof switchOf>[0]) => switchOf(m, 'support-access-toggle');

function switchTo(m: Parameters<typeof toggle>[0], checked: boolean): void {
  toggle(m).dispatchEvent(new CustomEvent('ionChange', { detail: { checked } }));
}

afterEach(() => {
  document.body.innerHTML = '';
});

describe('SupportAccessCard', () => {
  it('follows the setting live, off by default, in the person’s language', async () => {
    const m = await open({ locale: 'es' });
    expect(m.client.stream.subscriptions(OP).map((sub) => sub.params)).toEqual([{}]);
    expect(m.wrapper.find('[data-testid="support-access-loading"]').exists()).toBe(true);
    await m.result(m.call, OP, OFF);
    expect(m.wrapper.text()).toContain('Acceso de soporte');
    expect(m.wrapper.find('[data-testid="support-access-loading"]').exists()).toBe(false);
    expect(toggle(m).checked).toBe(false);
    expect(toggle(m).disabled).toBe(false);
  });

  it('turning it on saves it at once and says what it allows', async () => {
    const m = await open({ onApi: () => Response.json(ON) });
    await m.result(m.call, OP, OFF);
    switchTo(m, true);
    await flush();
    expect(posted(m)).toEqual([['/api/support-access/update', { enabled: true }]]);
    expect(toastSuccess).toHaveBeenCalledWith('Support access is on: ERPlora support can come in.');
    await m.result(m.call, OP, ON, 2);
    expect(toggle(m).checked).toBe(true);
  });

  it('turning it off says support can no longer come in', async () => {
    const m = await open({ onApi: () => Response.json(OFF) });
    await m.result(m.call, OP, ON);
    switchTo(m, false);
    await flush();
    expect(posted(m)).toEqual([['/api/support-access/update', { enabled: false }]]);
    expect(toastSuccess).toHaveBeenCalledWith('Support access is off: ERPlora support can no longer come in.');
  });

  it('says who changed it last and when', async () => {
    const m = await open();
    await m.result(m.call, OP, ON);
    expect(m.wrapper.get('[data-testid="support-access-changed"]').text()).toBe(
      `Last changed by Ana, ${formatDateTime('2026-11-24T09:30:00Z', 'en')}.`,
    );
  });

  it('while nobody has changed it, it says nothing about who did', async () => {
    const m = await open();
    await m.result(m.call, OP, OFF);
    expect(m.wrapper.find('[data-testid="support-access-changed"]').exists()).toBe(false);
  });

  it('lists who of support came in and when, the most recent first', async () => {
    const m = await open();
    const visits = [
      { person: 'Sara Soto', entered_at: '2026-11-24T10:00:00Z' },
      { person: 'Ivo Ruiz', entered_at: '2026-11-23T16:45:00Z' },
    ];
    await m.result(m.call, OP, { ...ON, visits });
    const rows = m.wrapper.findAll('[data-testid="support-visit"]');
    expect(rows.map((row) => [row.get('[data-testid="settings-row-title"]').text(), row.get('[data-testid="settings-row-hint"]').text()])).toEqual([
      ['Sara Soto', formatDateTime('2026-11-24T10:00:00Z', 'en')],
      ['Ivo Ruiz', formatDateTime('2026-11-23T16:45:00Z', 'en')],
    ]);
    expect(m.wrapper.find('[data-testid="support-visits-empty"]').exists()).toBe(false);
  });

  it('a single entry is a list of one, without the line for none', async () => {
    const m = await open();
    await m.result(m.call, OP, { ...ON, visits: [{ person: 'Sara Soto', entered_at: '2026-11-24T10:00:00Z' }] });
    expect(m.wrapper.findAll('[data-testid="support-visit"]')).toHaveLength(1);
    expect(m.wrapper.find('[data-testid="support-visits-empty"]').exists()).toBe(false);
  });

  it('while nobody of support has come in, it says so', async () => {
    const m = await open();
    await m.result(m.call, OP, ON);
    expect(m.wrapper.get('[data-testid="support-visits-empty"]').text()).toBe('Nobody from ERPlora support has come in yet.');
    expect(m.wrapper.findAll('[data-testid="support-visit"]')).toHaveLength(0);
  });

  it('whoever does not run the business sees it disabled, and why', async () => {
    const m = await open({ session: EMPLOYEE });
    await m.result(m.call, OP, { ...ON, can_change: false });
    expect(toggle(m).disabled).toBe(true);
    expect(m.wrapper.text()).toContain('Only who runs the business can change it.');
  });

  it('a change that cannot be saved says so and paints the switch again on the saved value', async () => {
    const m = await open({ onApi: () => Response.json({ error: { code: 'internal_error', message: 'x' } }, { status: 500 }) });
    await m.result(m.call, OP, OFF);
    const moved = toggle(m);
    switchTo(m, true);
    await flush();
    expect(m.wrapper.get('[data-testid="support-access-save-failed"]').text()).toContain('Could not save the change.');
    expect(toggle(m)).not.toBe(moved);
    expect(toggle(m).checked).toBe(false);
    expect(toastSuccess).not.toHaveBeenCalled();
  });

  it('a setting that cannot be read says so with «Retry»', async () => {
    const m = await open();
    m.call.push(errorFrame(subId(m.client, OP), 'internal_error'));
    await flush();
    expect(m.wrapper.text()).toContain('Could not load the support access.');
    expect(m.wrapper.find('[data-testid="support-access-toggle"]').exists()).toBe(false);
    expect(m.wrapper.find('[data-testid="support-access-retry"]').exists()).toBe(true);
  });
});
