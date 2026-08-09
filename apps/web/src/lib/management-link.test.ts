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
// it look wired while never reacting to a login.
vi.mock('./session', async () => {
  const { ref } = await import('vue');
  return { user: ref<{ permissions?: string[] } | null>(null) };
});

const { openExternal } = vi.hoisted(() => ({ openExternal: vi.fn(async () => {}) }));
vi.mock('./open-external', () => ({ openExternal }));

import { canOpenManagement, managementUrl, openManagement } from './management-link';
import { user } from './session';

const session = user as unknown as { value: { permissions?: string[] } | null };

beforeEach(() => {
  config.cloudApiUrl = 'https://erplora.com';
  config.hubId = 'hub-1';
  session.value = null;
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

    expect(openExternal).toHaveBeenCalledWith(
      'https://erplora.com/dashboard/?view=advanced&hub=hub-1&utm_source=hub',
    );
    expect(assign).not.toHaveBeenCalled();
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
});
