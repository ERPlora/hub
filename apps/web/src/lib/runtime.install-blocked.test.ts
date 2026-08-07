// ADR-0060 (hub#68): instalar un módulo puede exigir COMPRAR una dependencia. El runtime
// responde 409 con `code: "install_blocked"` + `blocked_on` + `purchase`, y la UI tiene que poder
// ofrecer la compra. Antes, cualquier !res.ok se convertía en `Error('request-install X → 409')`:
// el usuario veía un número y no se enteraba de que solo le faltaba contratar un módulo.
import { describe, it, expect, vi, afterEach } from 'vitest';

import { requestInstall, InstallBlockedError } from './runtime';

/** Respuesta del runtime como la construye `request_install` en `crates/server/src/lib.rs`. */
function blockedResponse() {
  return {
    ok: false,
    status: 409,
    json: async () => ({
      ok: false,
      error: 'el módulo `verifactu` necesita módulos que este hub no tiene contratados: invoice',
      code: 'install_blocked',
      blocked_on: ['invoice'],
      purchase: [
        {
          module_id: 'invoice',
          module_type: 'premium',
          price: '9.00',
          currency: 'EUR',
          purchase_url: '/marketplace/invoice/',
        },
      ],
    }),
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('requestInstall · plan bloqueado (ADR-0060)', () => {
  it('lanza un InstallBlockedError que NOMBRA lo que falta comprar', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => blockedResponse()));

    const err = await requestInstall('verifactu', 'latest').then(
      () => null,
      (e) => e,
    );

    expect(err).toBeInstanceOf(InstallBlockedError);
    expect(err.code).toBe('install_blocked');
    expect(err.blockedOn).toEqual(['invoice']);
    // Lo que la UI necesita para ofrecer la compra, no un 409 pelado.
    expect(err.purchase[0]).toMatchObject({
      moduleId: 'invoice',
      price: '9.00',
      currency: 'EUR',
      purchaseUrl: '/marketplace/invoice/',
    });
    // El mensaje del runtime ya viene traducible/legible: se conserva.
    expect(err.message).toContain('invoice');
  });

  it('un fallo normal sigue siendo un Error corriente con su código estable', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: false,
        status: 502,
        json: async () => ({ ok: false, error: 'cloud: boom', code: 'install_cloud_unavailable' }),
      })),
    );

    const err = await requestInstall('inventory', 'latest').then(
      () => null,
      (e) => e,
    );

    expect(err).toBeInstanceOf(Error);
    expect(err).not.toBeInstanceOf(InstallBlockedError);
    expect(err.code).toBe('install_cloud_unavailable');
    expect(err.message).toContain('boom');
  });

  it('una instalación correcta devuelve el resultado sin tocar nada', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: true,
        status: 200,
        json: async () => ({
          ok: true,
          module_id: 'inventory',
          version: '1.0.0',
          status: 'installed',
        }),
      })),
    );

    await expect(requestInstall('inventory', 'latest')).resolves.toMatchObject({
      ok: true,
      module_id: 'inventory',
      status: 'installed',
    });
  });
});
