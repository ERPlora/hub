// El guardarraíl que faltaba: **toda cadena del catálogo tiene que poder PINTARSE** (hub#1293).
//
// Cómo se descubrió: la capa del art. 13 RGPD del otorgamiento decía «…portabilidad en
// privacy@erplora.com». Para vue-i18n, `@` abre un **mensaje enlazado** (`@:otra.clave`), así que
// esa cadena no compila — y no falla ella sola: revienta el `render` del componente entero con
// «Invalid linked format», dejando la pantalla EN BLANCO. En producción eso es una pantalla fiscal
// que no se pinta; y ninguna de las 500 pruebas de componentes lo vio, porque todas montan con un
// catálogo de mensajes VACÍO y `t('x.y')` devuelve la clave sin compilar nada.
//
// La familia es más grande que ese `@`: `{` sin cerrar, `|` (que vue-i18n lee como plural) y
// `@:`/`@.lower:` mal escritos rompen igual. Por eso el guardia es mecánico y barre el catálogo
// entero, en vez de arreglar la línea y seguir — es la única forma de que la siguiente dirección de
// correo que alguien pegue sin escapar salga en rojo aquí y no en el mostrador.
//
// La escapatoria correcta es la que ya usaba `emailPlaceholder`: `"you{'@'}company.com"`.
import { describe, expect, it } from 'vitest';
import { createI18n } from 'vue-i18n';

const localeModules = import.meta.glob<{ default: Record<string, unknown> }>('./locales/*.ts', {
  eager: true,
});

/** Every leaf key path of a catalogue, dotted (`nav.home`). Arrays count as leaves. */
function keyPaths(node: unknown, prefix = ''): string[] {
  if (node === null || typeof node !== 'object' || Array.isArray(node)) return [prefix];
  return Object.entries(node as Record<string, unknown>).flatMap(([key, value]) =>
    keyPaths(value, prefix ? `${prefix}.${key}` : key),
  );
}

const catalogues = Object.entries(localeModules).map(
  ([path, mod]) => [path.match(/\/([^/]+)\.ts$/)?.[1] ?? path, mod.default] as const,
);

describe('todas las cadenas compilan', () => {
  for (const [locale, messages] of catalogues) {
    it(`«${locale}» no tiene ni una cadena que reviente al pintarse`, () => {
      const i18n = createI18n({
        legacy: false,
        locale,
        // Sin fallback: se está probando ESTE catálogo, no lo que otro taparía.
        fallbackLocale: locale,
        missingWarn: false,
        fallbackWarn: false,
        messages: { [locale]: messages } as Record<string, never>,
      });
      const broken: string[] = [];
      for (const path of keyPaths(messages)) {
        try {
          i18n.global.t(path);
        } catch (e) {
          broken.push(`${path}: ${e instanceof Error ? e.message : String(e)}`);
        }
      }
      expect(broken).toEqual([]);
    });
  }
});
