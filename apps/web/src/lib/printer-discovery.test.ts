// hub#338 — las DOS frases que decide todo.
//
// «No encuentro impresoras» y «el sistema no me deja buscarlas» acababan en la misma pantalla
// vacía, y le piden al usuario cosas OPUESTAS: conectar una impresora, o darle un permiso a la
// app. Quien se cree la frase equivocada pierde la tarde: la impresora lleva encendida todo el
// rato, o al revés, se pone a tocar ajustes del sistema que ya estaban bien.
//
// Estos tests fijan el copy: no que exista, sino que cada frase mande a hacer LO SUYO — y que
// nunca digan lo mismo.
import { describe, expect, it } from 'vitest';

import { i18n } from '../i18n';
import { printerDiscoveryMessage } from './printer-discovery';

/** Cambia el idioma del shell durante una comprobación (y lo deja como estaba). */
function withLocale<T>(locale: string, fn: () => T): T {
  const previous = i18n.global.locale.value;
  i18n.global.locale.value = locale;
  try {
    return fn();
  } finally {
    i18n.global.locale.value = previous;
  }
}

describe('printerDiscoveryMessage: los dos finales de un escaneo', () => {
  it('las dos frases existen en inglés (fuente) y en español, y NO son la misma', () => {
    for (const locale of ['en', 'es']) {
      withLocale(locale, () => {
        const blocked = printerDiscoveryMessage('permission_denied');
        const none = printerDiscoveryMessage('no_printers');
        expect(blocked.length).toBeGreaterThan(20);
        expect(none.length).toBeGreaterThan(20);
        expect(blocked).not.toEqual(none);
        // Una clave sin traducir sale como la propia clave: sería un mensaje inútil en pantalla.
        expect(blocked).not.toContain('hardware.');
        expect(none).not.toContain('hardware.');
      });
    }
  });

  it('sin permiso manda a los AJUSTES, no a buscar una impresora que ya está encendida', () => {
    withLocale('en', () => {
      const blocked = printerDiscoveryMessage('permission_denied').toLowerCase();
      expect(blocked).toContain('permission');
      expect(blocked).toContain('settings');
    });
    withLocale('es', () => {
      const blocked = printerDiscoveryMessage('permission_denied').toLowerCase();
      expect(blocked).toContain('permiso');
      expect(blocked).toContain('ajustes');
    });
  });

  it('con permiso y cero impresoras manda a la IMPRESORA, sin hablar de permisos', () => {
    withLocale('en', () => {
      const none = printerDiscoveryMessage('no_printers').toLowerCase();
      expect(none).toContain('printer');
      expect(none).not.toContain('permission');
    });
    withLocale('es', () => {
      const none = printerDiscoveryMessage('no_printers').toLowerCase();
      expect(none).toContain('impresora');
      expect(none).not.toContain('permiso');
    });
  });
});
