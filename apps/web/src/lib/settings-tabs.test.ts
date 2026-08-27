import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolveSettingsTab, SETTINGS_TABS } from './settings-tabs';

const settingsSource = readFileSync(new URL('../views/SettingsPage.vue', import.meta.url), 'utf8');
const profileSource = readFileSync(new URL('../views/ProfilePage.vue', import.meta.url), 'utf8');

describe('navegación de Ajustes', () => {
  // La fila de hardware de Ajustes decía «ERPlora Bridge» y, al lado, «Desactivado» — las dos cosas
  // FALSAS a la vez: «Bridge» es una app que ADR-0196 eliminó, y el estado era una cadena LITERAL,
  // así que rezaba «Desactivado» siempre: dentro de la app instalada, en el navegador, y con la
  // impresora imprimiendo. Un usuario con el hardware funcionando leía que no lo tenía.
  //
  // El lenguaje correcto ya lo fijó hub#500 en `SystemPage`: se habla de la impresora del mostrador,
  // no de un proceso. Nadie que lleva un bar sabe qué es un «bridge».
  it('la fila de hardware no nombra al Bridge, que ya no existe', () => {
    expect(settingsSource).not.toContain('ERPlora Bridge');
    expect(settingsSource).not.toContain('bridgeDesc');
  });

  it('el estado del hardware se LEE, no se escribe a mano', () => {
    // La prueba de que no vuelve a cablearse: el literal `settings.disabled` suelto era todo el
    // «estado». Ahora la fila depende de si estamos dentro de la app instalada.
    expect(settingsSource).toContain('isTauri');
    expect(settingsSource).not.toMatch(/slot="end">\{\{ t\('settings\.disabled'\) \}\}/);
  });

  it('la fila de hardware lleva a algún sitio en vez de fingir que se pulsa', () => {
    // Tenía `button detail` —la flecha que promete que algo pasa— y ni un `@click`. Un control que
    // no hace nada al pulsarlo es el defecto que hub#475 tuvo que arreglar en otras diez pantallas.
    const fila = settingsSource.slice(settingsSource.indexOf("t('settings.hardware')"));
    const item = fila.slice(0, fila.indexOf('</ion-card>'));
    if (item.includes('button')) {
      expect(item).toMatch(/@click|href|router-link/);
    }
  });

  it('no ofrece una pestaña Tienda duplicada', () => {
    expect(SETTINGS_TABS).toEqual(['hub', 'tax', 'tickets', 'permissions', 'data']);
    expect(SETTINGS_TABS).not.toContain('store');
  });

  it('redirige el enlace antiguo de Tienda a los ajustes del Hub', () => {
    expect(resolveSettingsTab('#store')).toBe('hub');
    expect(resolveSettingsTab('#hub')).toBe('hub');
  });

  it('conserva los enlaces de las pestañas vigentes', () => {
    expect(resolveSettingsTab('#tax')).toBe('tax');
    expect(resolveSettingsTab('#tickets')).toBe('tickets');
    expect(resolveSettingsTab('#permissions')).toBe('permissions');
    expect(resolveSettingsTab('#data')).toBe('data');
  });

  it('mantiene exactamente una paleta global en Ajustes y una personal en Perfil', () => {
    expect(settingsSource.match(/<ok-theme-picker/g)).toHaveLength(1);
    expect(profileSource.match(/<ok-theme-picker/g)).toHaveLength(1);
  });

  it('no conserva el contenido ni el selector de la antigua Tienda', () => {
    expect(settingsSource).not.toContain("tab === 'store'");
    expect(settingsSource).not.toContain('value="store"');
    expect(settingsSource).not.toContain('storeType');
    expect(settingsSource).not.toContain('storeLocale');
  });

  it('does not show local-only Hub controls that pretend to save', () => {
    expect(settingsSource).not.toContain('showModulesInSidebar');
    expect(settingsSource).not.toContain('saveHubSettings');
    expect(settingsSource).toContain('country_code: value');
  });

  // Esta guarda vigilaba la zona horaria PROHIBIENDO la palabra `hubTimezone`, porque el control
  // que había era `const hubTimezone = ref<string>('madrid')` atado a un `v-model` y a nada más:
  // ni el valor era IANA ni cambiarlo salía del navegador. Prohibir el nombre servía mientras la
  // fila no existía; ahora existe y guarda de verdad (hub#1154), así que la guarda pasa a afirmar
  // lo que de verdad importaba — que PERSISTE — en vez de un nombre. Prohibir la palabra habría
  // bloqueado el arreglo; borrar la guarda habría dejado volver al control de mentira.
  it('el selector de zona horaria GUARDA de verdad, no es un ref local que finge', () => {
    // El valor de mentira original. `'madrid'` no es un nombre IANA: no lo aceptaría ni el runtime.
    expect(settingsSource).not.toMatch(/ref<string>\(\s*'madrid'\s*\)/);
    // La fila existe…
    expect(settingsSource).toContain("t('settings.timezone')");
    // …y su cambio va por el MISMO persistidor que el resto de ajustes del hub, con la clave
    // `timezone`. Un `v-model` suelto vuelve a dejar esto en rojo.
    expect(settingsSource).toMatch(/function onTimezoneChange[\s\S]{0,800}persistHubSettings\(\{\s*timezone:/);
  });
});
