// @vitest-environment happy-dom
// The setup document is re-read when the shell language changes (hub#2356).
//
// The runtime translates the apps' items of `hub.setup.status` into the VIEWER's language. A
// document read before the person switched language keeps those items in the old one while the
// shell's own labels switch at once — and the blocking strip is painted on every screen, Profile
// included, which is exactly where the language is changed. Without a re-read the strip mixed the
// two languages until the next navigation.
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('./module-loader', () => ({ loadInstalledManifests: vi.fn() }));

import { refreshSetupStatusOnLocaleChange, SETUP_STATUS_QUERY } from './setup-status';

function client() {
  return { query: vi.fn().mockResolvedValue([{ items: [], total: 0, pending: 0 }]) };
}

function changeLocale(locale: string): void {
  window.dispatchEvent(new CustomEvent('erplora:locale-changed', { detail: { locale } }));
}

let stop: (() => void) | undefined;
afterEach(() => {
  stop?.();
  stop = undefined;
});

describe('the setup document follows the shell language (hub#2356)', () => {
  it('re-reads the query when the language changes', () => {
    const c = client();
    stop = refreshSetupStatusOnLocaleChange(
      () => c as never,
      () => true,
    );

    changeLocale('en');

    expect(c.query).toHaveBeenCalledTimes(1);
    expect(c.query).toHaveBeenCalledWith(SETUP_STATUS_QUERY);
  });

  it('does not re-read when the language did not actually change (saving the theme republishes it)', () => {
    const c = client();
    stop = refreshSetupStatusOnLocaleChange(
      () => c as never,
      () => true,
    );

    changeLocale('en');
    changeLocale('en');
    changeLocale('es');

    expect(c.query).toHaveBeenCalledTimes(2);
  });

  it('does not ask the runtime without a session (signing out resets the language too)', () => {
    const c = client();
    stop = refreshSetupStatusOnLocaleChange(
      () => c as never,
      () => false,
    );

    changeLocale('en');

    expect(c.query).not.toHaveBeenCalled();
  });

  it('stops listening once unsubscribed', () => {
    const c = client();
    refreshSetupStatusOnLocaleChange(
      () => c as never,
      () => true,
    )();

    changeLocale('en');

    expect(c.query).not.toHaveBeenCalled();
  });
});

describe('the shell subscribes it once, for the whole session (hub#2356)', () => {
  it('App.vue — always mounted — wires the re-read to the session', async () => {
    const { readFileSync } = await import('node:fs');
    const { join } = await import('node:path');
    const app = readFileSync(join(import.meta.dirname, '..', 'App.vue'), 'utf8');
    expect(app).toContain('refreshSetupStatusOnLocaleChange(getClient, () => isAuthed.value);');
  });
});
