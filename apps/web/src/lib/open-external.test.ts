// Tests del helper `openExternal` (deep-link de compra, Fase 4): el Hub es una PWA pura, así que
// siempre abre la URL en una pestaña nueva con `noopener`. Entorno node puro: se stubbea `window`.
import { afterEach, describe, expect, it, vi } from 'vitest';

import { openExternal } from './open-external';

describe('openExternal', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('abre la URL en pestaña nueva con noopener', async () => {
    const open = vi.fn();
    vi.stubGlobal('window', { open });

    await openExternal('https://erplora.com/dashboard/billing/modules/pos/?hub=h1&utm_source=hub');

    expect(open).toHaveBeenCalledWith(
      'https://erplora.com/dashboard/billing/modules/pos/?hub=h1&utm_source=hub',
      '_blank',
      'noopener',
    );
  });
});
