// Las urls de los assets de un módulo, direccionadas por versión (hub#935).
//
// Dos funciones puras y una sola idea: **la versión va en la RUTA**. En la query no sirve — la clave
// de caché del borde de esta zona la ignora (probado: `?v=$RANDOM` → `cf-cache-status: HIT`), que es
// por lo que un módulo actualizado seguía ejecutándose viejo en el navegador.
//
// `stripModuleVersion` es el reverso, y existe porque en DESARROLLO no hay runtime detrás: los
// assets los sirve Vite desde `public/`, donde los módulos están en `public/modules/<id>/…` sin
// carpeta de versión. Sin quitar el segmento, el shell de dev pediría una ruta que no existe y
// ningún Web Component cargaría — cambiar la url de producción no puede romper el dev.
import { describe, expect, it } from 'vitest';

import { moduleBase, stripModuleVersion } from './module-url';

describe('moduleBase', () => {
  it('mete la versión en la ruta, no en la query', () => {
    expect(moduleBase('flows', '0.1.7')).toBe('/modules/flows/v/0.1.7');
  });

  it('da direcciones distintas a versiones distintas — que es TODO el arreglo', () => {
    expect(moduleBase('flows', '0.1.7')).not.toBe(moduleBase('flows', '0.1.6'));
  });

  it('escapa la versión: es texto que viene de un manifest, no una constante', () => {
    expect(moduleBase('flows', '1.0.0+build 2')).toBe('/modules/flows/v/1.0.0%2Bbuild%202');
  });

  it('sin versión conocida cae a la url de siempre (runtime anterior, manifest sin version)', () => {
    expect(moduleBase('flows', undefined)).toBe('/modules/flows');
    expect(moduleBase('flows', null)).toBe('/modules/flows');
    expect(moduleBase('flows', '')).toBe('/modules/flows');
  });
});

describe('stripModuleVersion (solo dev: Vite sirve public/, que no tiene carpeta de versión)', () => {
  it('quita el segmento de versión de cualquier asset del módulo', () => {
    expect(stripModuleVersion('/modules/flows/v/0.1.7/dist/flows.esm.js')).toBe(
      '/modules/flows/dist/flows.esm.js',
    );
    expect(stripModuleVersion('/modules/flows/v/0.1.7/module.json')).toBe(
      '/modules/flows/module.json',
    );
    expect(stripModuleVersion('/modules/flows/v/0.1.7/locales/es.json')).toBe(
      '/modules/flows/locales/es.json',
    );
  });

  it('deja intacta una url que no lleva versión', () => {
    expect(stripModuleVersion('/modules/flows/dist/flows.esm.js')).toBe(
      '/modules/flows/dist/flows.esm.js',
    );
  });

  it('no toca un `v/` que sea del propio módulo y no el marcador de versión', () => {
    // El marcador es siempre el TERCER segmento (`/modules/<id>/v/<version>/…`). Un directorio `v`
    // más adentro del módulo es suyo y se sirve tal cual.
    expect(stripModuleVersion('/modules/flows/dist/v/0.1.7/x.js')).toBe(
      '/modules/flows/dist/v/0.1.7/x.js',
    );
  });

  it('deja en paz lo que no es un asset de módulo', () => {
    expect(stripModuleVersion('/api/navigation')).toBe('/api/navigation');
    expect(stripModuleVersion('/assets/index.js')).toBe('/assets/index.js');
  });
});
