// Tests de la PALETA de tema (ADR-0138, ERPlora/pm#15) — dos capas:
//
//   - hub_settings.theme_palette  → paleta GLOBAL del hub (la fija un admin en /settings)
//   - localStorage `erplora.palette` → override POR USUARIO en este navegador
//
// Sin override local se aplica la global; con override, gana el override. Aplicar =
// atributo `data-ok-palette` en el <html> ('erplora' = default → SIN atributo), el
// mismo contrato que applyPalette() de OutfitKit y que el Cloud.
//
// Entorno node puro (como open-external.test.ts): window/document/localStorage stubbeados;
// vi.resetModules() por test porque theme.ts guarda estado a nivel de módulo.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

type ThemeModule = typeof import('./theme');

function stubDom(): { root: { attrs: Map<string, string> }; store: Map<string, string> } {
  const attrs = new Map<string, string>();
  const store = new Map<string, string>();
  const root = {
    attrs,
    classList: { toggle: vi.fn() },
    setAttribute: (k: string, v: string) => attrs.set(k, v),
    removeAttribute: (k: string) => attrs.delete(k),
    hasAttribute: (k: string) => attrs.has(k),
    getAttribute: (k: string) => attrs.get(k) ?? null,
  };
  vi.stubGlobal('document', {
    documentElement: root,
    // Vue runtime-dom crea un <template> contenedor AL IMPORTARSE; el stub debe soportarlo.
    createElement: () => ({ innerHTML: '', content: { firstChild: null }, cloneNode: () => ({}) }),
  });
  vi.stubGlobal('window', {
    matchMedia: () => ({ matches: false, addEventListener: vi.fn() }),
  });
  vi.stubGlobal('localStorage', {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => store.set(k, v),
    removeItem: (k: string) => store.delete(k),
  });
  return { root, store };
}

async function loadTheme(): Promise<ThemeModule> {
  vi.resetModules();
  return await import('./theme');
}

let dom: ReturnType<typeof stubDom>;

beforeEach(() => {
  dom = stubDom();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('paleta: default', () => {
  it('sin nada elegido, el <html> queda SIN data-ok-palette (marca erplora)', async () => {
    const t = await loadTheme();
    t.bootTheme();
    expect(dom.root.attrs.has('data-ok-palette')).toBe(false);
    expect(t.themePalette.value).toBe('erplora');
  });
});

describe('paleta: override local (por usuario)', () => {
  it('setLocalPalette aplica el atributo y persiste en erplora.palette', async () => {
    const t = await loadTheme();
    t.bootTheme();
    t.setLocalPalette('ocean');
    expect(dom.root.attrs.get('data-ok-palette')).toBe('ocean');
    expect(dom.store.get('erplora.palette')).toBe('ocean');
    expect(t.themePalette.value).toBe('ocean');
  });

  it("setLocalPalette('erplora') QUITA el atributo (default explícito)", async () => {
    const t = await loadTheme();
    t.bootTheme();
    t.setLocalPalette('ocean');
    t.setLocalPalette('erplora');
    expect(dom.root.attrs.has('data-ok-palette')).toBe(false);
  });

  it('el override guardado se aplica en el boot', async () => {
    dom.store.set('erplora.palette', 'violet');
    const t = await loadTheme();
    t.bootTheme();
    expect(dom.root.attrs.get('data-ok-palette')).toBe('violet');
  });

  it('un valor corrupto en localStorage se ignora (sin atributo)', async () => {
    dom.store.set('erplora.palette', 'glass'); // id viejo del Cloud, ya no existe
    const t = await loadTheme();
    t.bootTheme();
    expect(dom.root.attrs.has('data-ok-palette')).toBe(false);
  });
});

describe('paleta: global del hub (hub_settings)', () => {
  it('sin override local, la global del hub se aplica al llegar', async () => {
    const t = await loadTheme();
    t.bootTheme();
    t.setHubPalette('forest');
    expect(dom.root.attrs.get('data-ok-palette')).toBe('forest');
    expect(t.themePalette.value).toBe('forest');
  });

  it('el override local GANA a la global', async () => {
    dom.store.set('erplora.palette', 'ocean');
    const t = await loadTheme();
    t.bootTheme();
    t.setHubPalette('forest');
    expect(dom.root.attrs.get('data-ok-palette')).toBe('ocean');
  });

  it("quitar el override local ('' = seguir al hub) vuelve a la global", async () => {
    const t = await loadTheme();
    t.bootTheme();
    t.setHubPalette('forest');
    t.setLocalPalette('ocean');
    t.setLocalPalette('');
    expect(dom.root.attrs.get('data-ok-palette')).toBe('forest');
    expect(dom.store.has('erplora.palette')).toBe(false);
  });

  it('una global desconocida degrada al default (sin atributo)', async () => {
    const t = await loadTheme();
    t.bootTheme();
    t.setHubPalette('rainbow');
    expect(dom.root.attrs.has('data-ok-palette')).toBe(false);
  });
});
