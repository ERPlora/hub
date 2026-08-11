import { describe, expect, it } from 'vitest';

import {
  CAPABILITY_CATALOG,
  capabilitiesToConsent,
  capabilitiesFromIds,
  capabilityMeta,
} from './module-capabilities';
import type { ModuleCapability } from './runtime';

// Lo que devuelve el runtime para un módulo que YA estuvo instalado.
function runtimeCap(id: string, granted = false): ModuleCapability {
  return { id, label: `L:${id}`, description: `D:${id}`, requested: true, granted };
}

describe('capabilityMeta — el catálogo de etiquetas', () => {
  it('conoce las cinco capabilities del core', () => {
    // Espejo de `crates/server/src/settings.rs::capability_meta`. `manage_flows` (hub#714) nunca
    // se añadió al espejo del frontend: era el fleco que dejaba mudo al modal.
    expect(Object.keys(CAPABILITY_CATALOG).sort()).toEqual(
      ['certificate', 'manage_flows', 'network', 'notify', 'printer'],
    );
  });

  it('describe manage_flows en términos de lo que el dueño arriesga', () => {
    const meta = capabilityMeta('manage_flows');
    expect(meta.label).toBe('Administrar automatizaciones');
    expect(meta.description).not.toBe('');
  });

  it('una capability desconocida sale con un texto genérico, nunca vacía', () => {
    // Un permiso nuevo del core que este espejo aún no conozca tiene que APARECER igualmente:
    // esconderlo sería volver a instalar sin preguntar, que es justo el fallo de pm#132.
    const meta = capabilityMeta('some_future_capability');
    expect(meta.label).not.toBe('');
    expect(meta.description).not.toBe('');
  });
});

describe('capabilitiesFromIds — del catálogo Cloud al modal', () => {
  it('convierte los ids que declara el manifest en filas del modal', () => {
    expect(capabilitiesFromIds(['manage_flows'])).toEqual([
      {
        id: 'manage_flows',
        label: 'Administrar automatizaciones',
        description: capabilityMeta('manage_flows').description,
        requested: true,
        granted: false,
      },
    ]);
  });

  it('🔴 nada llega concedido: el catálogo declara, no concede', () => {
    // ADR-0079 es default-deny. Si esto naciera en `true`, instalar equivaldría a conceder.
    for (const cap of capabilitiesFromIds(['manage_flows', 'network', 'printer'])) {
      expect(cap.granted).toBe(false);
      expect(cap.requested).toBe(true);
    }
  });

  it('sin ids no hay nada que consentir', () => {
    expect(capabilitiesFromIds([])).toEqual([]);
  });
});

describe('capabilitiesToConsent — de quién nos fiamos para preguntar', () => {
  it('🔴 PRIMERA instalación: el runtime no lo conoce, así que manda el catálogo', () => {
    // El fallo entero de pm#132: aquí el runtime devuelve vacío y hasta hoy eso significaba
    // «instala sin preguntar». Ahora significa «pregúntaselo al catálogo».
    expect(capabilitiesToConsent([], ['manage_flows'])).toEqual(capabilitiesFromIds(['manage_flows']));
  });

  it('el runtime también falla entero (módulo desconocido → error): sigue mandando el catálogo', () => {
    expect(capabilitiesToConsent(null, ['manage_flows'])).toEqual(capabilitiesFromIds(['manage_flows']));
  });

  it('reinstalación: el runtime SÍ lo conoce y es la autoridad', () => {
    // Sus etiquetas vienen del servidor (traducidas y al día); el espejo local es solo respaldo.
    const fromRuntime = [runtimeCap('manage_flows', true)];
    expect(capabilitiesToConsent(fromRuntime, ['manage_flows'])).toEqual(fromRuntime);
  });

  it('el runtime solo aporta lo que el módulo PIDE, no todo el catálogo', () => {
    const mixed = [runtimeCap('manage_flows'), { ...runtimeCap('printer'), requested: false }];
    expect(capabilitiesToConsent(mixed, [])).toEqual([runtimeCap('manage_flows')]);
  });

  it('un módulo que no pide nada no abre modal por ninguna de las dos vías', () => {
    expect(capabilitiesToConsent([], [])).toEqual([]);
    expect(capabilitiesToConsent(null, [])).toEqual([]);
  });
});
