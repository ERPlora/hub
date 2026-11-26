// Tips → Settings (TIP-F01; WORKBOOK «Pantallas · Ajustes»): «Ask for a tip at the charge», which suggestion comes
// chosen, «Allow another amount» and, for each active payment method, its three suggestions, each a percentage or an
// amount; «Save» sends only what changed and says «Settings saved.». A suggestion that is wrong is said under its field
// and nothing is saved. Whoever may not change them reads them blocked. Loading, error, reconnecting and app inactive.
import { describe, expect, it } from 'vitest';

import { click, errorFrame, flush, ionChecked, ionValue } from '../../../../base/frontend/__tests__/mount-in-shell';
import { MANAGER, OWNER, mountTip } from '../__tests__/mount-tip';
import type { SettingsOut } from '../operations';
import SettingsPage from './SettingsPage.vue';

const OP = 'tip.settings.get';
const SETTINGS: SettingsOut = {
  enabled: false,
  allow_custom: true,
  preselected: 0,
  methods: [
    { method_id: 'm-cash', method_name: 'Cash', method_type: 'cash', suggestions: [{ percent: 3 }, { percent: 5 }, { percent: 10 }] },
    { method_id: 'm-card', method_name: 'Card', method_type: 'card', suggestions: [{ percent: 3 }, { percent: 5 }, { amount: 200 }] },
  ],
};

type Field = Element & Record<string, unknown>;

async function setup(locale: 'en' | 'es' = 'en', session = OWNER) {
  const m = await mountTip(SettingsPage, { path: '/tip/settings', locale, session });
  await m.live();
  const field = (testid: string) => m.inDoc(testid) as unknown as Field;
  const save = () => click(m.inDoc('tip-settings-save'));
  const posted = () => m.sent().filter((call) => call.path === '/api/tip/settings' && call.method !== 'GET');
  return { ...m, field, save, posted };
}

describe('SettingsPage: what it shows', () => {
  it('sits under «Tips» with its tabs; «Loading the settings…» until they come', async () => {
    const s = await setup();
    expect(s.find('tip-settings-loading').text()).toContain('Loading the settings…');
    await s.result(OP, SETTINGS);
    expect(s.find('tip-settings-loading').exists()).toBe(false);
    expect(s.find('tip-settings-heading').text()).toBe('Tips at the charge');
  });

  it('paints the settings as they are, and each method’s three suggestions', async () => {
    const s = await setup();
    await s.result(OP, SETTINGS);
    expect([s.field('tip-settings-enabled').checked, s.field('tip-settings-allow_custom').checked]).toEqual([false, true]);
    expect(s.field('tip-settings-preselected').value).toBe(0);
    const choices = [...(s.inDoc('tip-settings-preselected')?.querySelectorAll('ion-select-option') ?? [])].map((option) => option.textContent?.trim());
    expect(choices).toEqual(['No tip', 'Suggestion 1', 'Suggestion 2', 'Suggestion 3']);
    expect(s.find('tip-settings-method-m-cash').exists() && s.find('tip-settings-method-m-card').exists()).toBe(true);
    expect(s.field('tip-settings-m-card-2-value').value).toBe('2.00');
  });

  it('a business without active payment methods says so', async () => {
    const s = await setup();
    await s.result(OP, { ...SETTINGS, methods: [] });
    expect(s.find('tip-settings-no-methods').text()).toBe('Sales has no active payment method yet.');
  });
});

describe('SettingsPage: saving', () => {
  it('sends only what changed and says «Settings saved.»', async () => {
    const s = await setup();
    await s.result(OP, SETTINGS);
    s.answer(200, { ...SETTINGS, enabled: true, preselected: 2 });
    await ionChecked(s.inDoc('tip-settings-enabled'), true);
    await ionValue(s.inDoc('tip-settings-preselected'), 2);
    await s.save();
    expect(s.posted().map((call) => call.body)).toEqual([{ enabled: true, preselected: 2 }]);
    expect(s.find('tip-settings-saved').text()).toContain('Settings saved.');
  });

  it('a suggestion changed sends the suggestions of every method, a percentage as a number and an amount in cents', async () => {
    const s = await setup();
    await s.result(OP, SETTINGS);
    s.answer(200, SETTINGS);
    await ionValue(s.inDoc('tip-settings-m-card-0-value'), '4', 'ionInput');
    await s.save();
    expect(s.posted().map((call) => call.body)).toEqual([
      {
        methods: [
          { method_id: 'm-cash', suggestions: [{ percent: 3 }, { percent: 5 }, { percent: 10 }] },
          { method_id: 'm-card', suggestions: [{ percent: 4 }, { percent: 5 }, { amount: 200 }] },
        ],
      },
    ]);
  });

  it('a wrong suggestion is said under its field and nothing is saved; correcting it lifts the mark', async () => {
    const s = await setup();
    await s.result(OP, SETTINGS);
    await ionValue(s.inDoc('tip-settings-m-cash-2-value'), '5', 'ionInput');
    await s.save();
    expect(s.posted()).toEqual([]);
    expect(s.field('tip-settings-m-cash-2-value').errorText).toBe('That suggestion is already there.');
    await ionValue(s.inDoc('tip-settings-m-cash-2-value'), '150', 'ionInput');
    expect(s.field('tip-settings-m-cash-2-value').errorText).toBeFalsy();
    await s.save();
    expect(s.field('tip-settings-m-cash-2-value').errorText).toBe('Write a percentage from 1 to 100.');
  });

  it('a refusal of the server is said above «Save»', async () => {
    const s = await setup();
    await s.result(OP, SETTINGS);
    s.answer(409, { error: { code: 'tip.boom', message: 'That payment method is not available in this business.' } });
    await ionChecked(s.inDoc('tip-settings-allow_custom'), false);
    await s.save();
    expect(s.find('tip-settings-save-error').text()).toContain('That payment method is not available in this business.');
  });
});

describe('SettingsPage: who and when', () => {
  it('whoever may not change them reads them blocked, without «Save»', async () => {
    const s = await setup('en', MANAGER);
    await s.result(OP, SETTINGS);
    expect(s.find('tip-settings-read-only').text()).toContain('You do not have permission to change these settings.');
    expect(
      ['enabled', 'allow_custom', 'preselected', 'm-cash-0-kind', 'm-cash-0-value'].map((name) => s.field(`tip-settings-${name}`).disabled),
    ).toEqual([true, true, true, true, true]);
    expect(s.inDoc('tip-settings-save')).toBeNull();
  });

  it('a read that fails says so with «Retry»; an app turned off is said in its place', async () => {
    const s = await setup();
    s.net.lastStream().push(errorFrame(s.subId(OP), 'tip.boom'));
    await flush();
    expect(s.find('tip-settings-load-error').text()).toContain('The settings could not be loaded.');
    expect(s.find('tip-settings-retry').exists()).toBe(true);
    s.net.lastStream().push(errorFrame(s.subId(OP), 'app_inactive'));
    await flush();
    expect(s.find('tip-settings-inactive').exists()).toBe(true);
    expect(s.find('tip-settings-load-error').exists()).toBe(false);
  });

  it('speaks Spanish', async () => {
    const s = await setup('es');
    await s.result(OP, SETTINGS);
    expect(s.find('tip-settings-heading').text()).toBe('Propinas al cobrar');
    expect(s.inDoc('tip-settings-enabled')?.textContent?.trim()).toBe('Pedir propina al cobrar');
  });
});
