import { describe, expect, it } from 'vitest';

import type { AppRow } from '../operations/apps';
import { appActions, appSwitch, type AppsTableState } from './apps-table';

function app(fields: Partial<AppRow> = {}): AppRow {
  return {
    id: 'flow',
    name: 'Flows',
    icon: 'ion:cube-outline',
    category: 'sales',
    category_label: 'Sales',
    summary: '',
    premium: false,
    right: 'free',
    state: 'on',
    chosen: true,
    path: '/flow/home',
    requires: [],
    required_by: [],
    refusal: null,
    mandatory: false,
    ...fields,
  };
}
/** The keys a test reads back instead of the words. */
const t = (key: string, values?: Record<string, unknown>) => (values ? `${key}(${Object.values(values).join(',')})` : key);
const owner = (extra: Partial<AppsTableState> = {}): AppsTableState => ({ t, mayManage: true, mayBuy: true, pending: null, ...extra });
const ids = (state: AppsTableState, row: AppRow) => appActions(state).filter((a) => a.hidden?.(row) !== true).map((a) => a.id);

describe('appSwitch: the switch of an app', () => {
  const read = (state: AppsTableState, row: AppRow) => {
    const s = appSwitch(state);
    return { checked: s.checked(row), disabled: s.disabled?.(row), busy: s.busy?.(row), note: s.note?.(row) ?? null, tone: s.noteTone?.(row) };
  };

  it('on for an app on or being set up; off for one off, failed or without its right', () => {
    const on = (state: AppRow['state']) => appSwitch(owner()).checked(app({ state }));
    expect([on('on'), on('creating'), on('off'), on('failed'), on('blocked')]).toEqual([true, true, false, false, false]);
  });

  it('named with the app and its state', () => {
    const s = appSwitch(owner());
    expect([s.label(app()), s.label(app({ state: 'off' }))]).toEqual([
      'base.appsPage.toggle.labelOn(Flows)',
      'base.appsPage.toggle.labelOff(Flows)',
    ]);
  });

  it('moves when the app can be turned off, on or retried; never one refused, being set up or without its right', () => {
    const disabled = (row: AppRow) => read(owner(), row).disabled;
    expect([disabled(app()), disabled(app({ state: 'off' })), disabled(app({ state: 'failed' }))]).toEqual([false, false, false]);
    expect([disabled(app({ refusal: 'Never off.' })), disabled(app({ state: 'off', refusal: 'Not here.' })), disabled(app({ state: 'blocked' }))]).toEqual([
      true,
      true,
      true,
    ]);
    expect(read(owner(), app({ state: 'creating' }))).toMatchObject({ busy: true });
  });

  it('while one change is sent, its switch waits and the others cannot move', () => {
    const state = owner({ pending: 'flow' });
    expect(read(state, app())).toMatchObject({ busy: true });
    expect(read(state, app({ id: 'task' }))).toMatchObject({ busy: false, disabled: true });
  });

  it('says why: a refusal, a failure in red, where a paid app is bought; nothing otherwise', () => {
    expect(read(owner(), app({ refusal: 'Never off.' }))).toMatchObject({ note: 'Never off.', tone: 'muted' });
    expect(read(owner(), app({ state: 'failed' }))).toMatchObject({ note: 'base.appBlocked.failed.heading(Flows)', tone: 'danger' });
    expect(read(owner({ mayBuy: false }), app({ state: 'blocked' }))).toMatchObject({ note: 'base.appsPage.buyWhere' });
    expect(read(owner(), app({ state: 'blocked' })).note).toBeNull();
    expect(read(owner(), app()).note).toBeNull();
  });

  it('who does not run the business has no switch, and reads only where a paid app is bought', () => {
    const employee = owner({ mayManage: false, mayBuy: false });
    expect(appSwitch(employee).hidden?.(app())).toBe(true);
    expect(read(employee, app({ refusal: 'Never off.' })).note).toBeNull();
    expect(read(employee, app({ state: 'failed' })).note).toBeNull();
    expect(read(employee, app({ state: 'blocked' })).note).toBe('base.appsPage.buyWhere');
  });
});

describe('appActions: what a row offers besides its switch', () => {
  it('an app on with a screen: «Open»', () => {
    expect(ids(owner(), app())).toEqual(['open']);
    expect(ids(owner(), app({ path: null }))).toEqual([]);
  });

  it('a paid app without its right: «Upgrade plan», with its text, only for whoever may buy it', () => {
    expect(ids(owner(), app({ state: 'blocked', path: null }))).toEqual(['plans']);
    expect(ids(owner({ mayBuy: false }), app({ state: 'blocked', path: null }))).toEqual([]);
    expect(appActions(owner()).find((a) => a.id === 'plans')).toMatchObject({ showLabel: true, label: 'base.appsPage.buy' });
  });

  it('a failed app: «Retry», with its text, and giving it up from «⋮»; one being set up can be given up too', () => {
    expect(ids(owner(), app({ state: 'failed', path: null }))).toEqual(['retry', 'off']);
    expect(ids(owner(), app({ state: 'creating', path: null }))).toEqual(['off']);
    expect(appActions(owner()).find((a) => a.id === 'retry')).toMatchObject({ showLabel: true });
    expect(appActions(owner()).find((a) => a.id === 'off')).toMatchObject({ menuOnly: true });
  });

  it('who does not run the business: only «Open»', () => {
    expect(ids(owner({ mayManage: false }), app({ state: 'failed', path: null }))).toEqual([]);
  });

  it('every action has a baked icon and a label', () => {
    for (const action of appActions(owner())) expect([action.icon?.startsWith('ion:'), typeof action.label]).toEqual([true, 'string']);
  });
});
