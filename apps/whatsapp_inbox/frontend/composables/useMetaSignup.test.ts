// The life of Meta's window (WHATSAPP_INBOX-F01): opened in the click, followed until Meta says which account and
// number were chosen and erplora.com's page brings the code back, then connected through door 11 with both, as they
// came; closed, cancelled, refused or blocked, it says so and connects nothing.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { effectScope } from 'vue';

import type { SignupOptions } from '../lib/metaSignup';
import { CLOSE_GRACE_MS, SESSION_WAIT_MS, useMetaSignup } from './useMetaSignup';

const OPTIONS: SignupOptions = {
  app_id: '1481226093843982',
  config_id: '1101452998214123',
  graph_version: 'v25.0',
  redirect_uri: 'https://erplora.com/whatsapp/return',
};
const FINISH = { waba_id: '102290129340398', phone_number_id: '106540352242922', business_id: '2729063490586005' };

let popup: { closed: boolean; close: () => void };
let opened: string[];

beforeEach(() => {
  vi.useFakeTimers();
  popup = { closed: false, close: vi.fn() };
  opened = [];
  vi.spyOn(window, 'open').mockImplementation((url) => {
    opened.push(String(url));
    return popup as unknown as Window;
  });
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

function start(connect = vi.fn().mockResolvedValue({ connected: true })) {
  const scope = effectScope();
  const signup = scope.run(() => useMetaSignup(connect, { hostname: () => 'a.localhost' }))!;
  signup.open(OPTIONS);
  const state = new URL(opened[0]).searchParams.get('state') as string;
  return { signup, connect, state, scope };
}

const meta = (event: string, data: Record<string, unknown>) =>
  window.dispatchEvent(
    new MessageEvent('message', { origin: 'https://www.facebook.com', data: JSON.stringify({ type: 'WA_EMBEDDED_SIGNUP', event, data }) }),
  );
const back = (data: Record<string, unknown>, origin = 'https://erplora.com') =>
  window.dispatchEvent(new MessageEvent('message', { origin, data: { type: 'erplora.whatsapp.signup', ...data } }));

describe('useMetaSignup', () => {
  it('opens Meta’s window in the click and connects what it gave, as it came', async () => {
    const { signup, connect, state } = start();
    expect(opened).toHaveLength(1);
    expect(state).toMatch(/^a\.[0-9a-f]{32}$/);
    expect(signup.step.value).toBe('waiting');

    meta('FINISH', FINISH);
    back({ state, code: 'AQD-one-time' });
    await vi.runAllTimersAsync();

    expect(connect).toHaveBeenCalledWith({ code: 'AQD-one-time', event: 'FINISH', ...FINISH });
    expect(signup.step.value).toBe('idle');
    expect(signup.result.value).toEqual({ connected: true });
    expect(signup.failure.value).toBeNull();
  });

  it('a code that arrives before Meta says the account waits for it a moment', async () => {
    const { connect, state } = start();
    back({ state, code: 'AQD' });
    await vi.advanceTimersByTimeAsync(SESSION_WAIT_MS / 2);
    meta('FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING', { waba_id: '1' });
    await vi.runAllTimersAsync();
    expect(connect).toHaveBeenCalledWith({ code: 'AQD', event: 'FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING', waba_id: '1', phone_number_id: '', business_id: '' });
  });

  it('without the account Meta chose, nothing is connected', async () => {
    const { signup, connect, state } = start();
    back({ state, code: 'AQD' });
    await vi.advanceTimersByTimeAsync(SESSION_WAIT_MS + 1);
    expect(connect).not.toHaveBeenCalled();
    expect(signup.failure.value).toEqual({ reason: 'no_account', message: '' });
    expect(signup.step.value).toBe('idle');
  });

  it('a window closed without finishing connects nothing and says so', async () => {
    const { signup, connect } = start();
    popup.closed = true;
    await vi.advanceTimersByTimeAsync(CLOSE_GRACE_MS + 1000);
    expect(signup.failure.value).toEqual({ reason: 'closed', message: '' });
    expect(signup.step.value).toBe('idle');
    expect(connect).not.toHaveBeenCalled();
  });

  it('Meta cancelling, or refusing with its reason, connects nothing', async () => {
    const cancelled = start();
    meta('CANCEL', { current_step: 'PHONE_NUMBER_SETUP' });
    expect(cancelled.signup.failure.value).toEqual({ reason: 'closed', message: '' });
    cancelled.scope.stop();

    opened = [];
    const refused = start();
    meta('CANCEL', { error_message: 'Number already in use' });
    expect(refused.signup.failure.value).toEqual({ reason: 'meta', message: 'Number already in use' });
    refused.scope.stop();

    opened = [];
    const denied = start();
    back({ state: denied.state, error: 'access_denied', error_description: 'Permissions error' });
    expect(denied.signup.failure.value).toEqual({ reason: 'meta', message: 'Permissions error' });
    expect(denied.connect).not.toHaveBeenCalled();
  });

  it('a code from another origin or another attempt is never connected', async () => {
    const { connect, state } = start();
    meta('FINISH', FINISH);
    back({ state, code: 'AQD' }, 'https://evil.example');
    back({ state: 'a.ffffffffffffffffffffffffffffffff', code: 'AQD' });
    await vi.advanceTimersByTimeAsync(SESSION_WAIT_MS + 1);
    expect(connect).not.toHaveBeenCalled();
  });

  it('erplora.com refusing the connection says its reason', async () => {
    const { signup, state } = start(vi.fn().mockRejectedValue(new Error('Meta did not accept the connection: expired.')));
    meta('FINISH', FINISH);
    back({ state, code: 'AQD' });
    await vi.runAllTimersAsync();
    expect(signup.failure.value).toEqual({ reason: 'connect', message: 'Meta did not accept the connection: expired.' });
    expect(signup.step.value).toBe('idle');
  });

  it('a browser that blocks the window says so', () => {
    vi.spyOn(window, 'open').mockReturnValue(null);
    const scope = effectScope();
    const signup = scope.run(() => useMetaSignup(vi.fn(), { hostname: () => 'a.localhost' }))!;
    signup.open(OPTIONS);
    expect(signup.failure.value).toEqual({ reason: 'blocked', message: '' });
    expect(signup.step.value).toBe('idle');
  });

  it('stops listening when the screen goes', async () => {
    const { connect, state, scope } = start();
    scope.stop();
    meta('FINISH', FINISH);
    back({ state, code: 'AQD' });
    await vi.runAllTimersAsync();
    expect(connect).not.toHaveBeenCalled();
  });
});
