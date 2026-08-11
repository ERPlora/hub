// `logout()` apaga siete subsistemas con `import()` dinámicos y NO espera a ninguno (es correcto:
// cerrar sesión no puede quedarse colgado de que cargue un chunk). Lo que sí importaba es que
// ninguno de esos siete se quedara como **promesa rechazada sin dueño**.
//
// El fallo real (2026-08-11): `vitest run` terminaba en rojo con
// `EnvironmentTeardownError: Cannot load '/src/lib/runtime.ts' … after the environment was torn
// down`, señalando la cadena `session.ts → dead-letter.ts → runtime.ts`. Un test hacía logout, el
// entorno se desmontaba antes de que el `import('./dead-letter')` resolviera, y el rechazo no tenía
// `catch`. No fallaba ninguna prueba —los 1179 tests pasaban— pero el proceso salía con código 1,
// así que el gate se caía por un error que no era de nadie. Y era invisible hasta que añadir
// CUALQUIER fichero de test movía el reparto entre workers lo justo para destaparlo.
//
// Contrato: en producción tampoco hay remedio para un chunk que no carga —el sondeo que se quería
// parar ya no hace nada sin sesión (`refreshDeadLetterCount` sale por `isAuthed`)—, así que el
// rechazo se traga a propósito y con comentario.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// Los seis que sí cargan. Se apagan de verdad; lo que se prueba es el séptimo.
vi.mock('./cloud', () => ({ runtimeLogout: vi.fn(), clearTokens: vi.fn() }));
vi.mock('./user-profile', () => ({ resetUserProfile: vi.fn() }));
vi.mock('./theme', () => ({ resetUserThemePreferences: vi.fn() }));
vi.mock('../i18n', () => ({ resetUserLocale: vi.fn() }));
vi.mock('./entitlement', () => ({ resetEntitlement: vi.fn() }));
vi.mock('./assistant-history', () => ({ clearAssistantHistory: vi.fn() }));
// El séptimo NO carga — exactamente lo que pasa cuando el entorno ya se desmontó (o cuando el
// navegador no puede traerse el chunk: red caída a mitad de un deploy).
vi.mock('./dead-letter', () => {
  throw new Error('chunk load failed');
});

import { logout } from './session';

describe('hub#714: logout no deja promesas rechazadas sueltas', () => {
  let seen: unknown[];
  const record = (reason: unknown): void => {
    seen.push(reason);
  };

  beforeEach(() => {
    seen = [];
    process.on('unhandledRejection', record);
  });
  afterEach(() => {
    process.off('unhandledRejection', record);
  });

  it('un subsistema que no se deja cargar no tumba el proceso', async () => {
    logout();
    // Dos vueltas de macrotarea: Node emite `unhandledRejection` al final del turno en el que el
    // rechazo se quedó sin manejador.
    await new Promise((r) => setTimeout(r, 20));
    await new Promise((r) => setTimeout(r, 20));

    expect(seen, `rechazos sin dueño: ${seen.map(String).join(' · ')}`).toEqual([]);
  });
});
