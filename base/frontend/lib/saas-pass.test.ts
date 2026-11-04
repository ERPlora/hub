// The pass to erplora.com (BASE-F11; ACCOUNTS-F29 of the SaaS): «Upgrade plan» and «Manage on erplora.com» ask the Hub
// for a pass at the click and open its address, so the person arrives already signed in. A browser blocks a window opened
// after an `await`, so the blank tab opens in the click and gets its address later; the installed app has no tabs, and
// hands the address to the device's browser. Whatever goes wrong, the usual address opens: it still works, asking to
// sign in.
import { afterEach, beforeEach, describe, expect, it, type MockInstance, vi } from 'vitest';
import { defineComponent, h } from 'vue';

import { flush, installedApp, leaveInstalledApp, mountBase, tap } from '../__tests__/mount-base';
import { SIGN_TIMEOUT_MS, type SaasPassNext, useSaasPass } from './saas-pass';

const USUAL = 'https://erplora.com/dashboard/store/plans?business=b1';
const SIGNED = 'https://erplora.com/hub-pass/?pass=abc%3A123';

const Door = defineComponent({
  props: { next: { type: String, default: 'plan' } },
  setup(props) {
    const { openSaasPass } = useSaasPass();
    return () =>
      h('a', {
        'data-testid': 'door',
        href: USUAL,
        onClick: (event: Event) => openSaasPass(props.next as SaasPassNext, USUAL, event),
      });
  },
});

/** The blank tab a browser gives back: the test reads where it was sent. */
function aTab() {
  return { opener: {} as unknown, location: { href: 'about:blank' } };
}

let open: MockInstance<typeof window.open>;
let tab: ReturnType<typeof aTab>;

beforeEach(() => {
  tab = aTab();
  open = vi.spyOn(window, 'open').mockReturnValue(tab as unknown as Window);
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  leaveInstalledApp();
});

const signed = () => Response.json({ url: SIGNED });
const refused = () => Response.json({ error: { code: 'base.saas_pass_needs_account', message: 'No.' } }, { status: 403 });

describe('useSaasPass in a browser', () => {
  it('opens the blank tab in the click, before the answer, and keeps the link from opening another', async () => {
    let answer: (response: Response) => void = () => {};
    const m = await mountBase(Door, { onApi: () => new Promise<Response>((resolve) => (answer = resolve)) });

    const seen = tap(m.wrapper.get('[data-testid="door"]').element);

    expect(open).toHaveBeenCalledTimes(1);
    expect(open).toHaveBeenCalledWith('about:blank', '_blank');
    expect(seen.defaultPrevented).toBe(true);
    expect(tab.location.href).toBe('about:blank');

    answer(signed());
    await flush();
    expect(tab.location.href).toBe(SIGNED);
  });

  it('the new tab never reaches back to the Hub', async () => {
    const m = await mountBase(Door, { onApi: signed });

    tap(m.wrapper.get('[data-testid="door"]').element);

    expect(tab.opener).toBeNull();
  });

  it.each(['plan', 'business'])('asks the operation for a pass to %s', async (next) => {
    const m = await mountBase(Door, { props: { next }, onApi: signed });

    tap(m.wrapper.get('[data-testid="door"]').element);
    await flush();

    const [call] = m.net.api;
    expect(call.url).toContain('/api/saas-pass');
    expect(call.init.method?.toUpperCase()).toBe('POST');
    expect(JSON.parse(call.init.body as string)).toEqual({ next });
  });

  it('when the browser blocks the tab, the link itself opens the usual address and nothing is signed', async () => {
    open.mockReturnValue(null);
    const m = await mountBase(Door, { onApi: signed });

    const seen = tap(m.wrapper.get('[data-testid="door"]').element);
    await flush();

    expect(seen.defaultPrevented).toBe(false);
    expect(m.net.api).toEqual([]);
  });

  it('when the operation refuses, the tab goes to the usual address, with no alarm', async () => {
    const error = vi.spyOn(console, 'error').mockImplementation(() => {});
    const m = await mountBase(Door, { onApi: refused });

    tap(m.wrapper.get('[data-testid="door"]').element);
    await flush();

    expect(tab.location.href).toBe(USUAL);
    expect(document.querySelector('ion-toast')).toBeNull();
    expect(error).toHaveBeenCalled();
  });

  it('when the network fails, the tab goes to the usual address', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    const m = await mountBase(Door, { onApi: () => Promise.reject(new TypeError('offline')) });

    tap(m.wrapper.get('[data-testid="door"]').element);
    await flush();

    expect(tab.location.href).toBe(USUAL);
  });

  it('when the answer never comes, the tab is not left blank: past its time it goes to the usual address', async () => {
    vi.useFakeTimers();
    let answer: (response: Response) => void = () => {};
    const m = await mountBase(Door, { onApi: () => new Promise<Response>((resolve) => (answer = resolve)) });

    tap(m.wrapper.get('[data-testid="door"]').element);
    await vi.advanceTimersByTimeAsync(SIGN_TIMEOUT_MS - 1);
    expect(tab.location.href).toBe('about:blank');
    await vi.advanceTimersByTimeAsync(1);
    expect(tab.location.href).toBe(USUAL);

    // An answer that comes too late sends the person nowhere else.
    answer(signed());
    await vi.advanceTimersByTimeAsync(0);
    expect(tab.location.href).toBe(USUAL);
  });
});

describe('useSaasPass in the installed app', () => {
  it('opens no window: the address goes to the device’s browser once it is signed', async () => {
    const invoke = installedApp('direct');
    const m = await mountBase(Door, { onApi: signed });

    const seen = tap(m.wrapper.get('[data-testid="door"]').element);
    expect(seen.defaultPrevented).toBe(true);
    await flush();

    expect(open).not.toHaveBeenCalled();
    expect(invoke).toHaveBeenCalledWith('open_external_url', { url: SIGNED });
  });

  it('when the operation refuses, the usual address goes to the device’s browser', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    const invoke = installedApp('direct');
    const m = await mountBase(Door, { onApi: refused });

    tap(m.wrapper.get('[data-testid="door"]').element);
    await flush();

    expect(invoke).toHaveBeenCalledWith('open_external_url', { url: USUAL });
  });
});
