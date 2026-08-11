// hub#714 — el cliente que el shell le pone a un Web Component de módulo va SIEMPRE con el id de
// ese módulo (`client.forModule(id)`).
//
// Por qué importa: `client.flows` (la puerta declarada al kernel de automatización, ADR-0283 §9)
// solo existe en un cliente con scope, y el runtime lee ese id para exigir la capability
// `manage_flows`. Quien conoce de verdad qué módulo se está montando es EL SHELL —es él quien
// carga el bundle y crea el elemento—, así que el id sale del cargador y no de lo que el módulo
// diga de sí mismo. Un sitio de montaje que se deje sin envolver le quita la puerta al módulo
// («esto no funciona en el widget y sí en la página») sin que nada más se entere.
//
// Es un test de FUENTE a propósito: el fallo que previene es una ASIGNACIÓN OLVIDADA en un quinto
// sitio de montaje que alguien añada mañana, y eso no lo ve ninguna prueba de comportamiento de
// los cuatro que hoy existen.
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

/** Todos los ficheros del shell que MONTAN el WC de un módulo y le pasan el cliente. */
const MOUNTS = [
  new URL('../views/ModuleView.vue', import.meta.url),
  new URL('./dashboard-widgets.ts', import.meta.url),
];

describe('hub#714: el WC de un módulo recibe un cliente con scope', () => {
  for (const url of MOUNTS) {
    const file = url.pathname.split('/').slice(-1)[0];
    const source = readFileSync(url, 'utf8');

    it(`${file} no entrega NUNCA el cliente sin scope`, () => {
      // Cualquier `el.client = <algo>` cuyo lado derecho no sea un `forModule(...)`.
      const unscoped = [...source.matchAll(/\.client\s*=\s*([^;\n]+)/g)]
        .map((m) => m[1].trim())
        .filter((rhs) => !rhs.includes('forModule('));
      expect(unscoped, `sin scope en ${file}: ${unscoped.join(' · ')}`).toEqual([]);
    });

    it(`${file} monta al menos un WC de módulo (el test no se ha quedado sin sujeto)`, () => {
      expect(source).toMatch(/\.client\s*=/);
    });
  }
});
