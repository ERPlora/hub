// Bloqueo por revalidación híbrida (ADR-0114 §6, hub#119): el bloque `revalidation`
// del proxy /api/entitlement alimenta isModuleBlocked(), que la UI usa para
// deshabilitar el WC del módulo con CTA "Gestionar suscripción".
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('./cloud', () => ({
  cloudEntitlement: vi.fn(async () => ({
    modules: [
      { moduleId: 'inventory', tier: 'free', version: '1.0.0' },
      { moduleId: 'whatsapp_inbox', tier: 'premium', version: '1.0.0' },
    ],
    blockedModules: ['whatsapp_inbox'],
  })),
  getAccessToken: vi.fn(() => 'token'),
  triggerHubGone: vi.fn(),
}));

const { invokeTauriSpy } = vi.hoisted(() => ({ invokeTauriSpy: vi.fn(async () => null) }));

vi.mock('./device', () => ({
  // ADR-0159: el gate es SIEMPRE el camino web (cloudEntitlement); el comando Tauri
  // `validate_entitlement` fue retirado con el producto local (ADR-0154).
  invokeTauri: invokeTauriSpy,
}));

vi.mock('./config', () => ({
  config: { hubId: 'hub-1', cloudApiUrl: 'https://cloud.test' },
}));

import { cloudEntitlement } from './cloud';
import {
  entitlementOffline,
  entitlementStatus,
  isModuleBlocked,
  isModuleEntitled,
  resetEntitlement,
  resolveEntitlement,
} from './entitlement';

const cloudEntitlementMock = vi.mocked(cloudEntitlement);
const RESOLVED = {
  modules: [
    { moduleId: 'inventory', tier: 'free', version: '1.0.0' },
    { moduleId: 'whatsapp_inbox', tier: 'premium', version: '1.0.0' },
  ],
  blockedModules: ['whatsapp_inbox'],
};

describe('entitlement: bloqueo por revalidación', () => {
  beforeEach(() => {
    resetEntitlement();
  });

  it('sin resolver: nada bloqueado (estricto a false) y entitlement permisivo', () => {
    expect(isModuleBlocked('whatsapp_inbox')).toBe(false);
    expect(isModuleEntitled('whatsapp_inbox')).toBe(true);
  });

  it('tras resolver: los blocked_modules del proxy quedan bloqueados', async () => {
    await resolveEntitlement();
    expect(isModuleBlocked('whatsapp_inbox')).toBe(true);
    expect(isModuleBlocked('inventory')).toBe(false);
    // Bloqueado ≠ no-entitled: el módulo sigue en el token (instalado y con datos);
    // solo se deshabilita su uso hasta restaurar la suscripción.
    expect(isModuleEntitled('whatsapp_inbox')).toBe(true);
  });

  it('resetEntitlement limpia el bloqueo', async () => {
    await resolveEntitlement();
    resetEntitlement();
    expect(isModuleBlocked('whatsapp_inbox')).toBe(false);
  });

  it('ADR-0159: el gate ya no invoca al shell (validate_entitlement retirado)', async () => {
    invokeTauriSpy.mockClear();
    await resolveEntitlement();
    expect(invokeTauriSpy).not.toHaveBeenCalled();
  });
});

// hub#1167 — el rate-limit del SaaS no puede borrar lo que el shell ya sabía.
//
// El runtime amortigua el 429 sirviendo su último entitlement bueno, así que al navegador ya casi
// nunca le llega. Pero cuando le llega (hub recién arrancado, sin nada cacheado que servir) el
// shell tiene que CONSERVAR el snapshot anterior en vez de volver a «sin resolver»: perderlo es lo
// que dejaba la pantalla de Apps diciendo que no hay apps mientras el runtime tenía varias
// (hub#1193), porque un `modules=[]` transitorio se lee como una verdad.
describe('entitlement: un fallo del Cloud no borra lo ya resuelto (hub#1167)', () => {
  beforeEach(() => {
    resetEntitlement();
    cloudEntitlementMock.mockReset();
    cloudEntitlementMock.mockResolvedValue(RESOLVED);
  });

  it('un 429 posterior conserva el entitlement anterior y solo marca offline', async () => {
    await resolveEntitlement();
    expect(entitlementStatus.value).toBe('unlocked');

    cloudEntitlementMock.mockRejectedValueOnce(new Error('runtime /api/entitlement → 429'));
    await resolveEntitlement();

    // Lo resuelto SIGUE en pie: ni se olvida qué módulos hay, ni cuáles están bloqueados.
    expect(entitlementStatus.value).toBe('unlocked');
    expect(isModuleEntitled('inventory')).toBe(true);
    expect(isModuleBlocked('whatsapp_inbox')).toBe(true);
    // Y el fallo queda VISIBLE para la UI, que es lo que distingue «no pude preguntar» de «no hay».
    expect(entitlementOffline.value).toBe(true);
  });

  it('un módulo NO entitled sigue sin estarlo tras el fallo: no se abre la mano por un 429', async () => {
    cloudEntitlementMock.mockResolvedValue({ modules: RESOLVED.modules, blockedModules: [] });
    await resolveEntitlement();
    expect(isModuleEntitled('un_modulo_que_no_compramos')).toBe(false);

    cloudEntitlementMock.mockRejectedValueOnce(new Error('runtime /api/entitlement → 429'));
    await resolveEntitlement();

    expect(isModuleEntitled('un_modulo_que_no_compramos')).toBe(false);
  });

  it('sin nada resuelto todavía, un fallo deja el shell PERMISIVO (no bloquea el arranque)', async () => {
    cloudEntitlementMock.mockRejectedValueOnce(new Error('runtime /api/entitlement → 429'));
    await resolveEntitlement();

    expect(entitlementStatus.value).toBe('unknown');
    expect(isModuleEntitled('inventory')).toBe(true);
    expect(entitlementOffline.value).toBe(true);
  });

  it('un refresco bueno posterior borra la marca de offline', async () => {
    await resolveEntitlement();
    cloudEntitlementMock.mockRejectedValueOnce(new Error('runtime /api/entitlement → 429'));
    await resolveEntitlement();
    expect(entitlementOffline.value).toBe(true);

    await resolveEntitlement();

    expect(entitlementOffline.value).toBe(false);
  });
});
