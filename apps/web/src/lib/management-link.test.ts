// hub#364 — the door from the till to MANAGEMENT, which is not a screen of this app: it is
// erplora.com. Three things are being pinned here, and each one is a way the door can betray
// whoever opens it:
//
//   - **Where it goes.** The link carries `view=advanced`, which is the hub's half of the ONE
//     switch of PLAN step 8 (the SaaS half is the "Simple view" toggle, saas#1159). Without the
//     marker the switch is a ratchet: `view_mode` can be set to `simple` and never back.
//   - **How it opens: THIS tab, never a new one.** On a till there may be no tab bar to come back
//     through — and inside the installed app `window.open` has no window to open (no shell/opener
//     plugin, and Tauri's webview does not spawn one), so a new-tab door is a door that does
//     nothing when pressed. Navigating in place always leaves Back, and the way back is a feature
//     of the destination (the SaaS enters the hub).
//   - **Who sees it.** `hub.administer` (ADR-0248), the permission the core already owns, read
//     from the session the runtime resolved. A waiter has no business — and often no account — at
//     erplora.com.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// A mutable stand-in for the boot-time config: `hubId` is resolved from the runtime at boot
// (`bootHubContext`), so the URL must be built when it is ASKED for, not when this module loads.
// `vi.hoisted` because the mock factory is lifted above every other statement in this file.
const { config } = vi.hoisted(() => ({
  config: { cloudApiUrl: 'https://erplora.com', hubId: 'hub-1' },
}));
vi.mock('./config', () => ({ config }));

// A real `ref`: `canOpenManagement` is a computed over the session, and a plain object would make
// it look wired while never reacting to a login. `hasPermission` reads from that same ref — the
// wildcard rule lives there now (hub#506) — so the mock exposes it over the same mutable state.
//
// The mock's surface is EXACTLY the module's: the second half of the lock (hub#1400) — HOW the
// person at the till proved who they are — goes in through `setHubSession`, the one funnel the five
// real login paths already use, and never through a handle invented for the test. A mock that
// exports what the module does not is how a suite stays green over an import that does not exist.
vi.mock('./session', async () => {
  const { computed, ref } = await import('vue');
  const user = ref<{ permissions?: string[] } | null>(null);
  const credentialKind = ref('');
  return {
    user,
    CREDENTIAL_CLOUD: 'cloud',
    openedWithCloudLogin: computed(() => credentialKind.value === 'cloud'),
    // Mirrors the real signature: omitting the kind is "it does not say", not "it was a password".
    setHubSession: (token: string | null, kind?: string | null) => {
      credentialKind.value = token ? (kind ?? '') : '';
    },
    hasPermission: (permission: string) => {
      const granted = user.value?.permissions ?? [];
      return granted.includes('*') || granted.includes(permission);
    },
  };
});

const { openExternal } = vi.hoisted(() => ({ openExternal: vi.fn(async () => {}) }));
vi.mock('./open-external', () => ({ openExternal }));

// The one-time pass the runtime mints (pm#196). Mocked, not stubbed through `fetch`, because what
// this file is about is which address the door ends up opening.
const { runtimeManagementHandoff } = vi.hoisted(() => ({
  runtimeManagementHandoff: vi.fn(async () => 'https://erplora.com/auth/handoff/code-abc/?next=%2Fdashboard%2F'),
}));
vi.mock('./cloud', () => ({ runtimeManagementHandoff }));

// A pass that cannot be minted must not fail MUTE: the door still opens, and the reason is reported.
const { reportClientError } = vi.hoisted(() => ({ reportClientError: vi.fn() }));
vi.mock('./error-report', () => ({ reportClientError }));

import { canOpenManagement, managementPath, managementUrl, openManagement } from './management-link';
import { user, setHubSession } from './session';

const session = user as unknown as { value: { permissions?: string[] } | null };

beforeEach(() => {
  config.cloudApiUrl = 'https://erplora.com';
  config.hubId = 'hub-1';
  session.value = null;
  setHubSession('runtime-token', 'cloud');
  openExternal.mockClear();
  runtimeManagementHandoff.mockClear();
  runtimeManagementHandoff.mockResolvedValue(
    'https://erplora.com/auth/handoff/code-abc/?next=%2Fdashboard%2F',
  );
  reportClientError.mockClear();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('managementUrl', () => {
  it('points at the SaaS management panel and asks it to remember the advanced view', () => {
    expect(managementUrl()).toBe(
      'https://erplora.com/dashboard/?view=advanced&hub=hub-1&utm_source=hub',
    );
  });

  it('names the hub it came from, escaped, so the panel can land on that business', () => {
    config.hubId = 'a b/c&d';

    expect(managementUrl()).toBe(
      'https://erplora.com/dashboard/?view=advanced&hub=a%20b%2Fc%26d&utm_source=hub',
    );
  });

  it('follows the configured Cloud base, so a dev hub does not send anyone to production', () => {
    config.cloudApiUrl = 'http://127.0.0.1:8001';

    expect(managementUrl()).toBe(
      'http://127.0.0.1:8001/dashboard/?view=advanced&hub=hub-1&utm_source=hub',
    );
  });

  it('reads the hub id when asked, not when the module loaded', () => {
    config.hubId = 'resolved-at-boot';

    expect(managementUrl()).toContain('hub=resolved-at-boot');
  });
});

describe('openManagement', () => {
  // Esto navegaba la VENTANA ACTUAL, y el comentario que lo justificaba decía que «navegar en el
  // sitio siempre deja Atrás, en toda superficie». **En la app instalada es falso**: la webview no
  // tiene chrome, ni botón de atrás, ni pestañas — el usuario aterrizaba en el SaaS y se quedaba
  // encerrado ahí, sin vuelta. Reportado por Ioan probando la app de escritorio (2026-08-09).
  //
  // Su otra premisa también había caducado: decía que dentro de la app `window.open` no abre nada.
  // Era cierto ANTES de hub#475, que es exactamente lo que arregló — `openExternal` sale por el
  // shell (`open_external_url`) en la app y abre pestaña en el navegador. Una sola puerta, las dos
  // superficies.
  //
  // Regla de Ioan: **la app nunca navega al SaaS en su ventana.** Pestaña nueva en navegador,
  // navegador del sistema en la app instalada.
  it('sale por la puerta de fuera — la app NUNCA se navega a sí misma al SaaS', async () => {
    const assign = vi.fn();
    vi.stubGlobal('window', { location: { assign } });

    await openManagement();

    expect(openExternal).toHaveBeenCalledTimes(1);
    expect(assign).not.toHaveBeenCalled();
  });

  // pm#196 — the half that actually mattered. The address went to the system browser as it stood,
  // and inside the installed app that browser is a different cookie jar from the webview: the owner
  // typed their password AND their second factor again, right before paying.
  it('trades the till session for a one-time address, so the browser lands already signed in', async () => {
    await openManagement();

    expect(runtimeManagementHandoff).toHaveBeenCalledWith(managementPath());
    expect(openExternal).toHaveBeenCalledWith(
      'https://erplora.com/auth/handoff/code-abc/?next=%2Fdashboard%2F',
    );
  });

  it('asks for the panel it would have opened, marker and all — the pass must not lose the destination', async () => {
    config.hubId = 'a b/c&d';

    await openManagement();

    expect(runtimeManagementHandoff).toHaveBeenCalledWith(
      '/dashboard/?view=advanced&hub=a%20b%2Fc%26d&utm_source=hub',
    );
  });

  // A door that goes dead when the pass cannot be minted is worse than today's, which at least
  // opened the panel. So it degrades to exactly today's behaviour — and says why, because a failure
  // nobody can see is a failure that never gets fixed.
  it('still opens the panel when the pass cannot be minted, and reports why', async () => {
    runtimeManagementHandoff.mockRejectedValue(new Error('handoff_unavailable'));

    await openManagement();

    expect(openExternal).toHaveBeenCalledWith(
      'https://erplora.com/dashboard/?view=advanced&hub=hub-1&utm_source=hub',
    );
    expect(reportClientError).toHaveBeenCalledTimes(1);
    expect(reportClientError.mock.calls[0][0].message).toContain('handoff');
  });

  it('does not turn an empty answer into an address', async () => {
    runtimeManagementHandoff.mockResolvedValue('');

    await openManagement();

    expect(openExternal).toHaveBeenCalledWith(
      'https://erplora.com/dashboard/?view=advanced&hub=hub-1&utm_source=hub',
    );
  });
});

describe('canOpenManagement', () => {
  it('is closed to a session that cannot administer the hub', () => {
    session.value = { permissions: ['pos.sale.create'] };

    expect(canOpenManagement.value).toBe(false);
  });

  it('opens for the permission the core already owns', () => {
    session.value = { permissions: ['pos.sale.create', 'hub.administer'] };

    expect(canOpenManagement.value).toBe(true);
  });

  it('honours the wildcard the shell grants an owner', () => {
    session.value = { permissions: ['*'] };

    expect(canOpenManagement.value).toBe(true);
  });

  it('is closed before anyone has signed in', () => {
    session.value = null;

    expect(canOpenManagement.value).toBe(false);
  });

  it('is closed to a session whose permissions never arrived', () => {
    session.value = {};

    expect(canOpenManagement.value).toBe(false);
  });

  // hub#1400, the lock, and the control that stops the escalation: a PIN is a credential of the
  // SHIFT — short, memorable, typed in front of people — and ADR-0226 already says the local user's
  // credential is never administrative. Turning it into the key to the billing panel would hand the
  // business's money to whoever opens the register. `hub.administer` is a permission of the ROLE and
  // does not answer this question, so it is necessary and NOT sufficient.
  it('stays shut for a PIN session, even when its role administers the hub', () => {
    session.value = { permissions: ['hub.administer'] };
    setHubSession('runtime-token', 'pin');

    expect(canOpenManagement.value).toBe(false);
  });

  it('stays shut for a PIN session holding the owner wildcard', () => {
    session.value = { permissions: ['*'] };
    setHubSession('runtime-token', 'pin');

    expect(canOpenManagement.value).toBe(false);
  });

  it('stays shut for a badge session', () => {
    session.value = { permissions: ['*'] };
    setHubSession('runtime-token', 'badge');

    expect(canOpenManagement.value).toBe(false);
  });

  // What a session opened before this shipped looks like: the login answered nothing, so the kind
  // never reached `setHubSession`. Showing the door to a session the runtime will then refuse is
  // precisely what hub#1400 forbids — it would promise something it does not deliver. It cures
  // itself when that session expires.
  it('stays shut when the session never said how it was opened', () => {
    session.value = { permissions: ['*'] };
    setHubSession('runtime-token');

    expect(canOpenManagement.value).toBe(false);
  });
});
