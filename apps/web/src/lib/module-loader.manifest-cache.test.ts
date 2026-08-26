// @vitest-environment happy-dom
//
// Un `module.json` ya leído no se vuelve a pedir en la misma sesión (hub#1099).
//
// El defecto medido en un hub QA con **25 módulos**: cada navegación pedía los 25 manifests
// **4,04 veces** (101 peticiones, 25 urls únicas, ~1,6 MB por montaje), y el ritmo en reposo CRECÍA
// con cada navegación hasta ~75 req/s ≈ 24 MB/min con la pestaña quieta. Para la tablet del
// mostrador en 4G eso es el plan de datos y la batería.
//
// La causa no es un bucle exótico: es que `loadManifest()` no cacheaba NADA y hay **tres** puertas
// que recorren TODOS los módulos instalados en cada montaje de ruta —`loadMenu`,
// `loadInstalledManifests` (widgets ADR-0054 + slots ADR-0043) y `resolveProtectsGuard`
// (hub#775)—. Cada una multiplicaba por 25. Y como `globalThis.erplora.loadSlot` está cableado a
// `loadSlotComponents` → `loadInstalledManifests` (main.ts), CUALQUIER Web Component de módulo que
// pida un slot repetidamente convierte su propia cadencia en una tormenta de 25 peticiones por
// llamada. Ese es el amplificador que hacía crecer el ritmo: el shell no ponía techo.
//
// Lo que se fija aquí es el techo: **N módulos = N peticiones**, no 4N ni 25× por cada quien
// pregunte. Con caché de sesión, un llamador repetido cuesta CERO red.
//
// Es invisible con 3 módulos y grave con 25: por eso los tests montan 25, que es el hub real.
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('./icons', () => ({ moduleIconRegistry: (i: Record<string, string>) => i }));
vi.mock('ionicons', () => ({ addIcons: () => {} }));
vi.mock('../i18n', () => ({ getLocale: () => 'en' }));
vi.mock('./entitlement', () => ({ isModuleEntitled: () => true }));

/** Los módulos que el runtime reporta como instalados y activos (`GET /api/modules`). */
const installedModules = vi.fn<() => Promise<{ id: string; status: string }[]>>();
vi.mock('./runtime', () => ({
  RUNTIME_URL: '',
  runtimeHeaders: () => ({}),
  listInstalledModules: () => installedModules(),
}));

import {
  invalidateManifestCache,
  loadInstalledManifests,
  loadManifest,
  loadMenu,
} from './module-loader';
import { resolveProtectsGuard } from './protects';

/** El hub que se midió: 25 módulos instalados y activos. */
const MODULE_COUNT = 25;
const MODULE_IDS = Array.from({ length: MODULE_COUNT }, (_, i) => `mod-${i + 1}`);

function navItem(moduleId: string) {
  return {
    module_id: moduleId,
    module_name: moduleId,
    module_version: '1.0.0',
    id: `${moduleId}-main`,
    label: moduleId,
    icon: null,
    component: `erp-${moduleId}`,
  };
}

const manifestOf = (moduleId: string) => ({
  name: moduleId,
  version: '1.0.0',
  ui: { entry: `dist/${moduleId}.esm.js` },
});

/** `fetch` de mentira que APUNTA cada url pedida — las peticiones son lo que se está midiendo. */
function stubFetch(options: { manifestStatus?: () => number } = {}): string[] {
  const urls: string[] = [];
  const status = options.manifestStatus ?? (() => 200);
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      urls.push(url);
      if (url.startsWith('/api/navigation')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            ok: true,
            data: MODULE_IDS.map(navItem),
            active_modules: MODULE_COUNT,
          }),
        } as unknown as Response;
      }
      const match = /^\/modules\/([^/]+)(?:\/v\/[^/]+)?\/module\.json$/.exec(url);
      if (match) {
        const code = status();
        if (code !== 200) return { ok: false, status: code, json: async () => ({}) } as unknown as Response;
        return { ok: true, status: 200, json: async () => manifestOf(match[1]) } as unknown as Response;
      }
      // Los sidecars del módulo (`dist/icons.json`, `dist/outfitkit.json`, `locales/<lang>.json`)
      // se barren igual que el manifest, 25 a 25, en la misma pasada. Aquí se sirven de verdad
      // para poder CONTARLOS: son el mismo defecto un piso más abajo.
      if (url.startsWith('/modules/')) {
        return { ok: true, status: 200, json: async () => ({}) } as unknown as Response;
      }
      return { ok: false, status: 404, json: async () => ({}) } as unknown as Response;
    }),
  );
  return urls;
}

/** Las peticiones de manifest que hubo — la unidad que cuenta la issue. */
const manifestHits = (urls: string[]): string[] => urls.filter((u) => u.endsWith('module.json'));

/** Un cliente del runtime que no sabe nada: las queries del guard degradan abiertas. */
const client = { query: vi.fn(async () => []) } as never;

beforeEach(() => {
  vi.unstubAllGlobals();
  invalidateManifestCache();
  installedModules.mockReset();
  installedModules.mockResolvedValue(MODULE_IDS.map((id) => ({ id, status: 'active' })));
});

/**
 * Lo que hace el shell al montar `/m/<id>`: el menú (`loadMenu`), el manifest del módulo activo
 * (pestañas Plan/Ajustes y `chrome`) y el guard `protects` de la ruta. Tres puertas, los mismos 25
 * manifests. Es la secuencia real de `views/ModuleView.vue#mount()`.
 */
async function mountModuleRoute(moduleId: string): Promise<void> {
  await loadMenu();
  await loadManifest(moduleId);
  await resolveProtectsGuard(client, `/m/${moduleId}`);
}

describe('el manifest de un módulo se lee UNA vez por sesión (hub#1099)', () => {
  it('una carga en frío de una ruta de módulo pide N manifests, no 4N', async () => {
    const urls = stubFetch();

    await mountModuleRoute('mod-1');

    // El techo de la issue: 25 módulos → 25 peticiones. Antes eran 51 por este camino (25 del menú
    // + 1 del módulo activo + 25 del guard) y 101 en el hub real, donde además entran los widgets.
    expect(manifestHits(urls)).toHaveLength(MODULE_COUNT);
    expect(new Set(manifestHits(urls)).size).toBe(MODULE_COUNT);
  });

  it('dos llamadas concurrentes al mismo manifest comparten UNA sola petición', async () => {
    const urls = stubFetch();

    // Sin dedupe de peticiones en vuelo, una caché por sí sola no basta: las tres puertas del
    // montaje arrancan a la vez y ninguna ha terminado cuando la siguiente empieza.
    const [a, b, c] = await Promise.all([
      loadManifest('mod-1'),
      loadManifest('mod-1'),
      loadManifest('mod-1'),
    ]);

    expect(manifestHits(urls)).toHaveLength(1);
    expect(a).toEqual(b);
    expect(b).toEqual(c);
  });

  it('navegar 8 veces NO multiplica las peticiones: el coste se paga una vez', async () => {
    const urls = stubFetch();

    for (const moduleId of MODULE_IDS.slice(0, 8)) await mountModuleRoute(moduleId);

    // Ocho navegaciones es exactamente la medida de la issue (~75 req/s en reposo tras la octava).
    expect(manifestHits(urls)).toHaveLength(MODULE_COUNT);
  });

  it('pone techo al amplificador: `loadSlot`/widgets repetidos NO vuelven a la red', async () => {
    // `main.ts` cablea `globalThis.erplora.loadSlot` → `loadSlotComponents` → `loadInstalledManifests`.
    // Un WC de módulo que pida su slot en cada render convertía cada llamada en 25 peticiones; ese
    // es el mecanismo por el que el ritmo crecía y no bajaba. Con caché, la 2ª llamada cuesta 0.
    const urls = stubFetch();

    await loadInstalledManifests();
    const afterFirst = manifestHits(urls).length;
    for (let i = 0; i < 20; i += 1) await loadInstalledManifests();

    expect(afterFirst).toBe(MODULE_COUNT);
    expect(manifestHits(urls)).toHaveLength(MODULE_COUNT);
  });

  it('tampoco vuelve a la red por los SIDECARS del módulo (iconos, sello, traducciones)', async () => {
    // `loadInstalledManifests` pide, por módulo y en cada llamada: el manifest, `dist/icons.json`,
    // `dist/outfitkit.json` y —fuera del inglés canónico— `locales/<lang>.json`. Cachear solo el
    // manifest habría dejado tres cuartas partes de la tormenta intactas y el mismo `loadSlot`
    // repetido costando ~75 peticiones en vez de ~100. Se cachea la pasada entera o no sirve.
    const urls = stubFetch();

    await loadInstalledManifests();
    const afterFirst = urls.filter((u) => u.startsWith('/modules/')).length;
    for (let i = 0; i < 10; i += 1) await loadInstalledManifests();

    expect(afterFirst).toBeGreaterThan(MODULE_COUNT); // manifest + sidecars
    expect(urls.filter((u) => u.startsWith('/modules/'))).toHaveLength(afterFirst);
  });

  it('un manifest ilegible NO se recuerda: un 500 pasajero no borra el módulo de la sesión', async () => {
    // Cachear el fallo sería peor que no cachear: un 5xx durante el arranque dejaría al módulo sin
    // menú, sin widgets y sin guard para el resto de la sesión, y sin nada en pantalla que lo diga.
    let code = 500;
    const urls = stubFetch({ manifestStatus: () => code });

    expect(await loadManifest('mod-1')).toBeNull();
    code = 200;
    expect(await loadManifest('mod-1')).toEqual(manifestOf('mod-1'));
    expect(manifestHits(urls)).toHaveLength(2);
  });

  it('`invalidateManifestCache()` lo vuelve a pedir — instalar un módulo cambia el conjunto', async () => {
    const urls = stubFetch();

    await loadManifest('mod-1');
    invalidateManifestCache();
    await loadManifest('mod-1');

    expect(manifestHits(urls)).toHaveLength(2);
  });
});
