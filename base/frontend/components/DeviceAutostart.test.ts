// «Start on login» in Settings › General, inside «This device» (BASE-F120, ERPlora/app HUB_APP-F27): only in the
// computer app, off from the factory, painting what the operating system answers and never what was asked.
import { afterEach, describe, expect, it } from 'vitest';

import { flush, installedApp, leaveInstalledApp, mountBase } from '../__tests__/mount-base';
import DeviceAutostart from './DeviceAutostart.vue';

type Answers = Parameters<typeof installedApp>[1];

const TOGGLE = '[data-testid="device-autostart-toggle"]';
const ERROR = '[data-testid="device-autostart-error"]';

/** The computer app, whose operating system says `enabled` until a command changes it. */
function computer(enabled: boolean, answers: Answers = {}) {
  const os = { enabled };
  const invoke = installedApp('direct', {
    autostart_is_enabled: () => os.enabled,
    autostart_enable: () => (os.enabled = true),
    autostart_disable: () => (os.enabled = false),
    ...answers,
  });
  return { os, invoke };
}

async function mounted(locale: 'en' | 'es' = 'en') {
  const m = await mountBase(DeviceAutostart, { locale });
  await flush();
  return m;
}

/** The switch's element, whose `checked` and `disabled` are what the person sees. */
const toggle = (m: Awaited<ReturnType<typeof mounted>>) => m.wrapper.get(TOGGLE).element as HTMLElement & { checked: boolean; disabled: boolean };

/** A person's tap: the switch moves first, then it tells. */
async function flip(m: Awaited<ReturnType<typeof mounted>>, checked: boolean): Promise<void> {
  toggle(m).checked = checked;
  toggle(m).dispatchEvent(new CustomEvent('ionChange', { detail: { checked } }));
  await flush();
}

const asked = (invoke: ReturnType<typeof installedApp>) => invoke.mock.calls.map(([command]) => command);

afterEach(() => {
  leaveInstalledApp();
  document.body.innerHTML = '';
});

describe('DeviceAutostart', () => {
  it('is not painted in a browser', async () => {
    const m = await mounted();
    expect(m.wrapper.find('[data-testid="device-autostart"]').exists()).toBe(false);
  });

  it('is not painted on Android, whose app refuses the command on purpose', async () => {
    installedApp('play', { autostart_is_enabled: () => Promise.reject('autostart is desktop-only') });
    const m = await mounted();
    expect(m.wrapper.find('[data-testid="device-autostart"]').exists()).toBe(false);
  });

  it('on the computer it says what it is for and shows what the system says: off from the factory', async () => {
    computer(false);
    const m = await mounted('es');
    expect(m.wrapper.get(TOGGLE).text()).toBe('Arrancar al iniciar sesión');
    expect(m.wrapper.get('[data-testid="device-autostart"]').text()).toContain(
      'Abre ERPlora al iniciar sesión en este ordenador, para que los tiques siempre tengan dónde imprimirse.',
    );
    expect(toggle(m).checked).toBe(false);
  });

  it('shows it on when the system already starts it', async () => {
    computer(true);
    const m = await mounted();
    expect(m.wrapper.get(TOGGLE).text()).toBe('Start on login');
    expect(toggle(m).checked).toBe(true);
  });

  it('turning it on asks the system and shows its answer', async () => {
    const { invoke } = computer(false);
    const m = await mounted();
    await flip(m, true);
    expect(asked(invoke)).toEqual(['autostart_is_enabled', 'autostart_enable']);
    expect(toggle(m).checked).toBe(true);
    expect(m.wrapper.find(ERROR).exists()).toBe(false);
  });

  it('turning it off asks the system to stop it', async () => {
    const { invoke, os } = computer(true);
    const m = await mounted();
    await flip(m, false);
    expect(asked(invoke)).toEqual(['autostart_is_enabled', 'autostart_disable']);
    expect(os.enabled).toBe(false);
    expect(toggle(m).checked).toBe(false);
  });

  it('a system that did not change keeps the switch where the system is, not where it was moved', async () => {
    computer(false, { autostart_enable: () => false });
    const m = await mounted();
    await flip(m, true);
    expect(toggle(m).checked).toBe(false);
  });

  it('waits for the system while it changes', async () => {
    let answer: (value: boolean) => void = () => undefined;
    computer(false, { autostart_enable: () => new Promise<boolean>((resolve) => (answer = resolve)) });
    const m = await mounted();
    await flip(m, true);
    expect(toggle(m).disabled).toBe(true);
    answer(true);
    await flush();
    expect(toggle(m).disabled).toBe(false);
    expect(toggle(m).checked).toBe(true);
  });

  it('a refusal says it could not change, reads the system again and goes away with the next change', async () => {
    let refuse = true;
    const { invoke, os } = computer(false, {
      autostart_enable: () => (refuse ? Promise.reject('Access is denied.') : (os.enabled = true)),
    });
    const m = await mounted();
    await flip(m, true);
    expect(m.wrapper.get(ERROR).text()).toContain('Could not change the start on login setting.');
    expect(asked(invoke)).toEqual(['autostart_is_enabled', 'autostart_enable', 'autostart_is_enabled']);
    expect(toggle(m).checked).toBe(false);
    expect(toggle(m).disabled).toBe(false);

    refuse = false;
    await flip(m, true);
    expect(m.wrapper.find(ERROR).exists()).toBe(false);
    expect(toggle(m).checked).toBe(true);
  });

  it('a refusal after the system did change shows what the system says now', async () => {
    const { os } = computer(false, {
      autostart_enable: () => {
        os.enabled = true;
        return Promise.reject('could not read it back');
      },
    });
    const m = await mounted();
    await flip(m, true);
    expect(m.wrapper.find(ERROR).exists()).toBe(true);
    expect(toggle(m).checked).toBe(true);
  });
});
