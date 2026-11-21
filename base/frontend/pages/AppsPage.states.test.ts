// What an app's switch says beforehand: refused, mandatory, being set up or failed (BASE-F14, F21, F22, F25).
import { toastSuccess } from '@erplora/ui/shell';
import { describe, expect, it, vi } from 'vitest';

import { app } from '../__tests__/app-row';
import { appActionLabel, flip, freshEachTest, LIST, type Mounted, noteOf, open, PLANS, pressAppAction, rowOf, STORE, switchState, TAX } from '../__tests__/apps-page';
import { confirmSpy } from '../__tests__/apps-page-spies';
import { EMPLOYEE } from '../__tests__/mount-base';
import type { AppList, AppRow } from '../operations/apps';

vi.mock('@erplora/ui/components', async (importOriginal) => (await import('../__tests__/apps-page-spies')).componentsWithConfirmSpy(importOriginal));
vi.mock('../lib/access', async (importOriginal) => (await import('../__tests__/apps-page-spies')).accessWithSessionSpy(importOriginal));

freshEachTest();

const state = (m: Mounted, id: string) => rowOf(m, id).find('[data-testid="apps-state"]');
const posted = (m: Mounted) => m.net.api.map((c) => [c.url, JSON.parse(String(c.init.body ?? '{}')) as Record<string, unknown>]);

describe('what an app refuses is said beforehand (hub#618, hub#694)', () => {
  const NEVER_OFF = 'VeriFactu can’t be turned off once it’s on.';
  const ONLY_THERE = 'VeriFactu is only for businesses in Spain.';
  const OFF_HERE = app('verifactu', { name: 'VeriFactu', state: 'off', chosen: false, path: null, refusal: ONLY_THERE });

  it('one on that never goes off: its switch stays on and cannot move, it says why and stays «Active»', async () => {
    const m = await open('/apps');
    await m.result(m.call, 'base.app.list', { ...LIST, apps: [app('verifactu', { name: 'VeriFactu', refusal: NEVER_OFF }), TAX] });
    expect(switchState(m, 'verifactu')).toMatchObject({ checked: true, disabled: true });
    expect(noteOf(m, 'verifactu').text()).toBe(NEVER_OFF);
    expect(state(m, 'verifactu').text()).toBe('Active');
    // «Open» is still there: only turning it off is refused.
    expect(await appActionLabel(m, 'verifactu', 'open')).toBe('Open: VeriFactu');
    // The app next to it goes on as ever.
    expect(switchState(m, 'tax').disabled).toBe(false);
    expect(noteOf(m, 'tax').exists()).toBe(false);
  });

  it('one off that does not go on: its switch stays off and cannot move, it is not available, and why', async () => {
    const m = await open('/apps#all');
    await m.result(m.call, 'base.app.list', { ...LIST, apps: [OFF_HERE] });
    expect(switchState(m, 'verifactu')).toMatchObject({ checked: false, disabled: true });
    expect(state(m, 'verifactu').text()).toBe('Not available');
    expect(noteOf(m, 'verifactu').text()).toBe(ONLY_THERE);
  });

  it('in Spanish too', async () => {
    const m = await open('/apps#all', { locale: 'es' });
    await m.result(m.call, 'base.app.list', { ...LIST, apps: [OFF_HERE] });
    expect(state(m, 'verifactu').text()).toBe('No disponible');
  });

  it('who does not run the business can do nothing about it: not the reason, only that it is not available', async () => {
    const m = await open('/apps#all', { session: EMPLOYEE });
    await m.result(m.call, 'base.app.list', { ...LIST, apps: [OFF_HERE, app('invoice', { name: 'Invoicing', refusal: NEVER_OFF })] });
    expect(m.wrapper.find('.data-table__cell-note, .data-table__card-note').exists()).toBe(false);
    expect(state(m, 'verifactu').text()).toBe('Not available');
  });
});

describe('what the business’s country requires on (hub#997)', () => {
  const MANDATORY_HERE = 'Taxes is mandatory for businesses in Spain: it can’t be turned off.';
  const label = (m: Mounted, id: string) => rowOf(m, id).find('[data-testid="apps-mandatory"]');
  const TAX_ON = app('tax', { name: 'Taxes', chosen: false, required_by: ['sale'], mandatory: true, refusal: MANDATORY_HERE });
  const SALE = app('sale', { name: 'Sales', requires: ['customer', 'tax'] });
  const CUSTOMER = app('customer', { name: 'Customers', chosen: false, required_by: ['sale'] });
  const VERIFACTU_OFF = app('verifactu', { name: 'VeriFactu', state: 'off', chosen: false, path: null, mandatory: true });
  const MINE: AppList = { ...LIST, max_apps: 20, apps: [SALE, TAX_ON, CUSTOMER, VERIFACTU_OFF] };

  it('«My apps» says it is mandatory in the business’s country, keeps its switch on and still, and says why', async () => {
    const m = await open('/apps');
    await m.result(m.call, 'base.app.list', MINE);
    expect(label(m, 'tax').text()).toBe('Mandatory in Spain');
    expect(state(m, 'tax').text()).toBe('Active');
    expect(switchState(m, 'tax')).toMatchObject({ checked: true, disabled: true });
    expect(noteOf(m, 'tax').text()).toBe(MANDATORY_HERE);
    // Another app goes on as ever, with no label.
    expect(label(m, 'sale').exists()).toBe(false);
    expect(switchState(m, 'sale').disabled).toBe(false);
  });

  it('one off is labelled too in «Add apps», still «Off» and offered to turn on', async () => {
    const m = await open('/apps#all');
    await m.result(m.call, 'base.app.list', MINE);
    expect(label(m, 'verifactu').text()).toBe('Mandatory in Spain');
    expect(state(m, 'verifactu').text()).toBe('Off');
    expect(switchState(m, 'verifactu')).toMatchObject({ checked: false, disabled: false });
  });

  it('turning off the app it came with never names it among what goes off with it', async () => {
    confirmSpy.mockResolvedValue(false);
    const m = await open('/apps');
    await m.result(m.call, 'base.app.list', MINE);
    await flip(m, 'sale', false);
    const asked = confirmSpy.mock.calls[0][0];
    expect(asked.message).toContain('Customers');
    expect(asked.message).not.toContain('Taxes');
  });

  it('in Spanish, with the country by its Spanish name', async () => {
    const m = await open('/apps', { locale: 'es' });
    await m.result(m.call, 'base.app.list', { ...MINE, country_name: 'España' });
    expect(label(m, 'tax').text()).toBe('Obligatoria en España');
  });

  it('whoever does not run the business reads the label too, not the reason', async () => {
    const m = await open('/apps', { session: EMPLOYEE });
    await m.result(m.call, 'base.app.list', MINE);
    expect(label(m, 'tax').text()).toBe('Mandatory in Spain');
    expect(noteOf(m, 'tax').exists()).toBe(false);
  });
});

describe('an app whose tables the business’s database is still getting', () => {
  const FLOW = app('flow', { name: 'Flows', state: 'off', chosen: false, path: null });
  const FLOW_CREATING = { ...FLOW, state: 'creating' as const, chosen: true };
  const FLOW_FAILED = { ...FLOW, state: 'failed' as const, chosen: true };
  const TASK = app('task', { name: 'Tasks' });
  const listOf = (...apps: AppRow[]): AppList => ({ apps, country_name: 'Spain', store_url: STORE, plan_url: PLANS, max_apps: 20, enabled: 1 });
  const creating = () => Response.json({ app: 'flow', state: 'creating', chosen: true, along: [] }, { status: 202 });

  it('switched on and answered «creating», it says it is being set up; its switch waits, on, until it is', async () => {
    const m = await open('/apps#all', { onApi: creating });
    await m.result(m.call, 'base.app.list', listOf(TASK, FLOW));
    await flip(m, 'flow', true);
    expect(posted(m)).toEqual([['/api/apps/enable', { app: 'flow' }]]);
    expect(vi.mocked(toastSuccess).mock.calls[0][0]).toBe('Turning on Flows… It will be ready in a moment.');
    await m.result(m.call, 'base.app.list', listOf(TASK, FLOW_CREATING), 2);
    expect([state(m, 'flow').text(), state(m, 'flow').attributes('data-tone')]).toEqual(['Turning on…', 'info']);
    expect(switchState(m, 'flow')).toMatchObject({ checked: true, disabled: true });
    expect(rowOf(m, 'flow').find('ion-spinner').exists()).toBe(true);
    expect(await appActionLabel(m, 'flow', 'open')).toBeUndefined();
    await m.result(m.call, 'base.app.list', listOf(TASK, { ...FLOW, state: 'on', chosen: true, path: '/flow/home' }), 3);
    expect(state(m, 'flow').text()).toBe('Active');
    expect(switchState(m, 'flow')).toMatchObject({ checked: true, disabled: false });
  });

  it('«My apps» lists the ones being set up and the ones that failed, with their state and no «Open»', async () => {
    const m = await open();
    await m.result(m.call, 'base.app.list', listOf(TASK, FLOW_CREATING, { ...FLOW_FAILED, id: 'website', name: 'Website' }));
    expect(m.wrapper.findAll('[data-testid="apps-row"]').map((row) => row.attributes('data-id'))).toEqual(['task', 'flow', 'website']);
    expect([state(m, 'flow').text(), state(m, 'website').text(), state(m, 'website').attributes('data-tone')]).toEqual([
      'Turning on…',
      'Could not turn on',
      'danger',
    ]);
    expect(await appActionLabel(m, 'flow', 'open')).toBeUndefined();
  });

  it('one that could not be turned on is off, says so, and offers «Retry», which sets it up again', async () => {
    const m = await open('/apps', { onApi: creating });
    await m.result(m.call, 'base.app.list', listOf(TASK, FLOW_FAILED));
    expect(switchState(m, 'flow')).toMatchObject({ checked: false, disabled: false });
    expect(noteOf(m, 'flow').text()).toBe('Flows could not be set up');
    expect(noteOf(m, 'flow').classes().some((c) => c.endsWith('--danger'))).toBe(true);
    expect(rowOf(m, 'flow').find('[data-testid="apps-row-flow-retry"]').text()).toBe('Retry');
    await pressAppAction(m, 'flow', 'retry');
    expect(posted(m)).toEqual([['/api/apps/retry', { app: 'flow' }]]);
    expect(vi.mocked(toastSuccess).mock.calls[0][0]).toBe('Turning on Flows… It will be ready in a moment.');
  });

  it('its switch turned on retries too', async () => {
    const m = await open('/apps', { onApi: creating });
    await m.result(m.call, 'base.app.list', listOf(TASK, FLOW_FAILED));
    await flip(m, 'flow', true);
    expect(posted(m)).toEqual([['/api/apps/retry', { app: 'flow' }]]);
  });

  it('a retry refused says why, on screen', async () => {
    const m = await open('/apps', {
      onApi: () => Response.json({ error: { code: 'base.app_not_failed', message: 'This app is not waiting to be set up again.' } }, { status: 409 }),
    });
    await m.result(m.call, 'base.app.list', listOf(TASK, FLOW_FAILED));
    await pressAppAction(m, 'flow', 'retry');
    expect(m.wrapper.find('[data-testid="apps-refused"]').text()).toContain('This app is not waiting to be set up again.');
  });

  it('one that could not be turned on can be given up instead, from «⋮»', async () => {
    confirmSpy.mockResolvedValue(true);
    const m = await open('/apps', { onApi: () => Response.json({ app: 'flow', state: 'off', chosen: false, along: [] }) });
    await m.result(m.call, 'base.app.list', listOf(TASK, FLOW_FAILED));
    expect(await appActionLabel(m, 'flow', 'off')).toBe('Turn off');
    await pressAppAction(m, 'flow', 'off');
    expect(posted(m)).toEqual([['/api/apps/disable', { app: 'flow' }]]);
  });

  it('one being set up can be given up too, in Spanish «Desactivar»', async () => {
    confirmSpy.mockResolvedValue(true);
    const m = await open('/apps', { locale: 'es', onApi: () => Response.json({ app: 'flow', state: 'off', chosen: false, along: [] }) });
    await m.result(m.call, 'base.app.list', listOf(TASK, FLOW_CREATING));
    expect(await appActionLabel(m, 'flow', 'off')).toBe('Desactivar');
    await pressAppAction(m, 'flow', 'off');
    expect(posted(m)).toEqual([['/api/apps/disable', { app: 'flow' }]]);
  });

  it('who does not run the business sees the state, without «Retry» nor a switch', async () => {
    const m = await open('/apps', { session: EMPLOYEE });
    await m.result(m.call, 'base.app.list', listOf(TASK, FLOW_FAILED));
    expect(state(m, 'flow').text()).toBe('Could not turn on');
    expect(await appActionLabel(m, 'flow', 'retry')).toBeUndefined();
    expect(rowOf(m, 'flow').find('ion-toggle').exists()).toBe(false);
  });

  it('in Spanish', async () => {
    const m = await open('/apps', { locale: 'es', onApi: creating });
    await m.result(m.call, 'base.app.list', listOf(TASK, FLOW_CREATING, { ...FLOW_FAILED, id: 'website', name: 'Web' }));
    expect([state(m, 'flow').text(), state(m, 'website').text()]).toEqual(['Activándose…', 'No se ha podido activar']);
    expect(noteOf(m, 'website').text()).toBe('No se ha podido preparar Web');
    expect(rowOf(m, 'website').find('[data-testid="apps-row-website-retry"]').text()).toBe('Reintentar');
    await pressAppAction(m, 'website', 'retry');
    expect(vi.mocked(toastSuccess).mock.calls[0][0]).toBe('Activando Web… Estará lista en un momento.');
  });
});
