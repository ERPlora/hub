import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';

import {
  CAPABILITY_CATALOG,
  capabilitiesToConsent,
  capabilitiesFromIds,
  capabilityBreaksKey,
  capabilityMeta,
} from './module-capabilities';
import type { ModuleCapability } from './runtime';
import en from '../i18n/locales/en';
import es from '../i18n/locales/es';

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

  // hub#1096 / ADR-0196: el Bridge se retiró (hub#339/#340). La copia que quedó aquí nombraba
  // «a través del bridge» — la pieza que el dueño buscaría para instalarla ya no existe: es el
  // callejón sin salida que cerró printing#12 en la pantalla de Impresión. Hoy la cola de
  // impresión vive en el Hub y la drena erplora-app como host de impresión.
  it('la descripción de printer no nombra el bridge retirado: dice cola del Hub + erplora-app', () => {
    const meta = capabilityMeta('printer');
    expect(meta.label).toBe('Impresora');
    expect(meta.description).not.toMatch(/bridge/i);
    expect(meta.description).toMatch(/cola de impresión/);
    expect(meta.description).toMatch(/erplora-app/);
  });

  it('el espejo .ts y capability_meta de Rust dicen EXACTAMENTE lo mismo (una sola verdad)', () => {
    // El texto vive dos veces A PROPÓSITO (el server es la autoridad, esto es el fallback de
    // primera instalación — ver cabecera de module-capabilities.ts), pero tiene que ser UN texto:
    // si solo se corrige un lado, el dueño ve descripciones distintas antes y después de instalar.
    // Mismo patrón que bridge-token-retired.test.ts: el test lee la fuente que no puede ejecutar.
    const rs = readFileSync(
      new URL('../../../../crates/server/src/settings.rs', import.meta.url),
      'utf8',
    );
    const arm = rs.match(/"printer"\s*=>\s*\(\s*"Impresora"\s*,\s*"([^"]+)"/);
    expect(arm, 'no se encontró el brazo "printer" de capability_meta en settings.rs').not.toBeNull();
    expect(CAPABILITY_CATALOG.printer.description).toBe(arm?.[1]);
  });
});

// Regression test for ERPlora/hub#1174 — Ajustes → Permisos pintaba label + descripción + toggle y
// NADA decía qué deja de funcionar con el interruptor apagado. La frase de la consecuencia vive en
// UN sitio (este catálogo, por id de capability) y es una CLAVE i18n, no texto: la pantalla solo la
// traduce. Este es el guardia que impide que se añada una capability al core sin ella.
describe('capabilityBreaksKey — qué se rompe con el permiso denegado (hub#1174)', () => {
  /** Los ids que el SERVIDOR conoce: `capability_meta` en `crates/server/src/settings.rs`. */
  function serverCapabilityIds(): string[] {
    const rs = readFileSync(
      new URL('../../../../crates/server/src/settings.rs', import.meta.url),
      'utf8',
    );
    const body = rs.match(/fn capability_meta\(id: &str\)[\s\S]*?\n\}/);
    expect(body, 'no se encontró `fn capability_meta` en crates/server/src/settings.rs').not.toBeNull();
    return [...(body?.[0] ?? '').matchAll(/^\s*"([a-z_]+)" => \(/gm)].map((m) => m[1]).sort();
  }

  /** Resuelve `settings.capabilityBreaks.x` dentro de un catálogo de locale. */
  function lookup(catalogue: unknown, key: string): unknown {
    return key.split('.').reduce<unknown>(
      (node, part) => (node && typeof node === 'object' ? (node as Record<string, unknown>)[part] : undefined),
      catalogue,
    );
  }

  it('🔴 el espejo web conoce EXACTAMENTE las capabilities que el servidor declara', () => {
    // Sin esto, una capability nueva del core entra sin etiqueta y sin consecuencia, y el fallo
    // solo se ve en la pantalla del cliente.
    expect(Object.keys(CAPABILITY_CATALOG).sort()).toEqual(serverCapabilityIds());
  });

  it('🔴 CADA capability declara qué se rompe si no se concede — el fallo nombra la que falta', () => {
    const missing = serverCapabilityIds().filter((id) => !CAPABILITY_CATALOG[id]?.breaksKey);
    expect(
      missing,
      `capabilities sin «qué se rompe» en CAPABILITY_CATALOG: ${missing.join(', ')}`,
    ).toEqual([]);
  });

  it('🔴 la consecuencia está traducida en en Y en es — el fallo nombra la clave que falta', () => {
    // ADR-0055/0199: inglés fuente + su `es`. Una clave sin traducción sale como clave cruda en la
    // tarjeta, que es peor que no decir nada.
    for (const id of [...serverCapabilityIds(), 'some_future_capability']) {
      const key = capabilityBreaksKey(id);
      for (const [locale, catalogue] of [['en', en], ['es', es]] as const) {
        const text = lookup(catalogue, key);
        expect(typeof text, `falta ${key} en ${locale}.ts (capability ${id})`).toBe('string');
        expect(text, `${key} está vacía en ${locale}.ts`).not.toBe('');
      }
    }
  });

  it('una capability desconocida cae en la consecuencia genérica, nunca en una clave inventada', () => {
    // Un id que este espejo no conoce tiene que decir algo: un aviso en blanco grita sin informar.
    expect(capabilityBreaksKey('some_future_capability')).toBe(
      capabilityBreaksKey('another_future_capability'),
    );
    expect(capabilityBreaksKey('certificate')).not.toBe(capabilityBreaksKey('printer'));
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
