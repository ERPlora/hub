import { describe, expect, it } from 'vitest';
import { PROFILE_ROUTE } from './routes';

describe('rutas del shell', () => {
  it('mantiene el perfil personal fuera de los ajustes del Hub', () => {
    expect(PROFILE_ROUTE).toBe('/profile');
    expect(PROFILE_ROUTE).not.toBe('/settings');
  });
});
