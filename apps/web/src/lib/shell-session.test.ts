// ADR-0159 (cliente fino): dentro del shell Tauri la PWA es la MISMA PWA cloud que en el
// navegador — la sesión ya NO es "independiente local" por el mero hecho de correr en Tauri.
// (Eso era del producto Hub Local/SQLite, retirado por ADR-0154: un 401 definitivo del refresh
// debe expirar la sesión y mandar a /login exactamente igual que en el navegador.)
import { describe, expect, it, vi } from 'vitest';

vi.mock('./shell', () => ({ beginRequest: vi.fn(), endRequest: vi.fn() }));
vi.mock('./device', () => ({
  // Simulamos estar DENTRO del shell Tauri.
  isTauri: () => true,
  loginHeaders: vi.fn(async () => ({ 'X-Client-Type': 'hub-desktop' })),
}));

import { hasIndependentLocalSession } from './cloud';
import { config, DEV_HUB_ID } from './config';

describe('ADR-0159: sesión dentro del shell Tauri', () => {
  it('correr en Tauri NO convierte la sesión en "independiente local"', () => {
    // Hub cloud real (hub_id ≠ dev): en el navegador esto es false; en el shell debe seguir
    // siendo false — el shell es un cliente fino de la MISMA PWA cloud.
    const prev = config.hubId;
    config.hubId = '11111111-2222-3333-4444-555555555555';
    try {
      expect(hasIndependentLocalSession()).toBe(false);
    } finally {
      config.hubId = prev;
    }
  });

  it('el runtime local/dev sigue siendo independiente (sin cambios)', () => {
    const prev = config.hubId;
    config.hubId = DEV_HUB_ID;
    try {
      expect(hasIndependentLocalSession()).toBe(true);
    } finally {
      config.hubId = prev;
    }
  });
});
