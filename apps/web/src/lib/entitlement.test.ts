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

import { isModuleBlocked, isModuleEntitled, resetEntitlement, resolveEntitlement } from './entitlement';

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
