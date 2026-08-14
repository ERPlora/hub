// @vitest-environment happy-dom
//
// Un módulo actualizado tiene que LLEGAR al navegador (hub#935).
//
// Estas dos frases no son la misma, y confundirlas era el bug:
//
//   1. «el servidor manda el código nuevo» — medido, y era CIERTO;
//   2. «la pantalla ejecuta el código nuevo» — medido, y era FALSO.
//
// En la misma carga de página de un hub real, con el navegador recién arrancado:
//
//   fetch('/modules/flows/dist/flows.esm.js', {cache:'reload'})  → el código NUEVO
//   customElements.get('erp-flows-editor').prototype             → el código VIEJO
//
// El manifest decía 0.1.7 y la pantalla ejecutaba 0.1.6. El `import()` iba a la MISMA url que la
// versión anterior, y esa url estaba resuelta en caché (el borde cachea `.js` cuando el origen no
// declara nada: `cf-cache-status: HIT`, `age: 236`). El fallo es MUDO: nada en la UI lo delata.
//
// Un `?v=` no arregla nada — el borde de esta zona ignora la query para la clave de caché. Lo que
// ninguna caché puede ignorar es una RUTA distinta. Así que la versión va en la ruta, y este fichero
// fija exactamente eso: **dos versiones de un módulo son dos direcciones distintas**. No comprueba
// que el servidor sirva bien (eso es `crates/server/tests/module_bundle_cache.rs`); comprueba lo
// otro, lo que faltaba: a QUÉ dirección va el navegador.
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('./runtime', () => ({ RUNTIME_URL: '', runtimeHeaders: () => ({}) }));
vi.mock('./icons', () => ({ moduleIconRegistry: (i: Record<string, string>) => i }));
vi.mock('ionicons', () => ({ addIcons: () => {} }));
vi.mock('../i18n', () => ({ getLocale: () => 'en' }));
vi.mock('./entitlement', () => ({ isModuleEntitled: () => true }));

import { loadInstalledManifests, loadMenu } from './module-loader';

/** Un item de `/api/navigation`. `version` ausente = un runtime anterior a hub#935. */
function navItem(moduleId: string, version?: string) {
  return {
    module_id: moduleId,
    module_name: moduleId,
    id: `${moduleId}-main`,
    label: moduleId,
    icon: null,
    component: `erp-${moduleId}`,
    ...(version === undefined ? {} : { module_version: version }),
  };
}

/** `fetch` de mentira que además APUNTA todas las urls pedidas (es lo que se está midiendo). */
function stubFetch(navData: unknown[], manifests: Record<string, unknown>) {
  const urls: string[] = [];
  const fetchMock = vi.fn(async (url: string) => {
    urls.push(url);
    if (url.startsWith('/api/navigation')) {
      return {
        ok: true,
        status: 200,
        json: async () => ({ ok: true, data: navData, active_modules: navData.length }),
      } as unknown as Response;
    }
    const match = /^\/modules\/([^/]+)(?:\/v\/[^/]+)?\/module\.json$/.exec(url);
    if (match && manifests[match[1]]) {
      return { ok: true, status: 200, json: async () => manifests[match[1]] } as unknown as Response;
    }
    return { ok: false, status: 404, json: async () => ({}) } as unknown as Response;
  });
  vi.stubGlobal('fetch', fetchMock);
  return urls;
}

const manifestAt = (version: string) => ({
  name: 'Flows',
  version,
  ui: { entry: 'dist/flows.esm.js' },
});

beforeEach(() => {
  vi.unstubAllGlobals();
});

describe('the bundle the browser imports is addressed BY VERSION', () => {
  it('carries the version in the PATH — a query string would be ignored by the edge', async () => {
    stubFetch([navItem('flows', '0.1.7')], { flows: manifestAt('0.1.7') });

    const [entry] = await loadMenu();

    expect(entry.entryUrl).toBe('/modules/flows/v/0.1.7/dist/flows.esm.js');
    // La comprobación que de verdad importa: la versión no puede ir en la query, porque ahí NO
    // cambia la clave de caché de esta zona (probado con `?v=$RANDOM` → `cf-cache-status: HIT`).
    expect(entry.entryUrl).not.toContain('?');
  });

  it('gives two versions of the same module two different addresses', async () => {
    // El corazón del defecto. Con la url de antes, estas dos cargas pedían el MISMO recurso, así que
    // la segunda la contestaba la caché con los bytes de la primera — y el custom element quedaba
    // registrado con el código viejo mientras el manifest decía la versión nueva.
    stubFetch([navItem('flows', '0.1.6')], { flows: manifestAt('0.1.6') });
    const [before] = await loadMenu();

    stubFetch([navItem('flows', '0.1.7')], { flows: manifestAt('0.1.7') });
    const [after] = await loadMenu();

    expect(after.entryUrl).not.toBe(before.entryUrl);
    expect(after.entryUrl).toContain('0.1.7');
  });

  it('believes the RUNTIME about the version, not a module.json that a cache may have answered', async () => {
    // `/api/navigation` va autenticada y ninguna caché la toca; `module.json` es un asset y sí puede
    // venir de una. Si el manifest llega atrasado, creerle reconstruiría el bug entero: se pediría la
    // url de la versión vieja, que además está cacheada, y volvemos a la casilla de salida.
    stubFetch([navItem('flows', '0.1.7')], { flows: manifestAt('0.1.6') });

    const [entry] = await loadMenu();

    expect(entry.entryUrl).toBe('/modules/flows/v/0.1.7/dist/flows.esm.js');
  });

  it('pide TODOS los assets del módulo por la ruta versionada, no solo el bundle', async () => {
    // `dist/icons.json` y `locales/<lang>.json` se reescriben in-place igual que el bundle: si se
    // siguen pidiendo por la url sin versión, quedan con el mismo defecto un piso más abajo.
    const urls = stubFetch([navItem('flows', '0.1.7')], { flows: manifestAt('0.1.7') });

    await loadMenu();

    const assets = urls.filter((u) => u.startsWith('/modules/') && !u.endsWith('module.json'));
    expect(assets.length).toBeGreaterThan(0);
    for (const url of assets) {
      expect(url, `${url} debe ir por la ruta versionada`).toContain('/v/0.1.7/');
    }
  });

  it('también versiona la url que usa el dashboard para montar widgets y slots', async () => {
    // `loadInstalledManifests` construye su propio `entryUrl` (widgets ADR-0054, slots ADR-0043).
    // Es una segunda puerta al mismo `import()`: arreglar solo el menú dejaría el dashboard viejo.
    stubFetch([navItem('flows', '0.1.7')], { flows: manifestAt('0.1.7') });

    const [installed] = await loadInstalledManifests();

    expect(installed.entryUrl).toBe('/modules/flows/v/0.1.7/dist/flows.esm.js');
  });

  it('cae a la url sin versión cuando nadie sabe decir la versión', async () => {
    // Un runtime anterior a hub#935 no manda `module_version` y hay manifests sin `version`. Ahí no
    // hay nada mejor que la url de siempre — que ahora el servidor marca como «revalida siempre»,
    // así que sigue siendo correcta, solo que sin poder cachearse.
    stubFetch([navItem('flows')], { flows: { name: 'Flows', ui: { entry: 'dist/flows.esm.js' } } });

    const [entry] = await loadMenu();

    expect(entry.entryUrl).toBe('/modules/flows/dist/flows.esm.js');
  });
});
