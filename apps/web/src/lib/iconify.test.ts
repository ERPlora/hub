// El data-URI que produce `svgToIcon` no es un formato libre: ionicons lo INSPECCIONA para decidir
// cómo cargarlo (dist/collection/components/icon/request.js → getSvgContent):
//
//   if (isSvgDataUrl(url) && isEncodedDataUrl(url))  → lo parsea con DOMParser, SIN red.
//                                                      ("This works with content security policies
//                                                       enabled", dice su propio comentario.)
//   si no                                            → fetchSvg(url) → fetch() por cada icono.
//
// Los dos predicados (icon/validate.js:44-45) son literalmente:
//   isSvgDataUrl     = url.startsWith('data:image/svg+xml')
//   isEncodedDataUrl = url.indexOf(';utf8,') !== -1        ← el marcador que hay que emitir
//
// Sin `;utf8,` los iconos siguen viéndose (un fetch a una data: URL funciona), pero pagamos una
// petición por icono y quedamos a merced del `connect-src` de la CSP — y OutfitKit corre también
// en el SaaS, que tiene CSP estricta. Este test fija el contrato.
import { describe, expect, it } from 'vitest';
import { svgToIcon, isInlineSvg } from './iconify';

const SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><path d="M1 2"/></svg>';

// Los mismos predicados que aplica ionicons, copiados de icon/validate.js:44-45.
const isSvgDataUrl = (url: string) => url.startsWith('data:image/svg+xml');
const isEncodedDataUrl = (url: string) => url.indexOf(';utf8,') !== -1;

describe('svgToIcon', () => {
  it('produce un data-URI que ionicons parsea con DOMParser, sin fetch', () => {
    const icon = svgToIcon(SVG);
    expect(isSvgDataUrl(icon), `ionicons no lo reconocería como SVG: ${icon.slice(0, 40)}`).toBe(true);
    expect(isEncodedDataUrl(icon), 'falta el marcador ";utf8," → ionicons haría fetch() por icono').toBe(true);
  });

  it('deja el SVG CRUDO en el data-URI: DOMParser busca el tag <svg> dentro de la propia URL', () => {
    // La trampa: con `;utf8,` ionicons deja de hacer fetch… y hace
    //   `new DOMParser().parseFromString(url, 'text/html').querySelector('svg')`   (request.js:41)
    // sobre la URL ENTERA. Si el SVG va percent-encoded (`%3Csvg…`) no hay ningún tag <svg> que
    // encontrar → lanza "Could not parse svg" y el icono sale VACÍO. Por eso el propio set de
    // ionicons emite `data:image/svg+xml;utf8,<svg xmlns=…` sin codificar.
    const icon = svgToIcon(SVG);
    expect(icon, 'el SVG va codificado → DOMParser no encuentra el tag y el icono sale vacío').toContain('<svg');
    expect(icon).not.toContain('%3Csvg');
    // Lo que haría ionicons: quedarse con lo que hay a partir del primer `<svg`.
    expect(icon.slice(icon.indexOf('<svg'))).toBe(SVG);
  });
});

describe('isInlineSvg', () => {
  it('distingue un SVG inline (lo trae un módulo) de un nombre a resolver', () => {
    expect(isInlineSvg(SVG)).toBe(true);
    expect(isInlineSvg('  <svg viewBox="0 0 1 1"></svg>')).toBe(true);
    expect(isInlineSvg('cart-outline')).toBe(false);
  });
});
